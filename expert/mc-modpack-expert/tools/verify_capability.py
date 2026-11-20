#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_capability —— 专家包能力可用性验收

回答一个问题：**封装出来的东西，智能体到底能不能发现、注册、调用？**
不是看文件在不在，而是逐条检查契约。

检查项：
    C1  plugin.json 结构合法（必填字段 / expertType / agentName 对应 MD 文件名）
    C2  agents[] 声明的 MD 全部存在，且 frontmatter name 与文件名一致
    C3  skills[] 声明的目录全部存在，SKILL.md 的 name 与目录名一致
    C4  plugin.json.skills 与 agent MD 的 skills 预加载列表一致（否则激活后不会预载）
    C5  已注册：marketplace.json 含该专家，且 version 与 plugin.json 一致
    C6  资源齐备：avatar 存在且 ≤500KB
    C7  脚本可执行：每个 .py 能通过语法编译
    C8  无残留 [TODO] 占位符

用法:
    python verify_capability.py <expert-dir> [--marketplace <marketplace.json>]
退出码 0 = 全通过；1 = 有失败项。
"""
import argparse
import json
import py_compile
import re
import sys
import tempfile
from pathlib import Path

OK, FAIL, WARN = "PASS", "FAIL", "WARN"


class Result:
    def __init__(self):
        self.rows = []

    def add(self, code, status, detail):
        self.rows.append((code, status, detail))

    def failed(self):
        return any(s == FAIL for _, s, _ in self.rows)


def read_front(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    return m.group(1) if m else ""


def fm_value(fm, key):
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", fm, re.M)
    return m.group(1).strip() if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("expert_dir")
    ap.add_argument("--marketplace", help="marketplace.json 路径，默认按标准位置推断")
    a = ap.parse_args()

    root = Path(a.expert_dir)
    r = Result()

    # ---------- C1 plugin.json ----------
    pj_path = root / ".codebuddy-plugin" / "plugin.json"
    if not pj_path.exists():
        r.add("C1", FAIL, "缺少 .codebuddy-plugin/plugin.json")
        return report(r)
    try:
        pj = json.loads(pj_path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        r.add("C1", FAIL, f"plugin.json 解析失败: {e}")
        return report(r)

    missing = [k for k in ("name", "version", "description", "expertType", "agentName",
                           "displayName", "profession", "displayDescription",
                           "categoryId", "tags", "quickPrompts") if k not in pj]
    if missing:
        r.add("C1", FAIL, f"缺字段: {missing}")
    elif pj["expertType"] not in ("agent", "team"):
        r.add("C1", FAIL, f"expertType 非法: {pj['expertType']}")
    elif len(pj.get("tags", [])) != 3 or len(pj.get("quickPrompts", [])) != 3:
        r.add("C1", FAIL, "tags/quickPrompts 必须各 3 个")
    elif pj["quickPrompts"][0] != pj.get("defaultInitPrompt"):
        r.add("C1", FAIL, "defaultInitPrompt 必须等于 quickPrompts[0]")
    else:
        r.add("C1", OK, f"结构合法 · v{pj['version']} · {pj['expertType']}")

    # ---------- C2 agents ----------
    agents = pj.get("agents") or []
    agent_names = set()
    if not agents:
        r.add("C2", FAIL, "agents[] 为空")
    else:
        bad = []
        for rel in agents:
            p = (root / rel).resolve()
            if not p.exists():
                bad.append(f"{rel} 不存在"); continue
            fm = read_front(p.read_text(encoding="utf-8"))
            nm = fm_value(fm, "name")
            if nm != p.stem:
                bad.append(f"{p.name} 的 name={nm} 与文件名不符")
            agent_names.add(p.stem)
        if pj.get("agentName") not in agent_names:
            bad.append(f"agentName={pj.get('agentName')} 不在 agents 中")
        r.add("C2", FAIL if bad else OK,
              "；".join(bad) if bad else f"agents {len(agents)} 个，name 与文件名一致")

    # ---------- C3 skills ----------
    skills = pj.get("skills") or []
    skill_names = set()
    if not skills:
        r.add("C3", WARN, "未声明 skills（专家将没有随包技能）")
    else:
        bad = []
        for rel in skills:
            d = (root / rel).resolve()
            sk = d / "SKILL.md"
            if not sk.exists():
                bad.append(f"{rel} 缺 SKILL.md"); continue
            fm = read_front(sk.read_text(encoding="utf-8"))
            nm = fm_value(fm, "name")
            if nm != d.name:
                bad.append(f"{d.name}: SKILL.md name={nm} 不一致")
            if not fm_value(fm, "description"):
                bad.append(f"{d.name}: 缺 description")
            skill_names.add(d.name)
        r.add("C3", FAIL if bad else OK,
              "；".join(bad) if bad else f"skills {len(skill_names)} 个，name 与目录一致")

    # ---------- C4 预加载一致性 ----------
    if skills and agents:
        bad = []
        for rel in agents:
            p = (root / rel).resolve()
            if not p.exists():
                continue
            fm = read_front(p.read_text(encoding="utf-8"))
            pre = fm_value(fm, "skills")
            if not pre:
                bad.append(f"{p.stem} 未声明 skills 预加载")
                continue
            declared = set(re.findall(r"[\w-]+", pre.strip("[]")))
            if not skill_names.issubset(declared) and skill_names:
                bad.append(f"{p.stem} 预加载 {sorted(declared)} 未覆盖 {sorted(skill_names)}")
        r.add("C4", FAIL if bad else OK,
              "；".join(bad) if bad else "agent 预加载与 plugin.json 一致")

    # ---------- C5 已注册 ----------
    mp = Path(a.marketplace) if a.marketplace else None
    if not mp:
        cand = root.parent.parent / ".codebuddy-plugin" / "marketplace.json"
        mp = cand if cand.exists() else None
    if not mp or not mp.exists():
        r.add("C5", WARN, "未找到 marketplace.json，无法核对注册状态")
    else:
        try:
            data = json.loads(mp.read_text(encoding="utf-8-sig"))
        except Exception as e:
            r.add("C5", FAIL, f"marketplace.json 解析失败: {e}")
            data = {}
        found = []

        def walk(o):
            if isinstance(o, dict):
                if o.get("name") == pj["name"]:
                    found.append(o)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(data)
        if not found:
            r.add("C5", FAIL, f"marketplace.json 中未注册 {pj['name']}")
        else:
            ent = found[0]
            ver = ent.get("version")
            if ver and ver != pj["version"]:
                r.add("C5", FAIL, f"注册版本 {ver} ≠ plugin.json {pj['version']}（需重新 register）")
            else:
                r.add("C5", OK, f"已注册 · v{ver or pj['version']} · {mp.name}")

    # ---------- C6 avatar ----------
    av = root / (pj.get("avatar") or "")
    if not pj.get("avatar") or not av.exists():
        r.add("C6", FAIL, f"头像缺失: {pj.get('avatar')}")
    else:
        kb = av.stat().st_size / 1024
        r.add("C6", OK if kb <= 500 else WARN,
              f"{av.name} {kb:.0f} KB" + ("" if kb <= 500 else "（超 500KB）"))

    # ---------- C7 脚本可编译 ----------
    pys = list(root.rglob("*.py"))
    bad = []
    for p in pys:
        try:
            py_compile.compile(str(p), cfile=str(Path(tempfile.gettempdir()) / "vc.pyc"),
                               doraise=True)
        except Exception as e:
            bad.append(f"{p.relative_to(root)}: {str(e)[:60]}")
    r.add("C7", FAIL if bad else OK,
          "；".join(bad) if bad else f"{len(pys)} 个脚本语法通过")

    # ---------- C8 TODO 残留 ----------
    todos = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in (".md", ".json"):
            try:
                if "[TODO" in p.read_text(encoding="utf-8", errors="ignore"):
                    todos.append(str(p.relative_to(root)))
            except Exception:
                pass
    r.add("C8", FAIL if todos else OK,
          f"残留占位符: {todos}" if todos else "无 [TODO] 残留")

    return report(r)


def report(r):
    width = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ "}
    print("能力可用性验收\n" + "=" * 62)
    for code, status, detail in r.rows:
        print(f"{width[status]} {code}  {detail}")
    print("=" * 62)
    n_fail = sum(1 for _, s, _ in r.rows if s == FAIL)
    n_warn = sum(1 for _, s, _ in r.rows if s == WARN)
    print(f"结果: {len(r.rows)} 项检查，失败 {n_fail}，警告 {n_warn}")
    if n_fail:
        print("结论: 存在阻断项，能力可能无法被发现或调用。")
        return 1
    print("结论: 可被智能体发现、注册、调用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
