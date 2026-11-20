# 生态与现成方案（2026-11-20 实测）

**使用前先查这张表。** 已经有成熟方案的部分不要重写；本技能只补别人没覆盖的那一层。

所有条目都经过 GitHub API / npm registry 实测，标注了核对日期。标「未验证」的表示只看到第三方页面描述，仓库或包本身未确认。

---

## 一、已验证的外部方案

### 1. packwiz —— 整合包「制作与分发」的行业标准

- 仓库：`github.com/packwiz/packwiz`（Go，MIT，**1044 ★**，最后推送 2026-10-14）
- 文档：`packwiz.infra.link`

**它做什么**：用 TOML 元数据而非 jar 管理整合包，天然 git 友好；`packwiz update --all` 批量更新；
CurseForge / Modrinth 双向导入导出；`packwiz-installer` 做自更新实例；区分 client-only / server-only。

**它不做什么**：不做本地实例的渲染层诊断（资源链、mipmap、动画栈），也不分析已装实例的冲突细节。

**何时用**：要发布整合包、要给服务器做自更新包、要把现有包纳入 git 管理。
**何时不用**：只是排查"我这台机器为什么糊/为什么崩"——那是本技能的活。

---

### 2. langyo/minecraft-mod-mcp —— 游戏内 MCP，面向「模组开发」

- 仓库：`github.com/langyo/minecraft-mod-mcp`（Python，**44 ★**，最后推送 **2026-11-19**，活跃）
- npm：`minecraft-mod-mcp@0.4.28`（2026-11-07）

**它做什么**：以模组形式在游戏内起 HTTP MCP 服务（默认端口 9876，占用则回退），
支持 MC 1.8.9 ~ 26.1.2、Forge / Fabric / NeoForge。面向**写模组**：在游戏里调用 API、验证行为。
带"释放鼠标"悬浮按钮解决切屏暂停的老问题。

**与本技能的关系**：互补。它解决"运行时能做什么"，本技能解决"装完之后为什么不对"。
两者可以同时用，不冲突。

---

### 3. dcd887/mc-pack-builder-mcp —— MCP，面向「建包 + 搜模组 + 依赖解析」

- 仓库：`github.com/dcd887/mc-pack-builder-mcp`（TypeScript，**0 ★**，最后推送 2026-10-23）
- npm：`mc-pack-builder-mcp@1.1.0`（2026-10-23，有 CI 与单元测试）
- 随附 SKILL.md：`skills/mc-pack-builder-helper/SKILL.md`

**工具**：`create_pack`、`search_mods`、`resolve_dependencies`。

**与本技能的重叠**：都涉及"依赖解析"。差别在于——它是**从零建包**（按 Modrinth 元数据解析），
本技能是**对已装实例做升级前校验**（下载候选 jar、读 `fabric.mod.json`、比对本地已装版本）。
前者回答"这套组合能不能装"，后者回答"把我现在这个换掉会不会崩"。

**取舍**：要新建整合包 → 用它或 packwiz，不要用本技能硬做。要升级已装实例的某个模组 → 用本技能的 `mc_version_check.py`。

---

### 4. ArchitektSpeer/mc-agent-mcp —— 让 agent 自己玩生存

- 仓库：`github.com/ArchitektSpeer/mc-agent-mcp`（Java，Fabric mod，**3 ★**，2026-10-17）
- 29 个工具，覆盖感知、移动、交互、背包、合成、聊天；MCP over Streamable HTTP，Bearer 认证；
  为慢模型内置每 tick 的生存反射（防苦力怕、进食、换气）。

**关系**：完全不同层。它是"替玩家操作"，本技能是"替玩家诊断"。不冲突，也不替代。

---

### 5. x12101xx/minecraftmcp —— 世界读写 MCP

- 仓库：`github.com/x12101xx/minecraftmcp`（Java + TypeScript，**0 ★**，2026-11-07）
- 要求 MC 26.3 / Fabric Loader 0.20.1 / JDK 25；服务端线程执行、大操作分 tick 调度。

**关系**：不同层。适用于"让 agent 读写世界"，不适用于诊断。

---

### 6. taracodlabs/aiden → `skills/minecraft-modpack-server`

- 仓库：`github.com/taracodlabs/aiden`（**902 ★**，AGPL-3.0，2026-10-19）
- 技能实际存在：`skills/minecraft-modpack-server/{SKILL.md, skill.json}`，Apache-2.0

**它做什么**：**服务端**搭建——NeoForge/Forge 安装、Java 版本、JVM 调参、防火墙、LAN、
备份、启动脚本；含实测坑（`allow-flight=true`、`max-tick-time`、首次启动慢）。

**关系**：互补。它是服务端侧，本技能是客户端侧。要开服就看它，不要在本技能里重写开服流程。

---

### 7. beihongliangchu/mctools —— 「MC 一键诊断」

- 仓库：`github.com/beihongliangchu/mctools`（**0 ★**，2026-10-22）
- 描述：Minecraft 联机诊断与整合包体检工具 · 免费分发包

**状态**：仓库存在，但**内容未审计**（未读源码、未验证其检测项）。
**关系**：面向玩家的 GUI/一键工具，不是 agent 可调用的接口。可作为"人工复查"的备选，不纳入本技能链路。

---

### 8. 启动器内置能力（HMCL / PrismLauncher）

- 依赖查看器、日志冲突分析、重复类扫描、依赖关系树。

**状态**：**未实测**（评估环境使用第三方启动器）。属于启动器界面内能力，无法被 agent 直接调用。
可用于人工交叉验证，不作为自动化链路的一环。

---

## 二、查不到 / 不采纳

| 条目 | 实测 | 结论 |
|---|---|---|
| `javimosch/packrinth`（第三方站点列为 Skill） | GitHub API 返回 **Not Found** | 仓库不存在或已删除，**不采纳** |
| 第三方站点宣称的「116,000+ SKILL.md」等规模数字 | 无法核实 | 营销数字，不作为选型依据 |

---

## 三、分工决策表

| 你的诉求 | 用谁 |
|---|---|
| 我这台机器为什么崩 / 糊 / 没动作 / 卡 | **本技能**（`mc_audit.py`） |
| 把这个模组升上去会不会崩 | **本技能**（`mc_version_check.py`） |
| 贴图糊了要批量修 mipmap | **本技能**（`mc_pack.py`） |
| 从零做一个整合包并发布 | packwiz，或 `mc-pack-builder-mcp` |
| 整合包纳入 git、做自更新分发给服务器 | packwiz |
| 写一个新模组、在游戏里验证 API | `langyo/minecraft-mod-mcp` |
| 搭 NeoForge/Forge 服务端、调 JVM、做备份 | `taracodlabs/aiden` 的 `minecraft-modpack-server` |
| 让 agent 自己玩、挖矿建造 | `ArchitektSpeer/mc-agent-mcp` |
| 让 agent 读写世界方块 | `x12101xx/minecraftmcp` |

---

## 四、本技能不覆盖、也不打算覆盖的部分

明确写出来，避免越界承诺：

- **整合包的制作与分发** → packwiz
- **服务端搭建与运维** → aiden 的 server skill
- **模组开发与运行时调用** → langyo 的 mod-mcp
- **游戏内自动化操作** → mc-agent-mcp
- **启动器级依赖图** → HMCL / PrismLauncher 界面

本技能的唯一定位：**对已装好的客户端实例做渲染层与资源层的证据化诊断**。
别人做过的，就指过去，不重写。

---

## 五、公开站点调研与可信度分级（2026-11-20 实测）

### 分级标准

| 级 | 类型 | 判据 |
|---|---|---|
| A | 一手仓库 / 官方 API | 能直接读到源码、元数据、构建列表 |
| B | 官方文档站 | 规范、版本说明 |
| C | 社区长文 / 实测记录 | 有具体取舍理由与版本信息，可与一手源交叉验证 |
| D | 内容农场 / 标题党列表 | 只有"最佳 X 个"，无版本、无代价、无来源 |

**引用规则**：A/B 可直接作为结论依据；C 需与一手源交叉验证后才采纳；D 只用来识别"哪些说法在流传"，不作为依据。

### 实测样本

| 来源 | 可达性 | 级 | 采纳 / 丢弃 |
|---|---|---|---|
| `docs.modrinth.com/api/` | HTTP 200 | B | 采纳。`depends` / `breaks` 语义与版本区间字段的一手依据 |
| `topmoddedservers.com/en/guides/mods-optimisation-minecraft` | HTTP 200 | C | <b>部分采纳</b>：①「一个类别只装一个」②「先上 Spark 测量再加」③ 指出 Faster Random 作者已归档、Noisium 原版归档需用 fork。与本地实测的"不要叠同类"一致 |
| `www.mcmod.cn` | HTTP 200 | C | 采纳为中文生态索引（模组/整合包条目页），不采纳其主观评分 |
| `bilibili.com/video/BV15Z421p7D8` | HTTP 200 | C | <b>仅作现象参考</b>：该作者记录了 connector 与传送门模组冲突、部分模组功能重叠需自行取舍——与"重复功能"判断一致，但无版本证据 |
| `bilibili.com/video/BV1cX4y1T7RZ` | HTTP 200 | C | 仅作安装流程参考（Forge/Fabric/光影安装），与诊断无关 |
| `bilibili.com/video/BV16i4y1C757` | HTTP 200 | C | 采纳其"常用站点清单"（mcmod / curseforge / planetminecraft / Complementary），不采纳模组选型 |
| `toxigon.com/best-minecraft-mods-for-performance-in-2026` | <b>HTTP 403</b> | D | <b>不采纳</b>。正文推荐 Phosphor / Starlight / LazyDFU——见下方实证，这三个在 1.21.1 上根本没有构建 |
| `wiki.fabricmc.net/documentation:fabric_mod_json_spec` | <b>HTTP 502</b> | 待验证 | 本次不可达，`fabric.mod.json` 语义以 Modrinth API 文档与实测行为为准 |
| `minecraft.wiki` | <b>HTTP 403</b> | 待验证 | 站点拦截抓取，未作为依据 |

### 过时方案的实证（用 Modrinth 构建列表反证）

对 1.21.1 + Fabric 查询结果：

| 模组 | 1.21.1 构建 | 结论 |
|---|---|---|
| Phosphor | <b>无</b> | 不可用。任何在 2026 年仍推荐它的文章，说明作者未核对版本 |
| Starlight | <b>无</b> | 不可用。光照引擎已并入原版，该模组不再发新版 |
| LazyDFU | <b>无</b> | 不可用 |
| Faster Random | 有 5.1.0（2024-07-23） | 长期未更新，社区指南称作者已归档并建议不要依赖 —— <b>待验证</b> |
| Noisium | 有 2.3.0（2024-08-21） | 原版停更，社区称需用 NoisiumForked —— <b>待验证</b> |
| Krypton | 有 0.2.8（2024-06-22） | 存在但陈旧；仅服务端网络优化才需要 |
| ImmediatelyFast | 1.6.15（2026-10-13） | 活跃 |
| Dynamic FPS | 3.11.4（2026-01-29） | 活跃 |

**用法**：评估任何"推荐列表"时，先把里面的模组名批量丢给 Modrinth 的 `game_versions` 过滤，
没有当前版本构建的直接划掉。这一步能在 30 秒内识别出内容农场文章。
