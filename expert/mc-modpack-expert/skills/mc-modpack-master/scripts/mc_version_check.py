#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mc_version_check —— 升级前置校验

背景（真实踩过的坑）:
    reeses-sodium-options 1.8.3+mc1.21.4 声明 depends: sodium >= 0.6.5，本地 0.6.13 满足，工作正常。
    误判为"版本分支不对"，升到标称 1.21.1 的 2.2.4，结果它硬依赖 sodium = 0.8.13 —— 启动直接崩。
    教训: version_number 里的 MC 号是构建标记，真正的兼容性只在 depends 的版本区间里。

用法:
    python mc_version_check.py --instance <实例目录> --mod reeses-sodium-options
    python mc_version_check.py --instance <实例目录> --list          # 只看哪些模组有新版
    python mc_version_check.py --instance <实例目录> --mod X --top 3 --apply   # 校验通过才替换

--apply 会备份旧 jar 到 <instance>/mods_backup_<日期>/，不做静默删除。
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

UA = {"User-Agent": "mc-modpack-master/1.0 (audit)"}
API = "https://api.modrinth.com/v2"


def api(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def installed_mods(instance):
    out = {}
    for jar in sorted((Path(instance) / "mods").glob("*.jar")):
        try:
            with zipfile.ZipFile(jar) as z:
                if "fabric.mod.json" not in z.namelist():
                    continue
                m = json.loads(z.read("fabric.mod.json").decode("utf-8", errors="replace"))
            out[m.get("id")] = {"version": str(m.get("version", "?")), "jar": jar,
                                "depends": m.get("depends") or {}, "name": m.get("name")}
        except Exception:
            continue
    return out


# ------------------------------------------------------------ 版本约束

def _nums(v):
    return [int(x) for x in re.findall(r"\d+", str(v))[:4]]


def cmp_ver(a, b):
    na, nb = _nums(a), _nums(b)
    n = max(len(na), len(nb))
    na += [0] * (n - len(na))
    nb += [0] * (n - len(nb))
    return (na > nb) - (na < nb)


def satisfies(installed, constraint):
    """支持 >=, >, <=, <, =, ~, ^, * 与空格分隔的区间。"""
    if not constraint or constraint.strip() in ("*", ""):
        return True, ""
    for part in constraint.split():
        part = part.strip()
        m = re.match(r"^(>=|<=|>|<|=|~|\^)?\s*(.+)$", part)
        if not m:
            continue
        op, ver = m.group(1) or "=", m.group(2).strip()
        c = cmp_ver(installed, ver)
        ok = {"=": c == 0, ">=": c >= 0, ">": c > 0, "<=": c <= 0, "<": c < 0,
              "~": c >= 0 and _nums(installed)[:2] == _nums(ver)[:2],
              "^": c >= 0 and _nums(installed)[:1] == _nums(ver)[:1]}.get(op, True)
        if not ok:
            return False, f"{op}{ver} 不满足（本地 {installed}）"
    return True, ""


# ------------------------------------------------------------ 候选版本

def candidates(slug, mcver, loader):
    url = f"{API}/project/{urllib.parse.quote(slug)}/version?game_versions=%5B%22{mcver}%22%5D&loaders=%5B%22{loader}%22%5D"
    try:
        return api(url)
    except Exception as e:
        print(f"  查询失败: {e}")
        return []


def read_remote_meta(version):
    """下载候选 jar 的 fabric.mod.json（只读元数据，不安装）。"""
    files = [f for f in version["files"] if f["filename"].endswith(".jar") and "sources" not in f["filename"]]
    if not files:
        return None
    f = files[0]
    tmp = Path(tempfile.gettempdir()) / f"mcvc_{int(time.time()*1000)}.jar"
    try:
        req = urllib.request.Request(f["url"], headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as o:
            shutil.copyfileobj(r, o)
        with zipfile.ZipFile(tmp) as z:
            if "fabric.mod.json" in z.namelist():
                return json.loads(z.read("fabric.mod.json").decode("utf-8", errors="replace")), f
            if "META-INF/neoforge.mods.toml" in z.namelist() or "META-INF/mods.toml" in z.namelist():
                return {"_forge": True}, f
    except Exception as e:
        print(f"    读取元数据失败: {e}")
    finally:
        tmp.unlink(missing_ok=True)
    return None, f


def preflight(meta, installed, ignore=("minecraft", "java", "fabricloader", "fabric-api",
                                       "fabric", "forge", "neoforge")):
    """返回 (是否通过, 违规列表)。"""
    bad = []
    if not meta or meta.get("_forge"):
        return True, []          # 非 Fabric 元数据，跳过深度校验
    for dep, constraint in (meta.get("depends") or {}).items():
        if dep in ignore:
            continue
        if dep not in installed:
            bad.append(f"缺少依赖 {dep} {constraint}")
            continue
        ok, why = satisfies(installed[dep]["version"], str(constraint))
        if not ok:
            bad.append(f"{dep} 需要 {constraint}，{why}")
    return not bad, bad


def guess_mc_version(instance):
    """推断 MC 版本。

    坑：直接对 depends.minecraft 去非数字字符会得到 "1.21"（因为常量写作 ">=1.21"），
    而 1.21 与 1.21.1 在 Modrinth 上是两个不同的 game_version，会查错分支。
    """
    inst = Path(instance)
    import collections

    # 1) 同级目录里形如 1.21.1 的版本文件夹最可信（版本隔离时一定存在）
    siblings = []
    if inst.parent.exists():
        for sib in inst.parent.iterdir():
            if sib.is_dir() and re.fullmatch(r"\d+\.\d+(\.\d+)?", sib.name):
                siblings.append(sib.name)

    # 2) 模组元数据里出现的完整版本号，取众数
    seen = collections.Counter()
    for jar in (inst / "mods").glob("*.jar"):
        try:
            with zipfile.ZipFile(jar) as z:
                if "fabric.mod.json" not in z.namelist():
                    continue
                m = json.loads(z.read("fabric.mod.json").decode("utf-8", errors="replace"))
        except Exception:
            continue
        for v in re.findall(r"\d+\.\d+\.\d+", str((m.get("depends") or {}).get("minecraft", ""))):
            seen[v] += 1

    if seen:
        best = seen.most_common(1)[0][0]
        # 三段版本优先；若同级目录里有同名版本，直接采信
        if best in siblings:
            return best
        same_minor = [s for s in siblings if s.split(".")[:2] == best.split(".")[:2]]
        if same_minor:
            return same_minor[0]
        return best
    if siblings:
        return sorted(siblings, key=lambda v: [int(x) for x in v.split(".")])[-1]
    return "1.21.1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--mod", help="要检查的模组 id")
    ap.add_argument("--mcver", help="游戏版本，默认从模组元数据推断")
    ap.add_argument("--loader", default="fabric")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--apply", action="store_true", help="校验通过就替换（会备份）")
    ap.add_argument("--list", action="store_true", help="列出所有模组是否有新版")
    a = ap.parse_args()

    inst = Path(a.instance)
    mods = installed_mods(inst)
    mcver = a.mcver or guess_mc_version(inst)
    print(f"实例 {inst}\nMC {mcver} / {a.loader} / 已装 {len(mods)} 个模组\n")

    if a.list:
        for mid, info in sorted(mods.items()):
            vers = candidates(mid, mcver, a.loader)
            if not vers:
                continue
            newest = vers[0]["version_number"]
            if cmp_ver(newest, info["version"]) > 0:
                print(f"  {mid:32s} {info['version']:20s} → {newest}")
        return 0

    if not a.mod:
        print("需要 --mod 或 --list")
        return 2

    info = mods.get(a.mod)
    print(f"当前: {a.mod} {info['version'] if info else '(未安装)'}"
          f"  {info['jar'].name if info else ''}")

    vers = candidates(a.mod, mcver, a.loader)
    if not vers:
        print("Modrinth 上没有该 MC 版本 / 加载器的构建")
        return 1

    passed = None
    for v in vers[:a.top]:
        vn = v["version_number"]
        newer = cmp_ver(vn, info["version"]) > 0 if info else True
        print(f"\n候选 {vn}  ({v['date_published'][:10]})  {'新版' if newer else '当前/更旧'}")
        meta, f = read_remote_meta(v)
        ok, bad = preflight(meta, mods)
        if ok:
            print("  依赖校验: 通过")
            if passed is None and newer:
                passed = (v, f)
        else:
            print("  依赖校验: 不通过")
            for b in bad:
                print(f"    - {b}")

    if a.apply:
        if not passed:
            print("\n没有依赖校验通过的新版，未做任何改动。")
            return 1
        v, f = passed
        bak = inst / f"mods_backup_{time.strftime('%Y%m%d')}"
        bak.mkdir(exist_ok=True)
        if info:
            shutil.move(str(info["jar"]), str(bak / info["jar"].name))
            print(f"\n旧版已备份: {bak / info['jar'].name}")
        dest = inst / "mods" / f["filename"]
        req = urllib.request.Request(f["url"], headers=UA)
        with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as o:
            shutil.copyfileobj(r, o)
        print(f"已安装: {dest.name}  ({v['version_number']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
