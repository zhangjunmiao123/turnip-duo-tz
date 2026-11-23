# Eden（Switch 模拟器）在 Retroid Pocket Duo 上的调优手册

这份手册只解决一件事：**让 Eden 在这台 Q-7790 上跑得比现在稳、比现在快。**
所有结论都标了出处，能复核；凡是推出来的，我都写明是推算。

---

## 0. 先把硬件底牌摊开

| 项 | 实际值 | 来源 |
|---|---|---|
| SoC | Qualcomm Dragonwing **Q-7790**（= Snapdragon 7 Gen 4 的 IoT/工业版，同 CPU/GPU 设计） | Qualcomm 产品简介 + Retroid 规格页 |
| CPU | 1× Cortex-A720 @2.6GHz + 4× A720 @2.4GHz + 3× A520 @1.8GHz | Retroid 规格页 |
| GPU | **Adreno 722 @1.15GHz** | 同上 |
| 内存 | **8GB LPDDR4X** + 128GB UFS 2.1 | Retroid 规格页（**不是** SoC 规格书里的 LPDDR5X） |
| 上屏 | 5.5" AMOLED 1920×1080 @120Hz | 同上 |
| 下屏 | 4.5" AMOLED 1280×960 @120Hz | 同上 |
| 散热 | 主动（风扇） | 同上 |

### 三个能决定优化方向的数字

**1. GPU 算力是够的。** 3DMark Wild Life Extreme：Duo **1721**，865 掌机（Retroid Pocket 5 一类）**1332** → 大约 **+29%**。

**2. 但 Eden 里只有 35–40fps。** Retro Game Corps / Gardiner Bryant 在零售机上实测 Hades、Metroid Dread 约 35–40fps，并明确把 Switch 模拟定性为"实验性"。

**3. 算力和帧数不成比例，差别在带宽。** SoC 的内存接口是 **2×16-bit**（Qualcomm 产品简介原文）。而 Duo 装的是 LPDDR4X（4266 MT/s）而不是规格书上限的 LPDDR5X（4200MHz 等效 8533 MT/s）：

| 内存 | 总线 | 等效速率 | 带宽 |
|---|---|---|---|
| LPDDR5X（SoC 上限） | 32-bit | 8533 MT/s | ≈ 34 GB/s |
| **LPDDR4X（Duo 实装）** | 32-bit | 4266 MT/s | **≈ 17 GB/s** |

> 这条是**推算**，不是官方标称：Retroid 只写了"LPDDR4X"，没公布总线宽度；总线宽度取自 Qualcomm 的 2×16-bit。但 35–40fps 这个实测值，和"带宽只有一半"是自洽的。

### 所以结论只有一句

**Adreno 722 不缺算力，缺的是喂数据的速度。** 一切优化都要往「减少显存往返」走，而不是往「多算、多精度」走。

这也解释了两件之前想不通的事：
- 为什么 `tzfast`（压纹理带宽）在 A650 上收益一般，在这台机器上可能是最大收益项。
- 为什么"更高分辨率缩放"在这台机器上掉帧特别猛——填充率直接吃带宽。

---

## 1. 装哪个驱动

按 `FORK-HOWTO.md` 出包后，你会拿到这四个，装法都一样（Eden → 设置 → 图形 → GPU 驱动 → 安装）：

| 包 | 定位 | 什么时候用 |
|---|---|---|
| **`base`** | **主力（v6.4 = v5.1 精确等效）** | 日常玩 Eden 用它。v6.4 把 `patches/` 整目录还原成上游 `5.1` tag 原文（v6.3 只做对了一半：大量补丁仍处于 `.off` 停用，`.so` 里没有 `TU_Z_*` 字符串就是证据），用 `diff -r` 校验逐字节一致。预期帧率与 v5.1 一致 |
| `tzeden` / `tzfast` / `tz5` / `tz5s` / `tz6f` 等 | 已归档（v6.0–v6.3） | 实测均比 v5.1 慢，移入 `variants-archive/`，不再构建；要用哪个手动移回 `patches/variants/` |

### v6.1 相对 v6.0 改了什么（荒野之息实测反馈后）

v6.0 在荒野之息上出现「帧数更低 + 边缘锯齿严重」。两个症状的**性质不一样**：

**一、锯齿：确实是 v6.0 引入的，已修。**

32 号把 `miplinear` 设 `false`（三线性→最近 mip）+ `aniso=0`，而 **v5.1 那条补丁只加 LOD 偏置，从不动这两项**。mip 直接跳变 = 远景草地/地面抖动发毛。v6.1 拆成 `TU_Z_TEXMIP`（默认 0 不动）与 `TU_Z_LODBIAS`（默认 0 不加偏置），默认与上游逐 bit 相同。

**二、帧数：不是 v6.0 新引入的，是 v5.1 就有的设计，v6.1 换方向。**

v5.1 也是强制 sysmem（`TU_Z_SYSMEM_ONLY` 默认 true + autotune 默认 `PREFER_SYSMEM`）。这条路在 865 上能赢，在带宽只有 ~17 GB/s、还要被双屏吃掉 1.58 GB/s 的 Duo 上方向是错的。v6.1 第一次把 GMEM 路径真正打开：

1. 36 号 `.off`，autotune 回上游 `BANDWIDTH`（逐 pass 按估算带宽选）；
2. FD722 几何从 `1/16/15` 改成 `2/32/16` —— 1/16/15 只在强制 sysmem 下验证过，一走 GMEM 就 `UBWC corruption + GPU hang`；2/32/16 是 T30 在 A722 实机 + autotune 开启下验证过的（`tzvauzi` 用的也是这套几何）；
3. 17 号不再在变体名不认识时静默回退 p2；KGSL governor 独立成 `TU_KGSL_GOVERNOR_OFF`（默认 1 = v5.1 行为）。

`tzeden` 和 `tzfast` 的区别现在只有 texfast 三个变量；**`tzeden` 不写死 `TU_DEBUG`**，显存模式在 Eden 菜单里现场切，不用重刷驱动。

> 关于 Eden 自带的驱动下载：Eden 确实能自动匹配并下载驱动，但拉来的是通用 T30/上游构建，**没有 A722 的 `num_ccu` / `tile_align_h` 设备条目调校**，所以手装这版才有意义。

---

## 2. Eden 设置：按收益排序

先改这七项，再谈驱动。**改一项测一次**，别一次改完——否则出问题无法归因。

| 优先 | 设置项（Eden → 设置 → 图形/系统） | 建议值 | 为什么 |
|---|---|---|---|
| ★★★ | **分辨率缩放** | **基线一律 `1x`**；测完驱动再考虑 `0.75x` | 荒野之息手持原生就是 720p，0.75x 等于 540p 拉伸到 1080p，几何边缘会明显更糟。它确实是单项收益最大的一档，但必须放在**画质基线确定之后**再动，否则"锯齿变严重"无法归因 |
| ★★★ | **Turnip 环境变量 → `TU_AUTOTUNE_ALGO`** | 留空（= `bandwidth`）→ `profiled` → 配 `TU_DEBUG=sysmem` 对照 | 决定显存模式怎么选。留空是上游按估算带宽逐 pass 选；`sysmem` 那档等于 v6.0 的旧行为 |
| ★★☆ | **各向异性过滤** | `关闭` | Eden 默认就关，确认别被打开。开着会多采纹理，在 17 GB/s 上不划算 |
| ★★☆ | **系统 → 显示刷新率** | Eden 内锁 60Hz | 见下方"双屏带宽账"。120Hz 下 40fps 的游戏反而会出现帧节奏不均 |
| ★☆☆ | **强制最大频率 / 性能模式** | 开（长测掉帧就关掉驱动侧的 `TU_KGSL_GOVERNOR_OFF`） | 有风扇，能扛；但持续满频会让机身先热、热到阈值被 thermal 降频。**短测 2 分钟好看，长测 10 分钟可能更差** |
| ★☆☆ | **ASTC 解码** | GPU | Switch 贴图以 ASTC 为主，Adreno 原生支持；走 CPU 会额外占 CPU 和内存带宽 |
| ★☆☆ | **异步着色器 / 管线缓存** | 开 | 换驱动后**必须重新编译**一次管线缓存，否则第一次进游戏会长时间卡顿，容易被误判成驱动慢 |

### 双屏带宽账（这台机器特有的）

两块 120Hz 屏是持续从内存扫描输出的，这笔开销和游戏无关、一直在扣：

| | 分辨率×4 字节×刷新率 | 占用 |
|---|---|---|
| 上屏 | 1920×1080×4×120 | ≈ 995 MB/s |
| 下屏 | 1280×960×4×120 | ≈ 590 MB/s |
| 合计 | | **≈ 1.58 GB/s** |

按 17 GB/s 算，**光是点亮两块屏就吃掉约 9% 的带宽**。把刷新率降到 60Hz、玩的时候把下屏关掉（或让 Eden 独占前台），能把这笔开销砍掉七成左右。不多，但它是白给的。

---

## 3. Eden 里的 Turnip 环境变量（本次最重要的发现）

Eden 在 2026-01-09 合并了 PR #3205「[turnip/android] Add environment variables settings for turnip drivers」，**图形设置里可以直接给 Turnip 驱动配环境变量**。

这带来两个变化：

1. **你能在 30 秒内切一次显存模式**，不用重出包、不用重装驱动。A/B 成本从"半小时"降到"半分钟"。
2. **驱动内置的默认值不会挡住你**。`20-default-env.py` 用的是 `setenv(..., 0)`，只在变量"尚未设置"时才写默认值。优先级是：

```
Eden 里设的值  >  Android 属性（debug.mesa.*）  >  驱动内置默认（default_env.conf）
```

所以 `tzeden` 里我故意**不写** `TU_DEBUG`，把它留给你。

### 值得挨个试的变量

| 变量 | 取值 | 作用 / 什么时候试 |
|---|---|---|
| `TU_AUTOTUNE_ALGO` | `bandwidth`（默认）/ `profiled` / `profiled_imm` / `prefer_sysmem` / `prefer_gmem` | **v6.1 起显存模式的主开关**。`bandwidth` = 上游按估算带宽逐 pass 选；`profiled` 用时间戳实测来学；`prefer_sysmem` 等于 v6.0 的旧行为（全部走系统内存，带宽吃紧时明显更慢）；`prefer_gmem` 全走片上 GMEM |
| `TU_AUTOTUNE_FLAGS` | `big_gmem` / `tune_small` / `preempt_optimize` | `big_gmem` = 绘图调用 ≥10 次的 render pass 一律进 GMEM。想让画面更省带宽可以试，但 1 MiB GMEM 下可能来回搬 |
| `TU_DEBUG` | `sysmem` | 硬强制系统内存，绕开 autotune。做对照用；**别和 `prefer_gmem`/`big_gmem` 混着理解**，它优先级最高 |
| `TU_DEBUG` | `gmem` | 强制片上 GMEM。**不推荐**：会把所有 pass 无条件塞进 1 MiB GMEM（本该走 sysmem 的大 pass 也塞）。想让 GMEM 用得多一点用 `TU_AUTOTUNE_FLAGS=big_gmem` |
| `TU_DEBUG` | `nolrz` | LRZ 导致深度瑕疵（阴影错位、物体穿透）时关掉 |
| `TU_KGSL_GOVERNOR_OFF` | `1`（默认）/ `0` | 关掉 KGSL governor，GPU 钉最高频。短测好看，长测（>10 分钟）如果帧数反而往下掉，改 `0` 交回系统调频 |
| `TU_Z_TEXFAST` | `1`（默认）/ `0` | texfast 总开关。`0` = 完全回到上游采样行为 |
| `TU_Z_TEXMIP` | `0`（默认）/ `1` | **画质杀手档**。`1` = 关各向异性 + mip 取最近（v6.0 的行为），省带宽但远景会 mip 跳变、边缘发毛 |
| `TU_Z_LODBIAS` | `0`（默认）/ `20` / `30` / `45` | 额外 LOD 偏置，单位 1/100。`0` = 不加偏置；数字越大越省带宽、远景越糊 |
| `TU_Z_BGRA_SWAP` | `1`（默认）/ `0` | 后缓冲 BGRA 实色交换。出颜色错乱（红蓝互换、整屏偏色）时先关这个 |
| `FD_DEV_FEATURES` | `has_8bpp_ubwc=0` | UBWC 相关花屏时试。注意：`num_ccu`、`tile_align_h`、`highest_bank_bit`、`cs_shared_mem_size` **不能**用它改，那几个只能重编 |

> 只写 `TU_DEBUG` 一个名字、不写 `=`，在部分版本里会被当成空值。按上表写完整形式更稳。
> 如果在你那版 Eden 里找不到这个入口：设置 → 图形 → GPU 驱动 附近，通常在选中自定义驱动后出现"驱动设置/配置"。

---

## 4. A/B 协议（照这个做，数据才有意义）

**铁律：一次只改一项。** 每轮记录四个数：

| 场景 | 驱动 | 显存模式 | 分辨率 | 平均 fps | 1% low | 画面异常 | 备注 |
|---|---|---|---|---|---|---|---|
| 基线 | v5.1（现装） | 未设 | 1x | | | | |
| ① | `tzeden` | 未设（= `bandwidth`） | 1x | | | | v6.1 默认 |
| ② | `tzeden` | `TU_AUTOTUNE_ALGO=profiled` | 1x | | | | 实测学习型 |
| ③ | `tzeden` | `TU_DEBUG=sysmem` | 1x | | | | 等于 v6.0 旧行为，用来确认掉帧归因 |
| ④ | `tzeden` | 同最强的一档 | 1x | | | | 再叠 `TU_Z_TEXMIP=1` 看画质/帧数交换比 |
| ⑤ | `tzfast` | 同最强的一档 | 1x | | | | texfast 三件套全开 |
| ⑥ | `tzvauzi` | 同最强的一档 | 1x | | | | 换一套外部 A722 寄存器表（几何相同） |
| ⑦ | ①–⑥ 里最好的 | | **1x → 0.75x** | | | | **最后**才动分辨率，量缩放的收益 |

> **关于 GMEM 与出问题怎么退**：v6.1 的 FD722 几何是 `num_ccu=2 / tile_align_h=32 / highest_bank_bit=16`，与 T30 一致，所以 autotune 选 GMEM 是**预期行为**，不用刻意避开。v6.0 的 1/16/15 只验证过强制 sysmem 的情况，autotune 一旦走 GMEM 会「produced UBWC corruption (purple/black lines) and a GPU hang」（57 号注释原文）——这也是 v6.1 改几何的直接原因。
>
> 万一还是出紫黑横条/横向条带：加 `TU_DEBUG=sysmem` 立刻绕开 GMEM，先保住可用性，再回来改几何。

**测法**：进游戏先跑 3 分钟让机身热稳定（有风扇也要等），然后固定一段路线跑 2 分钟，取中位数而不是峰值。同一款游戏、同一存档点、同一段路线。

**先测什么**：`tzeden` 的 ①②③ 三档显存模式——这一组信息量最大，半小时能出结论，而且全是改环境变量，不用重编。几何参数（⑥）放最后，因为它有花屏风险。

---

## 5. 怎么确认驱动真的加载了

装完驱动、进一次游戏，然后：

```bash
adb logcat -c
# 启动 Eden 并进入游戏，跑 1-2 分钟
adb logcat | grep -iE "default env|Adreno \(TM\) 722|vulkan.*driver"
```

- 看到 `default env: TU_AUTOTUNE_ALGO=bandwidth` / `default env: TU_Z_TEXFAST=1` 之类 → 内置默认值生效了，说明我们这版驱动确实被选中。
- 只看到 `Adreno (TM) 722` 但没有 `default env` → 加载的是系统驱动或别的构建，装错位置了。
- Eden 图形设置里显示的驱动名应为 `Turnip Duo TZ`。

> 想看得更细，可以加 `TU_DEBUG=startup`，日志里会打出 autotune 每个 render pass 选了 GMEM 还是 SYSMEM、以及理由（`early` 前缀的那些是 `prefer_*` 算法的提前返回）。这是判断"到底谁在强制 sysmem"最直接的办法。

---

## 6. 预期与边界

**我不给涨幅数字。** 理由：

- 3DMark 的 +29% 是 GPU 算力，Eden 是带宽 + 驱动成熟度 + CPU 单核的综合题，两者不能换算。
- 35–40fps 是别人的实测，你的机器、你的游戏、你的设置都不一样。
- TurnipZ 那个"34→59.9 FPS"是 **A650 @1350p**，GPU 规模、GMEM、带宽全不同，搬过来必然落空。

**能确定的是收益来源**：交换链格式转换（每帧一次全屏读写）、显存模式选对（gmem/sysmem 选错就是白搬双倍带宽）、双屏扫描输出（约 9% 带宽）、纹理取数（只有在确认带宽卡死时才值得用 `TU_Z_TEXMIP=1` 去换）。

**荒野之息要单独说一句**：它的 Switch 版**没有任何抗锯齿**，手持原生 720p，拉到 1080p 屏上几何边缘必然是硬的。这不是驱动能修的，也不是 v6.0 那个 texfast 造成的（texfast 只会让纹理更糟，不会让几何边缘更糟）。真要压边缘，只能提高 Eden 分辨率做超采样，代价是填充率。

**不能确定的是幅度**，那必须靠第 4 节那张表填出来。

**已知解决不了的**：Eden 在 A7xx 上偶发的菜单/图标闪烁是驱动侧回归（上游构建也有），本方案不修；Adreno 6xx 是 Turnip 上游打磨最久的目标，A7xx 仍在补，这个成熟度差不靠补丁逆转。

---

## 附：这台机器上没用的东西

- **原生安卓手游不走 Turnip**，用高通闭源驱动。这套产物只在 Eden/Cemu/Azahar 这类 AdrenoTools 容器里加载。
- `TU_DEBUG=noubwc`（OneUI 修复）——Android 16 原生系统用不上。
- 8 Elite 那边的 mesh shader / wave32 / `disable_gmem` 补丁——A7xx 没有对应硬件单元，一条都搬不过来。
