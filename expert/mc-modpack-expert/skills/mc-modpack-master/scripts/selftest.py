#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest —— 核心判定规则的确定性断言测试

为什么需要：审计脚本的结论全建立在几个纯函数上（贴图尺寸判定、版本约束判定、版本比较）。
这些函数一旦写错，报告会整篇误报，而且"看起来很正常"。所以用固定用例把它们钉死。

跑法：
    python selftest.py            # 全部用例
    python selftest.py -v         # 打印每条用例

退出码 0 = 全部通过；1 = 有用例失败。
覆盖：
    T1 贴图 mipmap 合法性判定（含动画条、非 2 次幂、过小）
    T2 版本约束解析（>=, =, <, ~, ^, 区间）
    T3 版本比较（1.21 vs 1.21.1 不能相等）
    T4 资源路径归一化（assets/<ns>/models/<path>.json → <ns>:<path>）
"""
import sys

# ---- 被测函数（与 mc_audit.py / mc_version_check.py 保持同源实现）----

POW2 = lambda n: n > 0 and (n & (n - 1)) == 0


def mip_safe(w, h):
    """宽必须是 2 的幂；高是 2 的幂，或是宽的整数倍（动画条）。"""
    return POW2(w) and (POW2(h) or h % w == 0)


def asset_key(path, folder):
    rest = path[len("assets/"):]
    if "/" not in rest:
        return None
    ns, tail = rest.split("/", 1)
    pre = folder + "/"
    return ns + ":" + tail[len(pre):-len(".json")] if tail.startswith(pre) else None


def _nums(v):
    import re
    return [int(x) for x in re.findall(r"\d+", str(v))[:4]]


def cmp_ver(a, b):
    na, nb = _nums(a), _nums(b)
    n = max(len(na), len(nb))
    na += [0] * (n - len(na))
    nb += [0] * (n - len(nb))
    return (na > nb) - (na < nb)


def satisfies(installed, constraint):
    import re
    if not constraint or constraint.strip() in ("*", ""):
        return True
    for part in constraint.split():
        m = re.match(r"^(>=|<=|>|<|=|~|\^)?\s*(.+)$", part)
        if not m:
            continue
        op, ver = m.group(1) or "=", m.group(2).strip()
        c = cmp_ver(installed, ver)
        ok = {"=": c == 0, ">=": c >= 0, ">": c > 0, "<=": c <= 0, "<": c < 0,
              "~": c >= 0 and _nums(installed)[:2] == _nums(ver)[:2],
              "^": c >= 0 and _nums(installed)[:1] == _nums(ver)[:1]}.get(op, True)
        if not ok:
            return False
    return True


# ---- 用例 ----

CASES = [
    # T1 贴图尺寸
    ("T1", "16x16 原版方块", lambda: mip_safe(16, 16) is True),
    ("T1", "32x32 高清", lambda: mip_safe(32, 32) is True),
    ("T1", "16x48 动画条（合法）", lambda: mip_safe(16, 48) is True),
    ("T1", "32x96 动画条（合法）", lambda: mip_safe(32, 96) is True),
    ("T1", "48x48 非 2 次幂（应判非法）", lambda: mip_safe(48, 48) is False),
    ("T1", "96x96 非 2 次幂", lambda: mip_safe(96, 96) is False),
    ("T1", "24x24 非 2 次幂", lambda: mip_safe(24, 24) is False),
    ("T1", "48x16 宽非 2 次幂", lambda: mip_safe(48, 16) is False),
    ("T1", "15x15 奇数", lambda: mip_safe(15, 15) is False),
    ("T1", "8x8 合法但过小（另由 undersized 规则处理）", lambda: mip_safe(8, 8) is True),

    # T2 版本约束
    ("T2", "sodium 0.6.13 满足 >=0.6.5", lambda: satisfies("0.6.13+mc1.21.1", ">=0.6.5") is True),
    ("T2", "sodium 0.6.13 不满足 =0.8.13", lambda: satisfies("0.6.13+mc1.21.1", "=0.8.13+mc1.21.1") is False),
    ("T2", "sodium 0.6.13 不满足 >=0.8.12", lambda: satisfies("0.6.13+mc1.21.1", ">=0.8.12") is False),
    ("T2", "iris 1.8.8 满足 <1.8.7? 否", lambda: satisfies("1.8.8+mc1.21.1", "<1.8.7") is False),
    ("T2", "sodium-extra 0.6.0 满足 >=0.6.0", lambda: satisfies("0.6.0+mc1.21.1", ">=0.6.0") is True),
    ("T2", "区间 '>=1.0 <2.0' 对 1.5 成立", lambda: satisfies("1.5", ">=1.0 <2.0") is True),
    ("T2", "区间 '>=1.0 <2.0' 对 2.1 不成立", lambda: satisfies("2.1", ">=1.0 <2.0") is False),
    ("T2", "通配 * 恒成立", lambda: satisfies("9.9.9", "*") is True),
    ("T2", "~1.21.1 对 1.21.5 成立", lambda: satisfies("1.21.5", "~1.21.1") is True),
    ("T2", "~1.21.1 对 1.22.0 不成立", lambda: satisfies("1.22.0", "~1.21.1") is False),

    # T3 版本比较
    ("T3", "1.21 < 1.21.1", lambda: cmp_ver("1.21", "1.21.1") < 0),
    ("T3", "1.21.1 == 1.21.1", lambda: cmp_ver("1.21.1", "1.21.1") == 0),
    ("T3", "1.9 < 1.10（按数值不按字典）", lambda: cmp_ver("1.9", "1.10") < 0),
    ("T3", "1.2.31 < 1.3.7", lambda: cmp_ver("1.2.31", "1.3.7") < 0),

    # T4 资源路径
    ("T4", "models 路径归一化",
     lambda: asset_key("assets/minecraft/models/block/stone.json", "models") == "minecraft:block/stone"),
    ("T4", "blockstates 路径归一化",
     lambda: asset_key("assets/yuushya/blockstates/oak_door.json", "blockstates") == "yuushya:oak_door"),
    ("T4", "目录不匹配返回 None",
     lambda: asset_key("assets/x/models/a/b.json", "blockstates") is None),
]


def main():
    verbose = "-v" in sys.argv
    failed = []
    for group, name, fn in CASES:
        try:
            ok = bool(fn())
        except Exception as e:
            ok = False
            name = f"{name}（抛异常: {e}）"
        if verbose or not ok:
            print(f"{'PASS' if ok else 'FAIL'}  [{group}] {name}")
        if not ok:
            failed.append((group, name))

    print("=" * 58)
    print(f"用例 {len(CASES)} 条，失败 {len(failed)} 条")
    if failed:
        for g, n in failed:
            print(f"  ✗ [{g}] {n}")
        return 1
    print("全部通过：核心判定规则行为符合预期。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
