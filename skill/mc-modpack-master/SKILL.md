---
name: mc-modpack-master
description: Minecraft 整合包诊断与治理的作业规程——只管「为什么不生效 / 为什么崩 / 为什么糊 / 为什么卡」，以及改之前怎么证明该改。当用户提到整合包优化、模组冲突、材质包顺序、光影、动画/动作不显示、火把不亮、启动崩溃、方块透明或紫黑、帧率低、resourcepacks、mods 目录、Fabric/Forge/NeoForge 版本、或要求审计/精简/补齐某个 Minecraft 实例时使用。含证据链式审计脚本、版本分支陷阱判据、资源链完整性检查与最小介入修复手法。
agent_created: true
---

# Minecraft 整合包诊断与治理

## 铁律

1. **先取证，再动手。** 任何结论必须能指到具体文件、具体日志行、具体数字。禁止「应该是」「可能是」直接下修复。
2. **不信版本号标签，只看 `depends` 约束。** `xxx+mc1.21.4` 的 `+mc1.21.4` 是构建标记，不是兼容性声明。曾把 `reeses-sodium-options 1.8.3+mc1.21.4`（`depends: sodium >=0.6.5`，完全可用）"升级"到标称 1.21.1 的 `2.2.4`，结果它硬依赖 `sodium =0.8.13`，直接崩在 Loader。
3. **`breaks` 是带版本区间的。** 只看键名会得出「sodium 与 iris 不兼容」这种错误结论。必须解出约束值再和已装版本比对。
4. **改任何配置前先备份，且备份不能留在游戏会扫描的目录里。** `resourcepacks/_backups/` 会被当成材质包扫描并报 `non-pack entry`。
5. **一次只改一个变量，改完立刻验证。** 连环改三次再测，出事无法归因。
6. **不重造轮子。** 版本、下载地址、依赖关系一律查 Modrinth API；能靠配置解决的不写代码；能靠上游新版解决的不自己打补丁。
7. **不为一个方块换一整套材质。** 局部打补丁优先于全局替换。

## 第一步：定位实例

```bash
# PCL / HMCL 的版本隔离实例通常在这里
ls -d "D:/.minecraft/versions/"*/ 2>/dev/null
ls -d "$APPDATA/.minecraft/versions/"*/ 2>/dev/null
```

一个实例至少要有：`mods/`、`config/`、`options.txt`、`logs/latest.log`。
**版本隔离时实例目录里没有 `minecraft.jar`**，原版资源在共享的 `versions/<ver>/<ver>.jar`，做资源链检查必须把它算进索引。

## 第二步：跑审计脚本

```bash
python scripts/mc_audit.py --instance "D:/.minecraft/versions/林与风1.2"
```

输出分级结论（critical / warn / info）+ `audit_<stamp>.json`。加 `--html` 出可读报告。
脚本只读，不改任何游戏文件。

判定顺序按「能直接毁体验」排：崩溃 → 动作/光照失效 → 画面糊 → 性能 → 美观。

## 第三步：按症状定位

| 症状 | 首要怀疑 | 验证方式 |
|---|---|---|
| 启动崩在 Loader 前 | 硬依赖断裂（缺类 / 版本区间不满足） | 启动器 stdout 里的 `HARD_DEP_NO_CANDIDATE`；`grep "Caused by"` |
| 崩在客户端初始化 | 某个模组的兼容层引用了新版才有的类 | `NoClassDefFoundError` 指向哪个包，就去升那个模组 |
| 第一人称动作全没了 | 动画**资源包**没启用（模组本体在 ≠ 动画在） | 游戏内是否有 `RESOURCE PACK DISABLED` 弹窗；查 `options.txt` 的 `resourcePacks` |
| 手持火把不照亮 | 根本没有动态光源模组 | `ls mods | grep -iE 'light|lucent|lamb'` |
| 方块透明 / 紫黑 | 模型缺失，或材质包与模组版本错配 | 审计的「资源链完整性」段落 |
| 画面整体发糊 | 非 2 次幂贴图压塌图集 mipmap | 审计的 mipmap 段落；看日志 `limits mip level` |
| 砍树时灵时不灵 | `treesMustHaveLeaves` / `choppingRequiresCorrectToolForDrops` | `config/treechop-*.toml` |
| 卡 / 掉帧 | 先看 tick，再看 GPU | F3：GPU% 与 `ms tick` 谁先满 |

## 第四步：修复手法库

### 资源包顺序

低 → 高（越靠后优先级越高）：

```
vanilla → 模组内置包 → 基础材质 → 汉化/附加 → 动画包 → 修复覆盖包（必须最顶）
```

判断依据是**谁要覆盖谁**，不是"哪个好看"。修复覆盖包放顶层，否则被基础材质盖掉。

### mipmap 塌陷

只有 `textures/block/` 与 `textures/item/` 进地形/物品图集。判定合法尺寸：

```python
def ok(w, h):
    pot = lambda n: n > 0 and (n & (n-1)) == 0
    return pot(w) and (pot(h) or h % w == 0)   # 后者是合法动画条，如 16x48
```

**别修带 `.png.mcmeta` 的**：帧尺寸写死在元数据里，改分辨率会破坏帧布局。
覆盖包路径要与原资源一致，且**必须是 2 次幂尺寸**才有意义。

### AppleDouble 垃圾

macOS 打包会混入 `._xxx`，在 zip 里表现为 `\x00\x05\x16\x07` 开头 + `Mac OS X` 字样，但文件名伪装成正常 `.json`。
重建 zip 时按前缀剔除，其余条目原样保留：

```python
if data.startswith(b"\x00\x05\x16\x07") or "__MACOSX" in name or name.split("/")[-1].startswith("._"):
    skip
```

### 版本分支

```bash
curl -s "https://api.modrinth.com/v2/project/<slug>/version?game_versions=%5B%22<MCVER>%22%5D&loaders=%5B%22fabric%22%5D"
```

拿到候选后**必须比对它的 `depends` 与本实例已装版本**，不能只看 `version_number` 里的 MC 号。
`scripts/mc_version_check.py` 就是干这个的。

### 崩溃后取证据

```bash
grep -aE "Caused by|HARD_DEP|Incompatible mods" <launcher_stdout>
ls -t <instance>/hs_err_pid*.log | head -1
```

## 第五步：验证，且要可复核

- 性能：F3 读 `FPS / GPU% / ms tick` 三个数，缺一不可判瓶颈。
- 动作：**逐帧差分**比肉眼看截图可靠。按住攻击键连拍 4 帧，比较手部区域与对照区（如左上角）的变化像素比例；对照区必须为 0，否则说明采集本身在抖。
- 资源：改完重载后 `grep` 目标错误是否归零，不要凭感觉。

## 禁止事项

- 不用"版本号看起来不对"当理由升级模组（先看 `depends`）。
- 不叠加第二个同类模组（第二个小地图 / 第二套优化栈 / 第二个动态光源）。
- 不在没有抖动证据时改 Camera 相关 mixin。
- 不为单个模型逐个禁用整个动画栈。
- 不把 `options.txt` 改动在游戏运行时写入（退出时会被覆盖）。
- 不删用户文件；一律移动到 `mods_disabled/` 或带日期的备份目录。

## 现成方案：先查，再决定要不要自己写

生态里已有成熟工具，**不要重复造**。动手前先看 `references/ecosystem.md`（含实测日期与星数）：

| 诉求 | 该用谁 |
|---|---|
| 做包、发布、git 管理、自更新分发 | **packwiz**（1044★，MIT，GitHub 实测存在） |
| 从零建包 + 搜模组 + 依赖解析 | `mc-pack-builder-mcp`（npm 1.1.0）或 packwiz |
| 写模组、游戏内调 API | `langyo/minecraft-mod-mcp`（44★，2026-11-19 仍活跃） |
| 搭 NeoForge/Forge 服务端 | `taracodlabs/aiden` 的 `minecraft-modpack-server` |
| 让 agent 玩 / 读写世界 | `mc-agent-mcp` / `x12101xx/minecraftmcp` |
| **已装实例为什么崩/糊/没动作/卡** | **本技能** |

本技能只做最后一格：对**已装好的客户端实例**做渲染层与资源层的证据化诊断。
别人覆盖的部分，指过去，不重写。

判断外部资料时按可信度分级（`references/ecosystem.md` 第五节）：
一手仓库/官方 API > 官方文档 > 社区实测长文 > 内容农场。
**看到推荐列表先做过滤**：把模组名批量丢给 Modrinth 的 `game_versions` 查询，没有当前版本构建的直接划掉。

## 测试与验证

四层，缺一层就不算验证过：

| 层 | 手段 | 判据 |
|---|---|---|
| 规则 | `python scripts/selftest.py` | 27 条固定用例全过（贴图尺寸、版本约束、版本比较、路径归一化） |
| 审计 | `mc_audit.py --instance …` | 对已知故障实例能复现同一条结论，且换一个实例不误报 |
| 契约 | `verify_capability.py`（在专家包内） | 8 项全 PASS，尤其 C4「预加载与 plugin.json 一致」 |
| 端到端 | 重启进游戏 | F3 三个数、逐帧差分对照区为 0、目标错误归零 |

**规则层为什么必须有**：审计结论全建立在几个纯函数上。写错一个，报告整篇误报却"看起来很专业"。
所以用固定用例把 `mip_safe` / `satisfies` / `cmp_ver` 钉死，改代码先跑它。

## 脚本

| 脚本 | 作用 |
|---|---|
| `scripts/mc_audit.py` | 全量只读审计：重复模组、材质链、动画栈、mipmap、资源链、配置越界、日志归因 |
| `scripts/mc_version_check.py` | 查 Modrinth 最新版并校验 `depends` 是否被当前实例满足（防"升级即崩"） |
| `scripts/mc_pack.py` | 材质包链路解析、非 2 次幂贴图扫描、覆盖包构建 |
| `scripts/selftest.py` | 核心判定规则的 27 条确定性断言 |

详细判据与实测案例见 `references/pitfalls.md`，技术路线选择见 `references/decisions.md`，
外部方案与分工见 `references/ecosystem.md`。
