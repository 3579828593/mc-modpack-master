# mc-modpack-master

**Minecraft 整合包诊断与治理** —— 只管「为什么不生效 / 为什么崩 / 为什么糊 / 为什么卡」，以及改之前怎么证明该改。

一个给 AI Agent 用的技能（Agent Skill）+ 一个专家包（Expert Package）。核心是一条纪律：
**每条结论必须能指到具体文件、日志行或数字；指不出来就不说。**

```
定位实例 → 只读审计 → 症状归因 → 最小介入修复 → 实测验证 → 五段式结论
```

---

## 它解决什么

| 现象 | 常见误判 | 本项目的做法 |
|---|---|---|
| 第一人称动作全没了 | 以为模组坏了 | 先查动画**资源包**是否启用——模组本体在 ≠ 动画数据在 |
| 手持火把不照亮 | 以为配置写错 | 先查有没有动态光源模组——功能不存在，不是参数问题 |
| 方块透明 / 紫黑 | 以为材质包太旧 | `blockstate → model → parent` 全链路解析，定位到具体缺失文件 |
| 画面整体发糊 | 调画质参数 | 查非 2 次幂贴图导致的 mipmap 塌陷（48×48 是常见元凶） |
| 升级模组后启动崩 | 以为版本号不对 | 下载候选 jar 读 `depends` 区间比对本地已装版本 |

## 它不做什么

- 不写模组代码、不反编译、不改模组 jar
- 不替用户决定存档取舍（删世界 / 回滚进度）
- 不承诺"必然提升 N 帧"，只给实测数字
- **不做整合包制作与分发** —— 用 [packwiz](https://github.com/packwiz/packwiz)
- **不做服务端搭建** —— 用 [aiden 的 minecraft-modpack-server](https://github.com/taracodlabs/aiden)
- **不做模组开发** —— 用 [langyo/minecraft-mod-mcp](https://github.com/langyo/minecraft-mod-mcp)

详见 [`skill/mc-modpack-master/references/ecosystem.md`](skill/mc-modpack-master/references/ecosystem.md)，
里面有每个外部方案的实测星数、最后推送日期与 HTTP 可达性。

---

## 快速开始

要求 **Python 3.9+**，零第三方依赖（仅标准库）。

```bash
# 1. 验证判定规则正常
python skill/mc-modpack-master/scripts/selftest.py

# 2. 审计一个整合包实例（只读，不改任何游戏文件）
python skill/mc-modpack-master/scripts/mc_audit.py --instance "<你的实例目录>" --html

# 3. 升级前校验：这个模组的新版会不会把包搞崩
python skill/mc-modpack-master/scripts/mc_version_check.py \
    --instance "<你的实例目录>" --mod <modrinth-slug>
```

输出分级结论（`critical` / `warn` / `info`）+ JSON/HTML 报告，写到 `<实例>/mc_audit/`。

### 作为 Agent Skill 安装

把 `skill/mc-modpack-master/` 整个目录放进你的技能目录，例如：

- WorkBuddy / CodeBuddy：`~/.workbuddy/skills/mc-modpack-master/`
- Claude Code：`~/.claude/skills/mc-modpack-master/`

重启会话后，技能描述会参与匹配；用户说「整合包崩了」「画面发糊」「动作不显示」时自动触发。

### 作为专家包安装

`doubao/                          豆包 / 扣子交付包（人设 + 知识库 + 校验清单）
├── 01-人设提示词.md
├── 02-知识库/                   5 份可直接上传的文档
├── 03-示例对话.md
├── 04-工具包/scripts/           给用户本地执行
└── 05-验收清单.md

expert/mc-modpack-expert/` 是 WorkBuddy 专家包格式（含 `plugin.json`、Agent MD、头像、随包技能）。

```bash
# 放到专家市场目录后注册
mkdir -p ~/.workbuddy/plugins/marketplaces/my-experts/plugins
cp -r expert/mc-modpack-expert ~/.workbuddy/plugins/marketplaces/my-experts/plugins/
python <expert-manager>/scripts/register_expert.py \
    ~/.workbuddy/plugins/marketplaces/my-experts/plugins/mc-modpack-expert
```

---

## 四层测试

| 层 | 命令 | 判据 |
|---|---|---|
| 规则 | `python skill/mc-modpack-master/scripts/selftest.py` | 27 条固定用例（贴图尺寸 / 版本约束 / 版本比较 / 路径归一化）全过 |
| 审计 | `mc_audit.py --instance …` | 对已知故障实例能复现同一结论，换实例不误报 |
| 契约 | `python expert/mc-modpack-expert/tools/verify_capability.py expert/mc-modpack-expert` | 8 项（结构 / agents / skills / 预加载 / 注册 / 头像 / 脚本 / 占位符）全 PASS |
| 端到端 | 改完重启进游戏 | F3 的 FPS / GPU% / ms tick 三项、逐帧差分对照区为 0、目标错误归零 |

**为什么规则层必须存在**：所有审计结论都压在 `mip_safe` / `satisfies` / `cmp_ver` 这几个纯函数上。
写错一个，报告会整篇误报，而且"看起来很专业"。用固定用例钉死，改代码先跑它。

---

## 目录结构

```
skill/mc-modpack-master/
├── SKILL.md                    作业规程：铁律 / 流程 / 症状表 / 接入规范
├── references/
│   ├── pitfalls.md             14 条实测故障判据（症状 / 判据 / 验证 / 修复）
│   ├── decisions.md            路线取舍表（渲染栈 / 光影 / 光源 / 动画 / 材质 / 家具）
│   └── ecosystem.md            外部方案实测与可信度分级
└── scripts/
    ├── mc_audit.py             八类只读审计
    ├── mc_version_check.py     升级前置校验
    ├── mc_pack.py              材质链 / 非 2 次幂扫描 / 覆盖包构建
    ├── PotScale.java           贴图补 2 的幂
    └── selftest.py             规则断言

expert/mc-modpack-expert/
├── .codebuddy-plugin/plugin.json
├── agents/mc-modpack-expert.md  人格 + 能力边界 + SOP + 自检清单
├── avatars/expert.jpg
├── skills/mc-modpack-master/    与 skill/ 下的副本完全一致（CI 会校验）
└── tools/verify_capability.py   8 项契约验收
```

> 两份技能副本必须一致——`expert/` 要能独立分发，所以不能做成引用。CI 里有专门的 `diff` 任务。

---

## 审计覆盖的八类问题

1. 重复模组 id（同名 jar 会互相覆盖注册表）
2. 已知冲突组合（Voxy × Iris、Continuity × 1×1 贴图）
3. 材质包链：条目是否存在、`pack_format`、修复包是否置顶
4. 贴图 mipmap：区分「真异常」「合法动画条」「已被覆盖」
5. 动画栈：EMF / ETF / FreshAnimations 包 / Punchy 包启用状态
6. 资源链完整性：`blockstate → model → parent`（含原版 jar 索引）
7. 模型字段损坏：`faces` 缺 texture、`textures` 非对象
8. 配置越界（如 `simulationDistance` 写 3/4 会被静默忽略）与日志归因

---

## 已知限制

| 项 | 现状 |
|---|---|
| Forge / NeoForge 深度依赖校验 | 未实现，仅 Fabric 完整 |
| 服务端 / 多人同步问题 | 未覆盖 |
| 存档损坏（region / NBT 级） | 未覆盖 |
| 光影源码解析 | 仅读 `iris.properties` 开关 |
| 运行时 profiler | 只能从日志迹象推断 |

**待验证**：`mctools` 的检测项、HMCL / PrismLauncher 的冲突诊断能力、部分社区资料对
Faster Random / Noisium 归档状态的描述。这些都没有一手证据，不要在 issue 里当作既定事实。

---

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。最重要的两条：

- 新增判据必须有**可复现的验证命令**，没实测过的写「待验证」，不许混进已验证区。
- 新增检查项必须补 `selftest.py` 用例，并在两个不同实例上各跑一次确认不误报。

## 许可

[MIT](LICENSE)
