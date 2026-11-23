# 技术核实：能不能在 Turnip-Duo-v5.1 上继续优化

结论先给：**能，但和你想的不是同一条路。TurnipZ-0.3.0 无法直接用在 Q-7790 上，它的调优思路却已经被 v5.1 吃进去一大半，真正还没拿到的是「那几个被关掉的开关」和「CPU 侧、CCU 几何这两处没试过的旋钮」。**

---

## 一、两个驱动分别是什么

| | Turnip-Duo-v5.1 | TurnipZ-0.3.0 |
|---|---|---|
| 目标 GPU | **Adreno 722**（Dragonwing Q-7790 / CQ7790S） | **Adreno 650**（骁龙 865 / 865+ / 870） |
| 出处 | `sherft2607/turnip-adreno722-duo` release 5.1 | `AlexSanz0902/turnip-sd865-z` release v0.3.0 |
| Mesa 基线 | 27.0.0 · Vulkan 1.4.363 · 上游 `74920caaa0be` | 27.0.0-devel · 上游 `6e4a77089e1` |
| 产物 | `libvulkan_freedreno.so` 13.5 MB + `meta.json` | 13.7 MB + `meta.json` |
| 作者自述 | vauzi 补丁集 + sherft2607 的 A722 硬件实测档 | 「用 Claude Opus 5.5 生成改动，本人在 RP5 上实测」 |

两者是**两个不同 GPU 的 .so**。Adreno 650 的二进制在 722 上不会被 Vulkan loader 选中（设备 ID 对不上），所以「把 TurnipZ 装到 Duo 上」不成立，只有「把它的做法搬过来」成立。

## 二、思路早就搬过了：patches 30–37 就是 Turnip-Z 的移植

Duo 仓库 README 里那句 `Patches 30-37: Turnip-Z engine (mutable-format UBWC, optimized texture sampling, sysmem rendering)` 不是宣传语，是代码事实。我逐字读了这 8 个补丁：

| 补丁 | 干什么 | 对应 TurnipZ 的哪个改动 |
|---|---|---|
| 30 | `DRM_FORMAT_MOD_QCOM_COMPRESSED` 的 swapchain 保住 TILE6_3 + UBWC | 压缩 swapchain 不解压 |
| 31 | 渲染中整幅深度清屏时保住 LRZ | LRZ 不被白白作废 |
| 32 | 关各向异性、mip 取最近、LOD +`TU_Z_LODBIAS/100` | **最核心的省钱手段**（各家实测提升主要来自这里） |
| 33+37 | B8G8R8A8 在 tiled 图上的真实色序交换（含输出/掩码/清除/拷贝/Blit 全链路） | BGRA 正确性配套 |
| 34+35 | 可变格式列表全 BGRA8 时保持 tiled 并走 `is_mutable` | 保留 UBWC 带宽优势 |
| 36 | `tu_autotune` 默认算法改 `PREFER_SYSMEM` | 「sysmem 渲染」 |

而且 **v5.1 的二进制里这些开关都在**，我扫了 `.so` 的字符串表：

```
TU_Z_TEXFAST  TU_Z_LODBIAS  TU_Z_BGRA_SWAP  TU_Z_LRZ_RESCUE
TU_Z_MUTABLE  TU_Z_SYSMEM_ONLY  TU_Z_SAFE_AMBLE
```

反过来扫 TurnipZ-0.3.0 的 `.so`：**一个 `TU_Z_*` 都没有**（它把这些改动编译成固定行为，没留开关）。也就是说「TurnipZ 有优化、Duo 没有」这个判断并不成立——Duo 这边是同一套东西，只是**用开关包起来了，而且默认值看不见**。

## 三、我在真实源码上验出的两个坑

拿 v5.1 钉住的那个 Mesa 提交（`74920caaa0be`）把 `tu_image.cc`、`tu_sampler.cc`、`tu_autotune.cc`、`fd6_format_table.c`、`tu_lrz.cc`、`tu_shader.cc`、`tu_pipeline.cc`、`tu_clear_blit.cc` 全部拉下来，逐个补丁比对锚点：

| 补丁 | 结果 |
|---|---|
| 30 / 31 / 32 / 33 / 36 / 37 | 锚点全部 1:1 命中，**能干净应用** |
| 34 `tu-z-mutable-swap` | **失效**：锚在 `z_mutable < 1` 这个变量上，而新版 30 号补丁已经不带这个变量了 |
| 35 `tu-z-mutable-safe` | **失效**：同一个原因 |

佐证：v5.1 的 `.so` 里有 `TU_Z_MUTABLE`，但**没有** `TU_Z_MUTABLE_SWAP` —— 和补丁失效完全对得上。所以仓库里 `34/35` 是死代码，谁把它们改名成 `.py` 启用，构建日志只会给一句 `no-change`，白跑一轮。

## 四、所以真正的增量只有四处

1. **把 31/32/33/37 重新打开，并把默认值显式烤死。**
   v5.1 到底默认开的哪一个，二进制里查不出来（布尔默认值是立即数，没有字符串可循）。不显式钉住，你就永远不知道自己在测什么。这是本方案性价比最高的一步。
2. **CPU 侧编译优化。** 仓库自己承认 `ANDROID_CPU_FLAGS` 这个钩子「idea from turnip-sd865-z, change 4」，但**默认是空的**——等于这个免费的东西一直没吃。它只影响着色器编译和命令录制（不损画质），正是 TurnipZ「编译着色器时更少卡顿」的来源。
3. **CCU 几何 1/16 还是 2/32。** 这里两条流水线自相矛盾：`57-fd722-duo.py` 把 A722 钉死成 `num_ccu=1, tile_align_h=16`，而同一仓库的 `build-turnip.yml` 写着「A722 device values = `--ccu2`：num_ccu 2, tile_align_h 32, hbb 16」。`num_ccu` 不是调优参数，它会被乘进颜色/深度的 bin 几何——**猜错要么浪费一半并行度，要么出条带**。只能用实测裁决。
4. **强制 sysmem 还是交给 autotune。** A722 只有 **1 MiB 片上 GMEM**，1080p 一帧塞不进去，走 GMEM 就得切成多个 bin 来回搬。TurnipZ 在 865 上能赢，很大程度是「干脆不走 GMEM」。36 号补丁已经软化成 `PREFER_SYSMEM`（保留 FDM/MSRTSS/反馈环的 GMEM 例外），但**没强制**；`TU_DEBUG=sysmem` 才是彻底版，而且它是 31 号 LRZ rescue 生效的前提。

## 五、拿不到的部分（说清楚，不画饼）

- **TurnipZ 没有源码。** 仓库只有 `LICENSE` 和 `README.md`，release 里只有一个 `.so` + `meta.json`。所以「把 0.3.0 的优化合并进 Duo」在源码层面无从下手，只能照着它的做法重写——而这件事 sherft2607 已经做完了。
- **0.4.0 的那三个画面修复拿不到**：MK8 路面全黑、SMO 着色器编译后的黑白帧、BotW 平面色块。这些在 865 上是真问题，在 722 上是否同样存在未知；要复现得自己逆向比对，投入产出比不划算。
- **0.3.0 自己承认「部分游戏比 0.2.0 慢」**，因为它是拿性能换稳定性（重新打开了各向异性 4x）。所以「效率提升许多」这个印象要打折：它对比的是上游 Turnip 26.3.0，不是对比 Duo v5.1。
- **顺带一提**：TurnipZ 现在已经有 **0.4.0**（2026-11 发布，比你说的 0.3.0 更新），三款游戏再快 2–11%，画质修复更多，仍是 A650 专用。

## 六、本方案做了什么

在 v5.1 的补丁树上，按「一次只动一个变量」的原则加 4 个变体（`patches/variants/`），一次 CI 全部产出，装到机器上直接 A/B：

| 变体 | 内容 | 要验证什么 |
|---|---|---|
| `tzqual` | 31/33/37 + 默认值钉死（texfast 明确关） | 画质优先基线，等价「v5.1 但确定性可控」 |
| `tzfast` | tzqual + 32（texfast，LOD +0.45） | 带宽换帧数到底能换多少 |
| `tzsys` | tzqual + `TU_DEBUG=sysmem` | 1 MiB GMEM 该不该彻底放弃 |
| `tzccu2` | tzqual + `num_ccu=2 / tile_align_h=32` | v5.1 的 1/16 档是不是过保守 |

四个包共用同一 Mesa 提交、同一 NDK、同一 CPU 编译参数，差异只有上面写的那一项。

## 七、逐项对比 v5.1：哪些是真差异，哪些只是「确定化」

先把话说清楚：**这不是「我在 v5.1 上加了一堆新优化」，而是「把 v5.1 里存在但状态不明的开关变成确定的，并补上三个它没试过的方向」。**

| 项 | v5.1（发布二进制） | 本方案 | 性质 |
|---|---|---|---|
| 30（QCOM_COMPRESSED 保 TILE6_3/UBWC） | 有 | 同 | 无变化 |
| 36（autotune 默认 PREFER_SYSMEM） | 有 | 同 | 无变化 |
| 31 / 32 / 33 / 37 代码 | 编进去了（`.so` 里有 `TU_Z_*` 字符串），但仓库里现在是 `.off` | 用当前已验证版本重新编入 | 若与发布时同版本则**功能等价**，只是重新确定化 |
| 这些开关的**默认值** | 看不出来（布尔默认是立即数，无字符串可查） | `default_env.conf` 逐项显式钉死 | **消除不确定性**（价值在可复现，不在性能） |
| texfast（关各向异性 + mip 取最近 + LOD） | 若按补丁源码是默认**开** | `tzqual` 关 / `tzfast` 开 + LOD 45 | **真差异**：至少有一个包和 v5.1 行为不同 |
| `TU_DEBUG=sysmem` | 没有 | `tzsys` 有 | **真差异**，且见下 |
| 31 号 LRZ rescue 是否真的在跑 | **否——死代码** | `tzsys` 里活 | **真差异**，见下 |
| `num_ccu` / `tile_align_h` | 1 / 16（57 号补丁强制） | `tzccu2` 改 2 / 32 | **真差异**，方向未知 |
| CPU 侧编译参数 | 空（钩子存在但没设） | `-march=armv8.2-a` | **真差异，且是唯一纯增益、零画质风险项** |

### 为什么说 v5.1 里的 31 号补丁是死代码

31（LRZ rescue）开头就是：

```c
if (!debug_get_option_tu_z_lrz_rescue() || !TU_DEBUG(SYSMEM) ||
    TU_DEBUG(NOLRZ) || TU_DEBUG(NOLRZFC))
   return false;
```

`TU_DEBUG(SYSMEM)` 只能由 `TU_DEBUG=sysmem`（或 `debug.mesa.TU_DEBUG`）打开。而 36 号补丁改的是 `tu_autotune` 的**算法默认值**——我核对了 `tu_autotune.cc`：算法只从 `TU_AUTOTUNE_ALGO` / drirc / 编译期 `DEFAULT` 三处来，**不会去动那个调试位**。所以除非用户自己设了 `TU_DEBUG=sysmem`，v5.1 里这段 LRZ 保留逻辑一次都不会执行。

这不是谁的 bug，是「补丁编进去了但触发条件没人满足」。`tzsys` 变体的意义就是把这条链路接通。

### 明确没有动的部分（别误会）

UBWC 检测与 Android 16 IMapper5 gralloc（01/15）、UBWC swapchain（16）、KGSL 调频锁 `KGSL_PROP_PWRCTRL`（17）、子通道 fence（25）、A722 魔数寄存器表与 `has_lpac=False`（56）、subgroup 半波前（09）—— **一行都没改**。如果你觉得 v5.1 在这些方面还有问题，本方案不解决。

### 期望幅度

不给数字。TurnipZ 那个「34 FPS → 59.9 FPS」是 **A650 @1350p** 的成绩，GPU 规模、GMEM 大小、带宽都不是一回事，直接搬过来必然落空。本方案能确定的是**收益来源**（纹理采样带宽、bin 切换次数、着色器编译卡顿），幅度只能靠你自己那台机器的 A/B 数据说话——这正是 `TEST-PLAN.md` 存在的理由。


---

## 附录：A722 相对 A650 的架构特性，这套驱动用到了多少

结论先说：**「认得 A722」和「吃到 A722 的优势」是两件事。前者做得很扎实，后者几乎为零。**

### 逐项核对（全部可在源码/设备表里复核）

| A7xx 特性 | 在本驱动里的状态 | 是否产生性能收益 |
|---|---|---|
| `CHIP.A7XX` 代码路径 | 已启用（`A6xxGPUInfo(CHIP.A7XX, [a7xx_base, a7xx_gen1, …])`） | 是底座，不是优化 |
| `a722_raw_magic_regs` 专属寄存器表 | 已启用（对 116 条 blob cmdstream + KGSL IOCTL 逆向，纠正 12 处从 A730 继承来的偏差） | **是**，但属正确性 |
| `highest_bank_bit = 15` | 已设（按 KGSL 属性） | **是**，属正确性（UBWC 条带靠它） |
| `tile_align_h = 16` / `num_ccu = 1` | 已设，但比同门 A720（2 / 32）保守 | **未知**，`tzccu2` 就是验证它 |
| `has_lpac` | 被 56 号补丁设为 `False` | **零收益，零损失**——见下 |
| `enable_tp_ubwc_flag_hint` | 被 56 号补丁设为 `False` | 属正确性：对齐 blob 的 `TPL1_DBG_ECO_CNTL1` 值 |
| UBWC 压缩策略 / GMEM fast clear 显式利用 / DP2ACC | **一条没碰** | 否 |

### 两个必须说清的核实结果

**1. `has_lpac` 在 A7xx 上是空转的。** 全 Mesa 对这个字段只有两处读取，都在 `tu_shader.cc`，且都被 `CHIP == A6XX` 包着：

```c
if (CHIP == A6XX && cs->device->physical_device->info->props.has_lpac) { … }
if (CHIP == A6XX) { …  if (…->props.has_lpac) { … } … }
```

A722 是 `CHIP.A7XX`，走 `else` 分支，这两个判断根本不进。所以 `has_lpac = False` 既不是「关掉了优势」，也不是「省下的性能」，它在 A722 上不产生任何指令差异。**不必为它单独出一版对照**——我原打算做的 `tzlpac` 变体因此取消，那是白跑一次 CI。

**2. `tile_align_h` 是唯一真正影响每帧开销的几何参数。** `tu_util.cc` 的 tile 选型里，`tile_size.height` 必须是 `tile_align_h` 的倍数，`tile_count.height = align(高度 / tile 高, tile_align_h)`：

```c
tile_size.height = ROUND_DOWN_TO(tile_size.height, tile_align_h);
… align(DIV_ROUND_UP(fb->height, tile_count.height), tile_align_h);
```

也就是说它直接决定一帧被切成几块、每块进出 GMEM 的次数。16 和 32 哪个对，取决于「tile 更大省 bin 切换」还是「tile 更小更容易塞进 GMEM」——这是纯经验问题，只能实测，不能推理。

### 关于「能不能超过骁龙 865」

三个层面必须分开，否则会得出错误结论：

1. **原生安卓手游不走 Turnip。** 那类游戏用的是高通闭源 Vulkan 驱动，本仓库产物只在 AdrenoTools 类容器（Eden/Citron 等模拟器）里被加载。所以「装了这套驱动手游变快」在原理上不成立。
2. **模拟器场景下，驱动只是变量之一。** A650 那台设备（如 Retroid Pocket 5）与 A722 这台的实际帧数差异，同时受 GPU 档位、内存带宽、CPU 单线程、散热和各自 Turnip 成熟度影响。**Adreno 6xx 是 Turnip 上游支持最久的目标，A7xx 仍在补**——这个成熟度差往往比架构代差更影响实测，而且不是改几行补丁能逆转的。
3. **驱动只能回收损失，不能突破上限。** 30–37 这套是架构无关的（在 A650 上跑同样代码同样生效），所以它不会成为「A722 超过 865」的原因。要赢，靠的是硬件和模拟器侧配置，不是这份驱动。

**不给跑分预测的原因**：我没有 Q-7790 的可靠公开规格（GPU 配置、带宽、GMEM 容量都无从核实），任何「能/不能赢」的定量断言都是编的。上面每条都能在 Mesa 源码里复核，这才是我愿意写的部分。

---

## 附录二：8 Elite（A8xx）生态调研结果

查了四条线：`whitebelyash/mesa-unified`（turnip/gen8 补丁栈）、`The412Banner/Banners-Turnip`（A8xx 分支，还额外维护一份 A710/720/722 实验驱动）、`YurNayt/Turnip_YN`、`StevenMXZ/Adreno-Tools-Drivers`。

### 一、A8xx 的优化，绝大多数不可移植

| A8xx 补丁 | 内容 | 对 A722 是否有用 |
|---|---|---|
| `a8xx_gen8.patch`（13 commits） | A8xx GPU 配置、A810/A825/A829/A830 条目、A8xx 魔数寄存器、`disable_gmem` 属性 | 否，架构专属 |
| Max 的 WinNative 系列 | mesh shader、wave32、A8xx 挂死修复 | 否，A7xx 无这些单元 |
| `a8xx_no_double_threadsize.py` | A8xx 关掉 double-threadsize | 否 |
| `tune_a830.py` | A830 关 `has_fs_tex_prefetch`（上游 TODO 证实） | A722 上该值为 True 且属 a7xx 设计，**但这可由运行时覆盖单测** |
| Steam Deck spoof（`TU_DEBUG=deck_emu`） | 骗过查设备的游戏 | 与本目标无关 |

### 二、真正有价值的三条

**1. A722 存在第二套独立逆向的设备条目，且对方声称在 A722 实机验证过。**

`Banners-Turnip` 的 `patches/a710-720.py` 明确写：*"Mesa's A722 entry still reuses the A730 regs with num_ccu = 1; this script replaces it … and num_ccu = 2 (Vauzi-17/710 5db89bd, tested on A720/A722 hardware)"*。它与本仓库 56 号补丁的差异：

| 项 | Duo 56 号 | Vauzi-17/710 |
|---|---|---|
| `num_ccu` | 1 | **2** |
| `tile_align_h` | 16 | **32** |
| `highest_bank_bit` | 15 | **16** |
| `REG_A6XX_PC_MODE_CNTL` | `0x00001f1f` | `0x0000003f` |
| `REG_A6XX_UCHE_CACHE_WAYS` | `0x00040004` | `0x00000000` |
| `REG_A7XX_SP_UNKNOWN_AB01` | `0x00000000` | `0x00000001` |
| `REG_A6XX_RB_RBP_CNTL` | 未设 | `0x0` |

两套都是逆向产物，**谁对无法靠推理判定**。所以新增 `tzvauzi` 变体：它等于 `tzqual` + 整套替换成上表右列，单变量对照。若出现花屏或固定周期横向条带，第一嫌疑是 `highest_bank_bit`（UBWC 条带直接由它决定），第二是 `tile_align_h`。

**2. `FD_DEV_FEATURES` 运行时覆盖机制在 v5.1 的二进制里是存在的。**

实证：对 `libvulkan_freedreno.so` 做字符串扫描，能找到 `FD_DEV_FEATURES` 与报错串 `Invalid feature "%s" in FD_DEV_FEATURES`。它能覆盖 `GPUProps` 里的字段，实测存在名字的有：`has_lpac`、`enable_tp_ubwc_flag_hint`、`has_8bpp_ubwc`、`has_gmem_fast_clear`、`has_fs_tex_prefetch`、`has_sampler_minmax`、`max_sets`、`reg_size_vec4`、`sysmem_per_ccu_color_cache_size`、`gmem_ccu_color_cache_fraction`。

**不能覆盖**的（二进制里根本没有这些名字，因为它们是 `A6xxGPUInfo` 的构造参数而非 `GPUProps` 字段）：`num_ccu`、`tile_align_h`、`tile_align_w`、`highest_bank_bit`、`cs_shared_mem_size`、`fibers_per_sp`。

用法（不用重编驱动）：`FD_DEV_FEATURES=enable_tp_ubwc_flag_hint=1`

> 注意：字节跳动系容器/Winlator 通过 `WRAPPER_` 前缀传环境变量，AdrenoTools 里则由容器自己起进程，环境变量能否透传到驱动进程取决于容器实现。最稳的是 `TU_DEBUG` 这类驱动自己读的变量（已在 `tzsys` 里用过）。

**3. `cs_shared_mem_size` 32 KiB → 64 KiB。**

`whitebelyash` 的 `dcbb41b2`（Banners 里做成 `a8xx_shared_mem.py`）把**每个**设备条目的 `cs_shared_mem_size` 从 `32 * 1024` 改成 `64 * 1024`，不是只改 A8xx。这是架构无关的一行改动，理论上对计算密集负载（模拟器的 BCn/ASTC 转码、图像缩放）有用，代价是多吃 32 KiB GMEM 预留。

因为 `cs_shared_mem_size` 不可运行时覆盖，要做就得重编。**暂未加入变体**——它和本次要回答的「A722 参数对不对」不是同一个问题，先别把变量堆在一起。

### 三、已排除的一条

`kgsl-zero-timeout-poll`（"DX12 不再每帧等 GPU 完成"）看起来很像能捡的漏，但**不用补**：它落在 Mesa main 2026-10-08（MR 44838），而本仓库钉的提交是 **2026-10-21**，源码里 `wait_timestamp_safe()` 已经有

```c
int timeout_ms = get_relative_ms(abs_timeout_ns);
if (timeout_ms == 0)
   return kgsl_poll_timestamp(device, context_id, timestamp);
```

所以这个修复本来就在里面。先查钉点日期再判断，比看到"某个补丁很诱人"就直接搬要省事。

---

## 附录三：Q-7790 的真实规格，以及它如何改变了优化方向

前两版附录是从驱动代码内部推的。这一节是从**设备侧**反推，结论和之前有一处重要修正。

### 一、核实到的硬件事实

| 项 | 值 | 来源 |
|---|---|---|
| SoC | Qualcomm Dragonwing **Q-7790**（Snapdragon 7 Gen 4 的 IoT/工业版，CPU/GPU 设计相同） | Qualcomm 产品简介 87-93954-1；Retroid 规格页 |
| CPU | 1× A720 @2.6 + 4× A720 @2.4 + 3× A520 @1.8（SoC 上限 prime 2.8） | Retroid 规格页 |
| GPU | Adreno 722 @1.15GHz | 同上 |
| 内存 | **8GB LPDDR4X**，128GB UFS 2.1 | Retroid 规格页 |
| 屏 | 上 1920×1080@120 AMOLED / 下 1280×960@120 AMOLED | 同上 |

### 二、三个关键数字

1. **3DMark Wild Life Extreme：Duo 1721，865 掌机 1332**（+29%）。GPU 算力不缺。
2. **Eden 实测：Hades / Metroid Dread 约 35–40fps**，社区把 Switch 模拟定性为"实验性"。
3. **内存是 LPDDR4X，不是 SoC 规格书上限的 LPDDR5X。** SoC 内存接口为 2×16-bit（32-bit 总线）：
   - LPDDR5X @4200MHz（等效 8533 MT/s）→ ≈ 34 GB/s
   - **LPDDR4X @4266 MT/s → ≈ 17 GB/s**

> 第 3 条是**推算**：Retroid 只写"LPDDR4X"，未公布总线宽度；32-bit 取自 Qualcomm 的 2×16-bit。但它与 35–40fps 的实测自洽，是目前最能解释"算力 +29% 却跑不动 Eden"的一条假设。若日后拿到实测带宽数据，应以实测为准。

### 三、由此产生的方向修正

**修正 1：`tzsys` 的定位要改。** 之前把它当"性能对照"，但 Vauzi-17（710/720/722 驱动的作者）的原文是："如果游戏不稳定，建议 `TU_DEBUG=sysmem`"。它是**稳定性兜底**，不是加速开关。而 MrPurple 在 Eden PR #3205 里的说法相反——`TU_DEBUG=gmem` 是让 A710/720 "能正常运行"的手段。两个方向相反的建议说明：**显存模式是逐芯片、逐游戏的经验值，不能推理，只能实测。**

**修正 2：带宽是首要矛盾，`tzfast` 的价值在这台机器上被放大。** 17 GB/s 的水位下，纹理采样是最大的可控开销。而且它省钱的方式和宣传的不一样：

```python
aniso = 0;                 # Eden 自己的各向异性过滤默认就是关 → 在 Eden 里基本是空操作
miplinear = false;         # ← 真正起作用的一条
lod_bias += 0.30           # 远景少采更细的 mip
```

三线性过滤要采两个 mip 层再插值，`miplinear = false` 只采一层——**纹理取数直接减半**。所以对 Eden 来说，texfast 的收益几乎全部来自 `miplinear`，和"关各向异性"无关。这也意味着：**在 Eden 里不用为"关各向异性"付画质代价，因为本来就是关的。**

**修正 3：`tzeden` 不写死 `TU_DEBUG`。** Eden 从 2026-01-09 起（PR #3205 已合并）支持在图形设置里配 Turnip 环境变量，而 `20-default-env.py` 用 `setenv(..., 0)`，优先级是：

```
Eden 里设的值 > Android 属性（debug.mesa.*） > default_env.conf 内置默认
```

所以内置默认不会挡住用户。把 `TU_DEBUG` 留空，一个驱动包就能覆盖 gmem / sysmem / autotune 三种模式，A/B 成本从"重出一版"降到"改一个设置"。这是本次最实用的一处改动，比多加任何补丁都省事。

**修正 4：双屏本身就是固定带宽开销。**

```
上屏 1920×1080×4B×120Hz ≈ 995 MB/s
下屏 1280×960 ×4B×120Hz ≈ 590 MB/s
合计                    ≈ 1.58 GB/s ≈ 17 GB/s 的 9%
```

这笔开销与游戏无关、一直在扣。降到 60Hz + 关下屏可砍掉约七成——这是设备侧的白捡项，不属于驱动职责，但必须写进 Eden 手册。

### 四、`cs_shared_mem_size` 单列为可选补丁

`cs_shared_mem_size` 在 Turnip 里只有一处用途（`tu_device.cc:1246`）：

```c
props->maxComputeSharedMemorySize = pdevice->info->cs_shared_mem_size;
```

它只是报给应用的 workgroup shared memory 上限，**不参与 GMEM 预算**。A6xx 时代是 32 KiB，A7xx 硬件支持到 64 KiB，FD722 条目沿用了 32 KiB。Eden 的 ASTC/BCn 解码走 compute，理论上受益。

但因为"只抬高一个查询上限、实际是否变大 workgroup 取决于 Eden 自己的启发式"，收益极可能为零。所以放在 `patches-optional/62-cs-shared-64k.py`，**不进默认变体**，避免污染主实验。已验证：只改 FD722 一处，其余 32 个设备块不动，幂等。

---

## 附录四：首次云端构建的实测结果（run #1，`variants=tzeden`）

### 一、构建是真的

| 项 | 实测 |
|---|---|
| 总时长 | 3 分 14 秒（Build 步 2 分 12 秒） |
| ninja 进度行 | 902 行 |
| 产出 `.so` | **12.88 MB**（v5.1 正品 12.89 MB） |
| Mesa | 27.0.0-devel，Vulkan 1.4.363，commit 2026-10-21 |
| 驱动包 | `Turnip-Duo-TZ-v6.0-tzeden.zip` 2.6 MB |

> 一开始我按“3 分钟不可能编完”判定为失败，这是错的。这台 runner 从 dl.google.com 拿 1.5 GB NDK 只要十几秒，且只编译 Turnip 一个目标（不含 gallium/llvmpipe），两分钟出头是真实可行的。**教训：不要用时长推断成败，看产物体积和 ninja 行数。**

### 二、补丁表：14 applied + 1 no-change

`no-change` 的是 `57-fd722-duo.py`，**这是设计行为，不是失效**。它是个"断言守卫"：`EXPECT=(1,16)`、`ENFORCE=False`，当 56 已经把四个值写对时它一个字都不改，然后把实测值打印出来：

```
57-fd722-duo.py: upstream FD722 num_ccu=1 tile_align_h=16 highest_bank_bit=15 cs_shared_mem_size=32 * 1024
57-fd722-duo.py: already applied
```

这行日志恰好是**最有价值的确认**——它证明最终固件里的 A722 几何就是 Duo 的已验证配置。

### 三、默认环境注入成功

```
20-default-env.py: default TU_Z_TEXFAST=1
20-default-env.py: default TU_Z_LODBIAS=30
20-default-env.py: default TU_Z_BGRA_SWAP=1
20-default-env.py: default TU_Z_LRZ_RESCUE=1
```

### 四、二进制里少了 `TU_Z_MUTABLE` / `TU_Z_SYSMEM_ONLY`，不是回归

扫产出的 `.so`，只找到 `TU_Z_TEXFAST` / `TU_Z_LODBIAS` / `TU_Z_BGRA_SWAP` / `TU_Z_LRZ_RESCUE` 四个开关；v5.1 里还有 `TU_Z_MUTABLE`、`TU_Z_SYSMEM_ONLY`。原因：v5.1 那两条是**环境变量门控**的实现，本仓库的 30 / 36 号补丁改成了**无条件生效**（36 号直接改 `tu_autotune` 的编译期 `DEFAULT = PREFER_SYSMEM`，源码里没有 getenv）。所以能力只会更强，不会更弱，只是不再需要设环境变量。副作用：**没法用环境变量关掉它们**。

### 五、一条必须记住的安全约束

57 号源码注释原文：`num_ccu` 与 `tile_align_h` 只在渲染进 GMEM 时才真正起作用；1/16/15 这套值只在强制 sysmem 下验证过，一旦 autotune 走 GMEM，会 `produced UBWC corruption (purple/black lines) and a GPU hang`。

本仓库 36 号补丁把 autotune 默认钉成 `PREFER_SYSMEM`，所以**默认配置是自洽安全的**。但一旦在 Eden 里手动设 `TU_DEBUG=gmem`，就绕开了这层保护，正好踩进那个坑。

**结论：`gmem` 只能配 2/32/16 的 `tzvauzi`，不能配 1/16/15 的 `tzeden` / `tzqual` / `tzsys`。** 这条已同步修正 `START-HERE.md` 与 `EDEN-GUIDE.md`。
