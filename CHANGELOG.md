# 更新日志

遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.4.0] - 2026-11-20

### 新增
- `doubao/` 豆包 · 扣子开发交付包：人设提示词、5 份知识库文档、3 条 few-shot、
  可执行脚本、10 条上线验收清单。
- `02-知识库/04-审计输出解读.md`：把审计输出的 severity 与 JSON 字段讲清楚，
  供无执行能力的平台解读用户贴回的结果。
- `02-知识库/05-降级诊断手册.md`：七类症状的手工排查路径，解决"平台不能跑脚本"的缺口。

### 说明
- 专家包本身未改动，版本保持 1.3.0；本版只新增交付形态。

## [1.3.0] - 2026-11-20

### 新增
- `references/ecosystem.md` 第五节：公开站点调研与可信度分级（A/B/C/D 四级），
  含 8 个来源的 HTTP 可达性与采纳/丢弃结论。
- `scripts/selftest.py`：27 条确定性断言，覆盖贴图尺寸判定、版本约束解析、
  版本比较、资源路径归一化四个纯函数。
- 用 Modrinth 构建列表反证「过时方案」：Phosphor / Starlight / LazyDFU 在 1.21.1 上零构建。
- 专家包 `tools/verify_capability.py`：8 项契约验收（含 C4 预加载一致性）。

### 变更
- `SKILL.md` 增加「测试与验证」四层表与外部资料可信度过滤规则。
- 外部方案路由表明确让位边界：建包 → packwiz，服务端 → aiden，模组开发 → langyo。

### 修复
- `mc_audit.py` 覆盖包自身被当作待检对象，导致同一批贴图被重复计数（48 → 96）。
- 被审计实例缺失原版 jar 时，资源链检查会把 `minecraft:item/generated`
  等原版模型误报为缺失（曾出现 3.4 万条误报）。

## [1.2.0] - 2026-11-20

### 新增
- 专家包 `mc-modpack-expert`（Agent 型），含人格定义、能力边界、五步 SOP、自检清单。
- 生态分工表写入 Agent MD，避免"为了看起来什么都能做"而重写 packwiz 或开服脚本。

## [1.1.0] - 2026-11-20

### 新增
- `references/ecosystem.md`：packwiz、minecraft-mod-mcp、mc-pack-builder-mcp、
  aiden server skill、mc-agent-mcp、minecraftmcp 的实测状态与分工决策表。
- 标注 `javimosch/packrinth` 在 GitHub 返回 Not Found，不采纳。

## [1.0.0] - 2026-11-20

### 新增
- 技能 `mc-modpack-master`：铁律七条、五步流程、症状判定表、十四类故障判据。
- `mc_audit.py`：八类只读审计（重复模组 / 已知冲突 / 材质链 / mipmap /
  动画栈 / 资源链 / 模型损坏 / 配置越界与日志归因）。
- `mc_version_check.py`：下载候选 jar 读 `fabric.mod.json`，逐条比对 `depends` 区间。
- `mc_pack.py` + `PotScale.java`：材质链解析、非 2 次幂扫描、覆盖包构建。
