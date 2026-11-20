#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mc_audit —— Minecraft 整合包只读审计

用法:
    python mc_audit.py --instance "<实例目录>"
    python mc_audit.py --instance ... --html            # 额外输出 HTML 报告
    python mc_audit.py --instance ... --vanilla "<原版 jar 路径>"

设计约束:
    1. 只读。除报告文件外不改动任何游戏文件。
    2. 每条结论都带证据（文件路径 / 原始行 / 计数）。
    3. 不猜版本兼容性——只比对实际读到的元数据。

零第三方依赖。
"""
import argparse
import json
import os
import re
import struct
import sys
import time
import zipfile
from pathlib import Path

# 跨平台输出：Windows 控制台默认 cp1252/gbk，打印中文会 UnicodeEncodeError
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------- 常量

POW2 = lambda n: n > 0 and (n & (n - 1)) == 0

# 只有这两类进地形/物品图集并生成 mipmap，检查其它目录全是噪音
MIPMAP_RELEVANT = ("/textures/block/", "/textures/item/")

# 已知会互相打架的组合
KNOWN_CONFLICTS = [
    (("voxy", "iris"), "Voxy 与 Iris 的地形管线互相递归，表现是区块不加载 + 帧率崩塌", "critical"),
    (("continuity", "skniro_furniture"), "Continuity 的 1x1 保留贴图会把方块图集 mipmap 压到 0", "warn"),
]

ANIMATION_CORE = ["entity_model_features", "entity_texture_features"]

# options.txt 合法区间（越界会被静默忽略，实际跑默认值）
LIMITS = {
    "renderDistance": (2, 32),
    "simulationDistance": (5, 32),
    "mipmapLevels": (0, 4),
    "guiScale": (0, 8),
    "maxFps": (10, 260),
    "biomeBlendRadius": (0, 7),
    "particles": (0, 2),
}


# ---------------------------------------------------------------- 工具

def read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def read_kv(p, sep=":"):
    out = {}
    for line in read_text(p).splitlines():
        if sep in line and not line.lstrip().startswith("#"):
            k, v = line.split(sep, 1)
            out[k.strip()] = v.strip()
    return out


def scan_mods(folder):
    """{modid: [记录]} + 读取失败的 jar 列表。"""
    by_id, broken = {}, []
    if not folder.exists():
        return by_id, broken
    for jar in sorted(folder.glob("*.jar")):
        try:
            with zipfile.ZipFile(jar) as z:
                if "fabric.mod.json" not in z.namelist():
                    broken.append({"jar": jar.name, "reason": "缺少 fabric.mod.json（Fabric 不会加载）"})
                    continue
                raw = z.read("fabric.mod.json").decode("utf-8", errors="replace")
                try:
                    meta = json.loads(raw)
                except Exception:
                    meta = json.loads(re.sub(r"[\x00-\x1f]", " ", raw))
        except Exception as e:
            broken.append({"jar": jar.name, "reason": f"读取失败: {e}"})
            continue
        mid = meta.get("id") or "?"
        by_id.setdefault(mid, []).append({
            "id": mid,
            "version": str(meta.get("version", "?")),
            "name": meta.get("name", mid),
            "jar": jar.name,
            "depends": meta.get("depends") or {},
        })
    return by_id, broken


def detect_vanilla(instance):
    """版本隔离的实例目录里没有客户端 jar，去共享 versions 目录找。"""
    for parent in [instance.parent, Path(os.environ.get("APPDATA", "")) / ".minecraft" / "versions"]:
        if not parent.exists():
            continue
        cands = sorted(parent.glob("*/*.jar"), key=lambda p: -p.stat().st_size)
        for c in cands:
            if c.parent == instance:
                continue
            if c.stat().st_size > 5 * 1024 * 1024:   # 客户端 jar 至少几 MB
                return c
    return None


# ---------------------------------------------------------------- 检查

def check_duplicates(by_id):
    dup = {k: v for k, v in by_id.items() if len(v) > 1}
    return {"duplicates": dup, "duplicate_count": len(dup),
            "unique_mods": len(by_id), "jar_count": sum(len(v) for v in by_id.values())}


def check_conflicts(by_id):
    hits = []
    for ids, desc, sev in KNOWN_CONFLICTS:
        if all(i in by_id for i in ids):
            hits.append({"mods": list(ids), "reason": desc, "severity": sev})
    return hits


def build_pack_entries(instance, packs):
    res = instance / "resourcepacks"
    out, missing = [], []
    for i, e in enumerate(packs):
        rec = {"index": i, "entry": e, "format": None, "description": None}
        if e.startswith("file/"):
            p = res / e[5:]
            if not p.exists():
                missing.append(e)
            else:
                rec["path"] = str(p)
                try:
                    with zipfile.ZipFile(p) as z:
                        meta = json.loads(z.read("pack.mcmeta").decode("utf-8-sig")).get("pack", {})
                    rec["format"] = meta.get("pack_format")
                    rec["description"] = meta.get("description")
                except Exception:
                    rec["format"] = "unreadable"
        out.append(rec)
    return out, missing


def iter_png(zpath):
    """产出 (内部名, 宽, 高, 是否有 .mcmeta)。"""
    try:
        with zipfile.ZipFile(zpath) as z:
            names = set(z.namelist())
            for n in names:
                if not n.lower().endswith(".png") or "/textures/" not in n:
                    continue
                head = z.read(n)[:24]
                if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n":
                    w, h = struct.unpack(">II", head[16:24])
                    yield n, w, h, (n + ".mcmeta") in names
    except Exception:
        return


def mip_safe(w, h):
    return POW2(w) and (POW2(h) or h % w == 0)


def check_mipmap(instance, mods_dir, enabled_packs):
    covered = set()
    for pack in (instance / "resourcepacks").glob("*.zip"):
        if any(k in pack.name for k in ("Fix", "fix", "Patch", "patch")):
            try:
                with zipfile.ZipFile(pack) as z:
                    for n in z.namelist():
                        if n.lower().endswith(".png"):
                            covered.add(n.split("assets/", 1)[-1])
            except Exception:
                pass
    res = {"blocking": [], "deferred": [], "covered": [], "undersized": []}

    def consider(owner, name, w, h, mc):
        if not any(s in name for s in MIPMAP_RELEVANT):
            return
        tail = name.split("assets/", 1)[-1] if "assets/" in name else name
        rec = {"owner": owner, "texture": name, "size": f"{w}x{h}"}
        if any(c.endswith(tail) for c in covered):
            res["covered"].append(rec)
        elif not mip_safe(w, h):
            (res["deferred"] if mc else res["blocking"]).append(rec)
        elif min(w, h) < 16:
            res["undersized"].append(rec)

    for jar in sorted(mods_dir.glob("*.jar")):
        for n, w, h, mc in iter_png(jar):
            consider(jar.name, n, w, h, mc)
    for name in enabled_packs:
        if any(k in name for k in ("Fix", "fix", "Patch", "patch")):
            continue                      # 覆盖包本身不含"待修"贴图，跳过避免重复计数
        p = instance / "resourcepacks" / name
        if not p.exists():
            continue
        for n, w, h, mc in iter_png(p):
            consider(name, n, w, h, mc)

    for k in list(res):
        seen, uniq = set(), []
        for it in res[k]:
            key = (it["owner"], it["texture"])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(it)
        res[k] = uniq
        res[k + "_count"] = len(uniq)
    return res


def check_animation(by_id, packs, config):
    facts, problems = {}, []
    for m in ANIMATION_CORE:
        facts[m] = by_id[m][0]["version"] if m in by_id else None
        if m not in by_id:
            problems.append(("critical", f"动画基础模组缺失：{m}",
                             "FreshAnimations 这类 .jem 动画必须由 EMF(模型)+ETF(纹理) 支撑，缺一个就不会有动作。"))

    fa = [p for p in packs if "FreshAnimations" in p or "FreshAnimations" in p]
    facts["fresh_animations_packs"] = fa
    if not fa:
        problems.append(("critical", "FreshAnimations 材质包未启用",
                         "mods 里有 EMF/ETF，但 resourcePacks 不含 FreshAnimations，等于没有动画数据。"))

    emf = {}
    p = config / "entity_model_features.json"
    if p.exists():
        try:
            emf = json.loads(read_text(p))
        except Exception:
            emf = {}
    facts["emf"] = {k: emf.get(k) for k in ("allowedCEM", "animationLODDistance",
                                           "modelsNamesDisabled", "onlyClientPlayerModel")}
    if emf.get("allowedCEM") not in (None, "ALL"):
        problems.append(("critical", "EMF 只允许部分 CEM 模型",
                         f"allowedCEM = {emf.get('allowedCEM')}，大量 .jem 模型会被跳过。"))
    lod = emf.get("animationLODDistance")
    if isinstance(lod, (int, float)) and lod < 8:
        problems.append(("warn", "动画 LOD 距离过短", f"animationLODDistance = {lod} 格"))

    punchy = {}
    pc = config / "punchy" / "punchy_config.json"
    if pc.exists():
        try:
            punchy = json.loads(read_text(pc))
        except Exception:
            punchy = {}
    facts["punchy"] = {k: punchy.get(k) for k in ("enableMod", "animationSpeed")} if punchy else None
    if punchy and punchy.get("enableMod") is not False:
        if not any(p.startswith("punchy:") for p in packs):
            problems.append(("critical", "Punchy 开着但动画资源包没启用",
                             "resourcePacks 里没有 punchy:punchy。Punchy 只装本体不带数据时，"
                             "第一人称动作全部失效，游戏内会弹 RESOURCE PACK DISABLED。"))
    return {"facts": facts, "problems": problems}


def check_options(options):
    out = []
    for key, (lo, hi) in LIMITS.items():
        if key not in options:
            continue
        try:
            v = int(options[key])
        except ValueError:
            out.append(("warn", f"{key} 非整数", f"{key} = {options[key]}")); continue
        if not lo <= v <= hi:
            out.append(("critical", f"{key} 越界会被静默忽略",
                        f"{key} = {v}，合法区间 {lo}~{hi}，实际仍跑默认值。"))
    return out


def check_treechop(by_id, config):
    if "treechop" not in by_id:
        return {"installed": False, "facts": {}, "problems": []}
    c = read_text(config / "treechop-client.toml")
    cm = read_text(config / "treechop-common.toml")

    def grab(t, k):
        m = re.search(rf"^\s*{re.escape(k)}\s*=\s*(.+)$", t, re.M)
        return m.group(1).strip() if m else None

    facts = {"version": by_id["treechop"][0]["version"],
             "choppingEnabled": grab(c, "choppingEnabled"),
             "sneakBehavior": grab(c, "sneakBehavior"),
             "treesMustHaveLeaves": grab(c, "treesMustHaveLeaves"),
             "chopInCreativeMode": grab(c, "chopInCreativeMode"),
             "requiresCorrectTool": grab(cm, "choppingRequiresCorrectToolForDrops")}
    probs = []
    if facts["choppingEnabled"] == "false":
        probs.append(("critical", "TreeChop 总开关关闭", "choppingEnabled = false"))
    if facts["sneakBehavior"] == '"INVERT_CHOPPING"':
        probs.append(("warn", "潜行会关闭砍树", 'sneakBehavior = "INVERT_CHOPPING"'))
    if facts["treesMustHaveLeaves"] == "true":
        probs.append(("warn", "要求树必须有可识别树叶",
                      "模组树的树叶不在 #minecraft:leaves 标签里时，整棵树判定为无叶，砍了不倒。"))
    if facts["requiresCorrectTool"] == "true":
        probs.append(("warn", "必须正确工具才砍",
                      "模组原木声明工具需求时，空手或错误工具不触发整棵砍伐。"))
    return {"installed": True, "facts": facts, "problems": probs}


def check_assets(instance, mods_dir, enabled_packs, vanilla):
    """blockstate → model → parent 全链路，外加模型字段损坏检测。"""
    jars = list(sorted(mods_dir.glob("*.jar")))
    if vanilla and vanilla.exists():
        jars.append(vanilla)
    packs = [instance / "resourcepacks" / n for n in enabled_packs
             if (instance / "resourcepacks" / n).exists()]

    models, blockstates = set(), set()
    blobs = []

    def key_of(n, folder):
        rest = n[len("assets/"):]
        if "/" not in rest:
            return None
        ns, tail = rest.split("/", 1)
        pre = folder + "/"
        return ns + ":" + tail[len(pre):-len(".json")] if tail.startswith(pre) else None

    for src in jars + packs:
        try:
            with zipfile.ZipFile(src) as z:
                for n in z.namelist():
                    if not n.startswith("assets/") or not n.endswith(".json"):
                        continue
                    try:
                        data = z.read(n)
                    except Exception:
                        continue
                    blobs.append((src.name, n, data))
                    if "/models/" in n:
                        k = key_of(n, "models")
                        if k:
                            models.add(k)
                    elif "/blockstates/" in n:
                        k = key_of(n, "blockstates")
                        if k:
                            blockstates.add(k)
        except Exception:
            continue

    def norm(ref):
        if not isinstance(ref, str) or ref.startswith("builtin/"):
            return None
        if ":" not in ref:
            ref = "minecraft:" + ref
        ref = ref.split("[")[0]
        return None if ref in ("minecraft:builtin/entity", "minecraft:builtin/generated") else ref

    missing_models, missing_parents, malformed = {}, {}, []
    for label, n, data in blobs:
        try:
            js = json.loads(data.decode("utf-8-sig"))
        except Exception:
            if "/models/" in n:
                malformed.append({"file": f"{label}:{n}", "reason": "JSON 解析失败"})
            continue
        if "/blockstates/" in n:
            refs = []

            def walk(node):
                if isinstance(node, dict):
                    for k, v in node.items():
                        refs.append(v) if k == "model" else walk(v)
                elif isinstance(node, list):
                    for v in node:
                        walk(v)
            walk(js)
            for r in refs:
                k = norm(r)
                if k and k not in models:
                    missing_models.setdefault(k, set()).add(f"{label}:{n}")
        elif "/models/" in n:
            p = norm(js.get("parent"))
            if p and p not in models:
                missing_parents.setdefault(p, set()).add(f"{label}:{n}")
            tex = js.get("textures")
            if tex is not None and not isinstance(tex, dict):
                malformed.append({"file": f"{label}:{n}", "reason": "textures 不是对象"})
                continue
            bad = 0
            for el in js.get("elements") or []:
                if not isinstance(el, dict):
                    bad += 1; continue
                for spec in (el.get("faces") or {}).values():
                    if not isinstance(spec, dict) or not isinstance(spec.get("texture"), str):
                        bad += 1
            if bad:
                malformed.append({"file": f"{label}:{n}", "reason": f"{bad} 个 face 缺 texture"})

    def summ(d, top=15):
        items = sorted(d.items(), key=lambda kv: -len(kv[1]))
        return {"count": len(items), "refs": sum(len(v) for v in d.values()),
                "top": [{"missing": k, "by": sorted(v)[:2], "n": len(v)} for k, v in items[:top]]}

    return {"models": len(models), "blockstates": len(blockstates),
            "missing_models": summ(missing_models), "missing_parents": summ(missing_parents),
            "malformed": {"count": len(malformed), "items": malformed[:20]}}


MIXIN_MISS = re.compile(r"@Mixin target (?P<t>[\w./$]+) was not found .*? from mod (?P<m>[\w-]+)")


def check_log(instance, by_id):
    p = instance / "logs" / "latest.log"
    if not p.exists():
        return {"available": False}
    lines = read_text(p).splitlines()
    mixin, errors = [], {}
    for i, line in enumerate(lines):
        m = MIXIN_MISS.search(line)
        if m and m.group("m") in by_id:
            mixin.append({"line": i + 1, "mod": m.group("m"), "target": m.group("t")})
        if "/ERROR]" in line:
            msg = line.split("]:", 1)[-1].strip()[:110]
            errors[msg] = errors.get(msg, 0) + 1
    return {"available": True, "lines": len(lines),
            "mixin_misses": mixin[:20], "mixin_miss_count": len(mixin),
            "top_errors": [{"msg": k, "n": v} for k, v in
                           sorted(errors.items(), key=lambda kv: -kv[1])[:8]]}


# ---------------------------------------------------------------- 主流程

def run(instance, vanilla=None, html=False):
    instance = Path(instance)
    mods_dir = instance / "mods"
    config = instance / "config"
    options = read_kv(instance / "options.txt", ":")

    by_id, broken = scan_mods(mods_dir)
    dup = check_duplicates(by_id)
    conflicts = check_conflicts(by_id)

    try:
        packs = json.loads(options.get("resourcePacks", "[]"))
    except Exception:
        packs = []
    pack_entries, missing_packs = build_pack_entries(instance, packs)
    enabled_names = [e[5:] for e in packs if e.startswith("file/")]

    vanilla = Path(vanilla) if vanilla else detect_vanilla(instance)

    mip = check_mipmap(instance, mods_dir, enabled_names)
    anim = check_animation(by_id, packs, config)
    tree = check_treechop(by_id, config)
    assets = check_assets(instance, mods_dir, enabled_names, vanilla)
    log = check_log(instance, by_id)

    findings = []

    def add(sev, title, detail):
        findings.append({"severity": sev, "title": title, "detail": detail})

    for c in conflicts:
        add(c["severity"], "已知模组冲突", f"{' + '.join(c['mods'])}：{c['reason']}")
    for mid, recs in dup["duplicates"].items():
        add("critical", f"重复模组 id：{mid}",
            "；".join(f"{r['jar']} ({r['version']})" for r in recs) + " —— 注册表会互相覆盖。")
    if broken:
        add("info", "不会被加载的 jar",
            "；".join(f"{b['jar']}（{b['reason']}）" for b in broken))
    if missing_packs:
        add("critical", "材质包条目指向不存在的文件",
            "；".join(missing_packs) + " —— 游戏静默跳过，表现为材质不生效。")
    for sev, t, d in anim["problems"]:
        add(sev, t, d)
    for sev, t, d in check_options(options):
        add(sev, t, d)
    for sev, t, d in tree["problems"]:
        add(sev, t, d)
    if mip.get("blocking_count"):
        add("critical", f"{mip['blocking_count']} 张贴图会压塌 mipmap 且未被覆盖",
            "；".join(f"{x['texture'].split('/')[-1]} ({x['size']})" for x in mip["blocking"][:4]))
    if mip.get("deferred_count"):
        add("info", f"{mip['deferred_count']} 张非 2 次幂贴图带 .mcmeta，保留原尺寸",
            "动画/CTM 帧尺寸写死在元数据里，改分辨率会破坏帧布局。")
    if mip.get("covered_count"):
        add("info", f"{mip['covered_count']} 张异常贴图已被覆盖包修复", "模组 jar 内仍是原尺寸，运行时被覆盖。")
    if assets["missing_models"]["count"]:
        mm = assets["missing_models"]
        add("critical", f"{mm['count']} 个模型被引用但不存在",
            "；".join(f"{t['missing']} ← {t['by'][0]}" for t in mm["top"][:3]))
    if assets["missing_parents"]["count"]:
        mp = assets["missing_parents"]
        add("warn", f"{mp['count']} 个模型 parent 缺失",
            "；".join(t["missing"] for t in mp["top"][:4]))
    if assets["malformed"]["count"]:
        add("info", f"{assets['malformed']['count']} 个模型字段写坏",
            "；".join(f"{i['file'].split(':')[-1]}（{i['reason']}）" for i in assets["malformed"]["items"][:3]))
    if log.get("mixin_miss_count"):
        add("warn", f"{log['mixin_miss_count']} 处 mixin 目标缺失",
            "；".join(f"{m['mod']}→{m['target'].split('/')[-1]}" for m in log["mixin_misses"][:4]))
    if log.get("top_errors"):
        add("info", "日志错误聚合",
            "；".join(f"{e['msg'][:60]} ×{e['n']}" for e in log["top_errors"][:4]))

    order = {"critical": 0, "warn": 1, "info": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "instance": str(instance),
        "vanilla_jar": str(vanilla) if vanilla else None,
        "summary": {"mods": dup["unique_mods"], "jars": dup["jar_count"],
                    "packs": len(packs),
                    "critical": sum(1 for f in findings if f["severity"] == "critical"),
                    "warn": sum(1 for f in findings if f["severity"] == "warn"),
                    "info": sum(1 for f in findings if f["severity"] == "info")},
        "findings": findings,
        "details": {"mipmap": mip, "animation": anim, "treechop": tree,
                    "assets": assets, "log": log, "pack_entries": pack_entries,
                    "options": {k: options.get(k) for k in list(LIMITS) + ["fullscreen", "graphicsMode", "ao"]}},
    }

    out_dir = instance / "mc_audit"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    jp = out_dir / f"audit_{stamp}.json"
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_json"] = str(jp)

    if html:
        hp = out_dir / f"audit_{stamp}.html"
        hp.write_text(render_html(report), encoding="utf-8")
        report["report_html"] = str(hp)
    return report


def render_html(r):
    color = {"critical": "#b91c1c", "warn": "#a16207", "info": "#1d4ed8"}
    rows = "".join(
        f'<div class="f"><span class="tag" style="background:{color.get(f["severity"],"#555")}">'
        f'{f["severity"]}</span><b>{f["title"]}</b><p>{f["detail"]}</p></div>'
        for f in r["findings"])
    s = r["summary"]
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>整合包审计 {r['generated_at']}</title>
<style>body{{font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
max-width:960px;margin:40px auto;padding:0 24px;color:#1a202c}}
h1{{font-size:25px;margin:0 0 4px}}.meta{{color:#6b7280;font-size:13px;margin-bottom:22px}}
.cards{{display:flex;gap:10px;margin:18px 0 26px;flex-wrap:wrap}}
.card{{flex:1 1 120px;border:1px solid #e5e7eb;border-radius:9px;padding:12px 14px;background:#fafafa}}
.card b{{display:block;font-size:22px}}.card span{{color:#6b7280;font-size:11.5px}}
.f{{border-left:3px solid #e5e7eb;padding:8px 0 8px 14px;margin:10px 0}}
.tag{{display:inline-block;color:#fff;font-size:11px;padding:1px 7px;border-radius:9px;margin-right:8px}}
.f p{{margin:4px 0 0;color:#4b5563;font-size:13.5px}}
h2{{font-size:17px;margin:30px 0 8px;border-bottom:1px solid #e5e7eb;padding-bottom:6px}}
pre{{background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;padding:12px;font-size:12.5px;overflow:auto}}
</style>
<h1>整合包审计报告</h1>
<div class="meta">{r['instance']} · {r['generated_at']} · 原版索引 {r['vanilla_jar'] or '未找到'}</div>
<div class="cards">
<div class="card"><b>{s['jars']}</b><span>启用 jar</span></div>
<div class="card"><b>{s['mods']}</b><span>唯一模组</span></div>
<div class="card"><b>{s['packs']}</b><span>材质包</span></div>
<div class="card"><b style="color:#b91c1c">{s['critical']}</b><span>严重</span></div>
<div class="card"><b style="color:#a16207">{s['warn']}</b><span>隐患</span></div>
</div>
<h2>问题清单</h2>{rows or '<p>无。</p>'}
<h2>动画栈</h2><pre>{json.dumps(r['details']['animation']['facts'], ensure_ascii=False, indent=1)}</pre>
<h2>材质链</h2><pre>{json.dumps(r['details']['pack_entries'], ensure_ascii=False, indent=1)}</pre>
</html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True, help="整合包实例目录")
    ap.add_argument("--vanilla", help="原版客户端 jar（默认自动探测）")
    ap.add_argument("--html", action="store_true", help="额外输出 HTML 报告")
    ap.add_argument("--full", action="store_true", help="打印完整 JSON")
    a = ap.parse_args()

    rep = run(a.instance, a.vanilla, a.html)
    if a.full:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        s = rep["summary"]
        print(f"实例 {rep['instance']}")
        print(f"模组 {s['mods']} / jar {s['jars']} / 材质包 {s['packs']}")
        print(f"严重 {s['critical']} · 隐患 {s['warn']} · 记录 {s['info']}\n")
        for f in rep["findings"]:
            print(f"[{f['severity'].upper():8s}] {f['title']}")
            print(f"           {f['detail']}")
        print(f"\nJSON: {rep['report_json']}")
        if rep.get("report_html"):
            print(f"HTML: {rep['report_html']}")
    return 0 if rep["summary"]["critical"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
