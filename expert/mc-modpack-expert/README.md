# 铁砧 · Minecraft 整合包工程师

以证据链排查 Minecraft 整合包故障：模组冲突、材质链断裂、动画与光照失效、性能瓶颈，给出最小必要修复。

## 类型

Agent 型（单个 AI 专家）

## 功能

| 能力 | 说明 |
|---|---|
| 崩溃归因 | 从 `Caused by` 链条定位到具体模组与缺失类，区分硬依赖断裂与版本分支错配 |
| 资源链审计 | `blockstate → model → parent` 全链路解析，含原版 jar 索引，找出会渲染成透明/紫黑的方块 |
| 画质诊断 | 非 2 次幂贴图导致的 mipmap 塌陷、材质包优先级错位、`pack_format` 代差、AppleDouble 垃圾 |
| 动作与光照 | 区分「引擎在但内容不在」与真正的功能缺失（如 EMF/ETF 装了但动画包没启用） |
| 性能定位 | 用 F3 的 `FPS / GPU% / ms tick` 判断瓶颈在显卡、CPU 还是模组逻辑 |

## 随包技能

`skills/mc-modpack-master/`

| 脚本 | 作用 |
|---|---|
| `mc_audit.py` | 八类只读审计，输出分级结论 + JSON/HTML |
| `mc_version_check.py` | 升级前校验 `depends` 区间，防「版本号看着不对就升」 |
| `mc_pack.py` + `PotScale.java` | 材质链解析、非 2 次幂扫描、覆盖包构建 |

判据在 `references/pitfalls.md`，路线取舍在 `references/decisions.md`。

## 使用示例

- 审计我的整合包，按优先级列出问题和修复方案
- 启动崩溃了，帮我定位是哪个模组导致的
- 画面发糊、动作不显示，帮我找出原因

## 能力边界

- 做：Fabric / Forge / NeoForge 客户端的静态审计、配置修正、资源包链路修复、升级前置校验。
- 不做：写模组代码、反编译、改模组 jar、替用户决定存档取舍、无证据猜测。
- 已知外部依赖：MCP `mc-debug`（`D:\PCL\mcp-mc-debug\server.py`），需在连接器页点 Trust 后才可调用；未 Trust 时使用脚本直连。

## 头像

已生成在 `avatars/expert.jpg`（512×512，83KB）。可替换为自定义头像：PNG/JPG，512×512，≤500KB。

## 安装

```bash
python3 scripts/init_expert.py ...   # 仅首次创建时需要
python3 scripts/validate_expert.py <expert-dir>
python3 scripts/register_expert.py <expert-dir>
```

## 打包分享

```bash
python3 scripts/package_expert.py <expert-dir>
```
