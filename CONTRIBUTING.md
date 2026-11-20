# 贡献指南

这个项目的第一原则是 **可复核**。任何结论都要能指到证据，任何改动都要能被别人重跑一遍验证。

## 提 Issue 之前

1. 先跑 `python skill/mc-modpack-master/scripts/selftest.py`，确认是规则问题还是环境问题。
2. 再跑一次审计，把 `mc_audit` 生成的 JSON 摘要贴进 issue。
3. 如果是某个具体故障，附上：
   - MC 版本、加载器与版本、模组数量
   - 相关日志原始行（`grep` 出来的那种，不是截图）
   - 你验证过什么、排除了什么

**不要**只贴一张"游戏崩了"的截图——那没法定位。

## 提 PR 之前

```bash
python skill/mc-modpack-master/scripts/selftest.py
python expert/mc-modpack-expert/tools/verify_capability.py expert/mc-modpack-expert
diff -r skill/mc-modpack-master expert/mc-modpack-expert/skills/mc-modpack-master
```

三条都要过。第三条是硬性要求：`expert/` 里的技能副本必须与 `skill/` 完全一致，
否则专家包分发出去装的是旧版本。

## 新增检查项（`mc_audit.py`）

1. 写一个 `check_xxx(...)` 函数，返回结构化结果，**不要在里面直接打印**。
2. 在 `run()` 里调用它，并把结论并入 `findings`（severity 只有 `critical` / `warn` / `info` 三档）。
3. 在 `references/pitfalls.md` 补对应的「症状 / 判据 / 验证命令 / 修复」四段。
4. 用两个不同实例各跑一次，确认不会误报。
5. 版本号按语义化递增（新增检查项 = MINOR）。

**只读约束**：审计函数不得写入被审计目录。报告文件只能写到 `<实例>/mc_audit/`。

## 新增判据（`references/pitfalls.md`）

格式固定四段，缺一段不收：

```markdown
## N. 一句话症状

**症状**：用户会怎么描述这个现象。
**判据**：为什么是这个原因，判定的关键点是什么。
**验证**：可直接复制的命令或代码片段。
**修复**：最小介入的做法，以及不要做什么。
```

没实测过的写在文末「待验证」区，**不要混进已验证区**。这一条比格式更重要。

## 新增外部方案（`references/ecosystem.md`）

必须给出：

- 仓库地址或包名
- 实测日期
- 星数、最后推送日期、许可证（或 HTTP 状态码）
- 可信度等级（A 一手 / B 官方文档 / C 社区长文 / D 内容农场）
- **本项目的取舍**：采纳什么、丢弃什么、为什么

不可达的链接标 HTTP 状态码（如 `403`），不要写"大概能用"。

## 可信度分级（引用外部资料时强制）

| 级 | 是什么 | 能否作为结论依据 |
|---|---|---|
| A | 一手仓库 / 官方 API | 可以 |
| B | 官方文档站 | 可以 |
| C | 社区长文 / 实测记录 | 需与一手源交叉验证 |
| D | 内容农场 / "最佳 N 个"列表 | 不可以 |

识别 D 级的一个快招：把文章推荐的模组名批量丢给 Modrinth 的 `game_versions` 查询，
没有当前版本构建的直接划掉。曾经用这招在 30 秒内判定一篇《2026 最佳性能模组》不可信——
它推荐的 Phosphor / Starlight / LazyDFU 在 1.21.1 上一个构建都没有。

## 代码风格

- Python：仅标准库，3.9+，函数写类型无关的朴素实现（不引入 dataclass / typing 依赖）。
- 脚本必须能 `--help`，失败返回非 0 退出码。
- 中文注释可以，但标识符用英文。
- 不提交 `__pycache__`、报告产物、个人路径。

## 提交信息

```
<类型>: <一句话>

类型: feat / fix / docs / test / chore
```

例：`feat: 增加 Textures 图集尺寸越界检查`
