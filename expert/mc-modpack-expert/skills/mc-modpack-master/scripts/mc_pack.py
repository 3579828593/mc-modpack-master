#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mc_pack —— 材质包链路与贴图修复

三个子命令:
    --chain                     打印材质包优先级链、格式版本、覆盖包是否置顶
    --scan                      扫描非 2 次幂的 block/item 贴图（会压塌 mipmap 的那类）
    --build <输出zip> --from S   从来源（jar 或 zip，可多次）抽取 --scan 命中的贴图，
                                用 PotScale.java 补成 2 次幂后打成覆盖包

判定依据:
    只有 textures/block 与 textures/item 进地形/物品图集并生成 mipmap。
    合法尺寸 = 宽是 2 的幂，且（高是 2 的幂 或 高是宽的整数倍[动画条]）。
    带 .png.mcmeta 的一律跳过——帧尺寸写死，改分辨率会破坏动画布局。
"""
import argparse
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

POW2 = lambda n: n > 0 and (n & (n - 1)) == 0
RELEVANT = ("/textures/block/", "/textures/item/")


def enabled_packs(instance):
    opts = Path(instance) / "options.txt"
    try:
        for line in opts.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("resourcePacks:"):
                return json.loads(line.split(":", 1)[1])
    except Exception:
        pass
    return []


def chain(instance):
    inst = Path(instance)
    res = inst / "resourcepacks"
    packs = enabled_packs(inst)
    print(f"材质包链（低 → 高，共 {len(packs)} 项）\n")
    last_idx = len(packs) - 1
    for i, e in enumerate(packs):
        fmt, note = "—", ""
        if e.startswith("file/"):
            p = res / e[5:]
            if not p.exists():
                note = "  !! 文件不存在"
            else:
                try:
                    with zipfile.ZipFile(p) as z:
                        fmt = json.loads(z.read("pack.mcmeta").decode("utf-8-sig"))["pack"].get("pack_format")
                except Exception:
                    fmt = "unreadable"
        print(f"  {i:2d}  {e:44s} format={str(fmt):>10s}{note}")
    print(f"\n最顶层 = {packs[-1] if packs else '(空)'}")
    print("修复覆盖包必须位于最后一项，否则会被基础材质盖掉。")


def _coverage(instance):
    """收集覆盖包里已修复的贴图相对路径，避免重复修。"""
    cov = set()
    for pack in (Path(instance) / "resourcepacks").glob("*.zip"):
        if not any(k in pack.name for k in ("Fix", "fix", "Patch", "patch")):
            continue
        try:
            with zipfile.ZipFile(pack) as z:
                for n in z.namelist():
                    if n.lower().endswith(".png"):
                        cov.add(n.split("assets/", 1)[-1])
        except Exception:
            pass
    return cov


def scan(instance, show=40):
    inst = Path(instance)
    cov = _coverage(inst)
    hits = []
    for jar in sorted((inst / "mods").glob("*.jar")):
        hits += _scan_zip(jar)
    for e in enabled_packs(inst):
        if not e.startswith("file/"):
            continue
        p = inst / "resourcepacks" / e[5:]
        if p.exists():
            hits += _scan_zip(p)
    for h in hits:
        tail = h["texture"].split("assets/", 1)[-1]
        h["covered"] = any(c.endswith(tail) for c in cov)
    hits.sort(key=lambda x: (x["covered"], x["owner"], x["texture"]))
    todo = [h for h in hits if not h["covered"]]
    print(f"非 2 次幂 block/item 贴图: {len(hits)} 张，已覆盖 {len(hits)-len(todo)} 张，待修 {len(todo)} 张\n")
    for h in hits[:show]:
        mark = "已覆盖" if h["covered"] else "待修  "
        print(f"  [{mark}] {h['owner'][:28]:28s} {h['texture'].split('assets/')[-1]:48s} {h['size']:>9s} → {h['target']}")
    if len(hits) > show:
        print(f"  ... 其余 {len(hits)-show} 张")
    return todo


def _scan_zip(path):
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            for n in names:
                if not n.lower().endswith(".png") or not any(s in n for s in RELEVANT):
                    continue
                if (n + ".mcmeta") in names:
                    continue                       # 动画/CTM，跳过
                head = z.read(n)[:24]
                if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
                    continue
                w, h = struct.unpack(">II", head[16:24])
                if POW2(w) and (POW2(h) or h % w == 0):
                    continue
                out.append({"owner": path.name, "texture": n, "size": f"{w}x{h}",
                            "target": f"{_np(w)}x{_np(h)}"})
    except Exception:
        pass
    return out


def _np(v):
    p = 16
    while p < v:
        p <<= 1
    return p


def build(instance, sources, out_zip, hits):
    if not hits:
        print("没有需要修复的贴图。")
        return 1
    want = {}
    for h in hits:
        want.setdefault(h["texture"].split("assets/", 1)[-1], h["texture"])

    tmp = Path(tempfile.mkdtemp(prefix="mcpack_"))
    src_dir, dst_dir = tmp / "src", tmp / "dst"
    src_dir.mkdir(); dst_dir.mkdir()
    got = 0
    for src in sources:
        src = Path(src)
        if not src.exists():
            print(f"来源不存在: {src}")
            continue
        with zipfile.ZipFile(src) as z:
            names = set(z.namelist())
            for tail, full in want.items():
                real = full if full in names else next((n for n in names if n.endswith(tail)), None)
                if not real or (real + ".mcmeta") in names:
                    continue
                p = src_dir / tail
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(z.read(real))
                got += 1
    print(f"抽取 {got} 张，开始补 2 次幂...")

    java = shutil.which("java") or shutil.which("javac")
    if not java:
        print("未找到 java/javac，无法缩放。请手动运行 PotScale.java。")
        return 2
    here = Path(__file__).parent
    cls = tmp / "classes"
    cls.mkdir()
    subprocess.run(["javac", "-encoding", "UTF-8", "-d", str(cls), str(here / "PotScale.java")], check=True)
    subprocess.run(["java", "-cp", str(cls), "PotScale", str(src_dir), str(dst_dir)], check=True)

    out = Path(out_zip)
    meta = {"pack": {"pack_format": 34,
                     "description": "Auto fix: 非 2 次幂 block/item 贴图补正（mc_pack 生成）"}}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.mcmeta", json.dumps(meta, ensure_ascii=False, indent=2))
        n = 0
        for p in sorted(dst_dir.rglob("*.png")):
            z.write(p, p.relative_to(dst_dir).as_posix())
            n += 1
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n覆盖包已生成: {out}  ({n} 张)")
    print("记得把它加到 resourcePacks 的最后一项（最高优先级）。")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--chain", action="store_true")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--build", metavar="OUT_ZIP")
    ap.add_argument("--from", dest="sources", nargs="*", default=[])
    a = ap.parse_args()

    if a.chain:
        chain(a.instance)
        return 0
    if a.scan or a.build:
        hits = scan(a.instance)
        if a.build:
            if not a.sources:
                print("\n--build 需要 --from <jar|zip> ...")
                return 2
            return build(a.instance, a.sources, a.build, hits)
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
