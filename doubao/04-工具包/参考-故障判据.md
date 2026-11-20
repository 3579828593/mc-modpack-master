# 故障判据库

每条都来自实际排障，带可复核证据。**先按症状查表，再验证，再动手。**

---

## 1. 「动作没了」——模组在，动画数据不在

**症状**：第一人称没有挥臂/挖矿动作；或实体不播放 FreshAnimations 动画。

**判据**：Punchy 这类模组是「本体 + 内置资源包」两件套。只装本体不带包时，游戏内会弹
`PUNCHY: RESOURCE PACK DISABLED`，`resourcePacks` 里找不到 `punchy:punchy`。

**验证**：
```bash
grep -o 'resourcePacks:.*' <instance>/options.txt | grep -c 'punchy:punchy'
```
返回 0 就是没启用。

**修复**：选项 → 资源包 → 勾选 Punchy!，或直接改 `options.txt` 加 `punchy:punchy`。

**同族陷阱**：FreshAnimations 也一样——`mods/` 里有 EMF+ETF 但 `resourcePacks` 没有
`FreshAnimations*.zip`，同样等于零动画。

---

## 2. 版本号 ≠ 兼容性

**症状**：一个"看起来版本分支不对"的模组，升级后启动直接崩。

**实测**：`reeses-sodium-options 1.8.3+mc1.21.4` 在 1.21.1 上工作正常，因为它的
`depends.sodium` 是 `>=0.6.5`，本地 0.6.13 满足。升到标称 `mc1.21.1-2.2.4` 后崩，
因为 2.2.4 的 `depends.sodium` 是 `=0.8.13+mc1.21.1`。

**判据**：`version_number` 里的 `+mcX.Y.Z` 是构建标记，不是兼容声明。
**唯一可信的是 `depends` 的版本区间。**

**验证**：`scripts/mc_version_check.py --mod <id>` 会下载候选 jar 读元数据并逐条比对。

---

## 3. `breaks` 是带区间的

**症状**：看到 `sodium` 声明 `breaks: [iris, sodium-extra]` 就以为装不了。

**判据**：Fabric 的 `breaks` 值是版本约束。`sodium 0.6.13` 声明的是
`iris <1.8.7`、`sodium-extra <0.6.0`。已装 1.8.8 / 0.6.0 → 不触发。

**验证**：
```python
for mid, m in mods.items():
    for tgt, cons in (m.get("breaks") or {}).items():
        if tgt in mods:
            print(mid, "breaks", tgt, cons, "已装", mods[tgt])
```

---

## 4. 崩在客户端初始化：`NoClassDefFoundError`

**症状**：`Minecraft has crashed!` + `Caused by: java.lang.NoClassDefFoundError: <某包>`

**判据**：某模组的兼容层引用了**新版本才有**的类。看 `NoClassDefFoundError` 的包名属于谁，
把那个模组升到含该类的版本。

**实测**：`fwa 1.3.7` 的 `EntityCullingCompat.init()` 引用
`dev.tr7zw.entityculling.versionless.api.EntityCullingAPIVersionless`，
本地 EntityCulling 1.10.5 没有 → 升到 1.12.1 解决。

**验证**：
```python
with zipfile.ZipFile(jar) as z:
    [n for n in z.namelist() if "EntityCullingAPIVersionless" in n]
```

---

## 5. 材质包代差：`pack_format` 对不上

**症状**：日志刷 `Unknown blockstate property`、某些方块丢材质包模型。

**判据**：`pack.mcmeta` 的 `pack_format` 与游戏版本不匹配时，靠 `nopackcompatcheck`
这类模组能绕过版本检查，但**属性层面的差异绕不过去**。

**实测**：`Stay_True pack_format=64`（1.21.9 时代）跑在 1.21.1（34）上，
`cut_sandstone.json` 用了新版才有的 `axis` 属性 → 3 个变体全部加载失败。
全包只影响这 1 个方块，所以**打补丁比换包划算**。

**验证**：
```bash
for z in <instance>/resourcepacks/*.zip; do
  python -c "import zipfile,json,sys;print(sys.argv[1], json.loads(zipfile.ZipFile(sys.argv[1]).read('pack.mcmeta').decode('utf-8-sig'))['pack']['pack_format'])" "$z"
done
```

---

## 6. AppleDouble：伪装成 JSON 的垃圾

**症状**：`Failed to load blockstate ... MalformedJsonException`，
但打开对应文件看内容是二进制。

**判据**：macOS 打包混入 `._xxx`。在 zip 里表现为首字节 `\x00\x05\x16\x07`，
第 4~14 字节是 `Mac OS X`，文件名却是正常的 `.json`。

**修复**：重建 zip，剔除这类条目与 `__MACOSX`，其余原样保留。

```python
if data.startswith(b"\x00\x05\x16\x07") or "__MACOSX" in name or name.split("/")[-1].startswith("._"):
    continue
```

---

## 7. 画面糊：非 2 次幂贴图压塌 mipmap

**症状**：远处方块边缘发虚、整体像蒙了层雾。

**判据**：只有 `textures/block` 与 `textures/item` 进地形/物品图集。
其中任一张宽不是 2 的幂，该 sprite 的 mip 链就退化。

**合法尺寸**：
```python
pot = lambda n: n > 0 and (n & (n-1)) == 0
ok = pot(w) and (pot(h) or h % w == 0)     # 后者是动画条，如 16x48
```

**例外**：带 `.png.mcmeta` 的不能改尺寸——帧高写死在元数据里，缩放会破坏帧布局。

**实测**：方块小镇 23 张 48×48 / 96×96 是主因（48 不是 2 的幂）。

---

## 8. Continuity 的 1×1 保留贴图

**症状**：装了 Continuity 后整张方块图集发糊。

**判据**：Continuity 会为连接纹理生成 1×1 保留贴图，把图集 mipmap 压到 0。
与具体材质包无关，是模组行为。

**取舍**：要么关 Continuity，要么接受糊。优先保清晰度。

---

## 9. Voxy × Iris

**症状**：地形一直加载不出来、帧率崩塌、日志里 `IrisUtil.voxyPipelinePatch` 循环。

**判据**：两者都接管地形渲染管线，互相递归。
**取舍**：二选一，没有共存方案。

---

## 10. 备份目录被当成材质包

**症状**：`Found non-pack entry '...resourcepacks/_backups', ignoring`

**判据**：游戏扫描 `resourcepacks/` 下所有条目。把 `.bak` 放进去就会被扫。
**修复**：备份一律放到实例根目录的 `_pack_backups/`，不要留在 `resourcepacks/`。

---

## 11. `simulationDistance` 有下限

**症状**：改了配置但没效果。

**判据**：1.21.1 的合法区间是 `[5, 32]`。写 3 或 4 会被日志判非法
`Value 3 outside of range [5:33]`，实际仍跑 5。

**同类**：`mipmapLevels` 0~4、`biomeBlendRadius` 0~7、`guiScale` 0~8，越界静默忽略。

---

## 12. 砍树时灵时不灵

**判据**（`config/treechop-*.toml`）：

| 键 | 默认 | 症状 |
|---|---|---|
| `choppingEnabled` | true | false 时完全不砍 |
| `sneakBehavior` | `INVERT_CHOPPING` | 潜行会**关闭**砍树 |
| `treesMustHaveLeaves` | true | 模组树树叶不在标签里 → 判定无叶 → 不倒 |
| `choppingRequiresCorrectToolForDrops` | true | 模组原木声明工具需求时空手不砍 |

**先确认功能是否真的没生效**：TreeChop 会在准星旁显示 `Chopped <方块> n/m 次`。
HUD 有计数 = 功能正常，问题在别处（此时不要再改配置）。

---

## 13. EMF 丢弃模型

**症状**：`[EMF]: model attempted creation more than 64 times {minecraft:bell#main}. EMF is now ignoring this model`

**判据**：某个实体模型被每帧重建而非复用，触发 EMF 的 64 次保护后直接放弃该模型。
影响面通常只有 1 个模型。**不要为此逐个禁用动画模组**——风险覆盖整个动画栈。

---

## 14. 验证方法本身的坑

| 坑 | 表现 | 对策 |
|---|---|---|
| 窗口失焦 | 切走窗口后 FPS 掉到个位数，误判性能 | 先 `SetForegroundWindow`，确认 `GetForegroundWindow` 相同再读数 |
| DPI 缩放 | 截图 1463×914，窗口实际 2560×1600，点击全错位 | 坐标 = 截图显示坐标 × (物理宽 / 截图宽) |
| 只看单帧截图 | 看不出动作是否存在 | 按住攻击键连拍 4 帧，比较手部区域与**对照区**的差异像素比例；对照区必须为 0 |

**逐帧差分的判读**：手部区域差异 5%~11% 说明在动；对照区恒为 0 证明采集稳定。
若手部也是 0，才是真的没动画。
