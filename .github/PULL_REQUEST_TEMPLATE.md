## 改了什么

<!-- 一句话说清 -->

## 为什么

<!-- 关联 issue 号，或说明触发的真实故障 -->

## 证据

<!-- 日志行 / 审计输出 / 复现步骤。没有证据的改动不会被合并 -->

## 自检

- [ ] `python skill/mc-modpack-master/scripts/selftest.py` 通过
- [ ] `python expert/mc-modpack-expert/tools/verify_capability.py expert/mc-modpack-expert` 通过
- [ ] `diff -r skill/mc-modpack-master expert/mc-modpack-expert/skills/mc-modpack-master` 无差异
- [ ] 新增判据已写入 `references/pitfalls.md`（未实测的已标注「待验证」）
- [ ] 无个人绝对路径、无 `__pycache__`
