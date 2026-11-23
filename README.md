# Turnip Vulkan Driver for Retroid Pocket Duo (Adreno 722)

> **这是 Turnip Duo TZ 分支（在 v5.1 补丁树上的实验版）**
>
> 相对上游 v5.1 的改动：把仓库里被关成 `.off` 的 Turnip-Z 补丁（31/32/33/37）重新启用、
> 用 `patches/variants/*/default_env.conf` 把每个开关的默认值显式钉死、加上 CPU 侧编译优化，
> 并按「一次只动一个变量」拆成 4 个可 A/B 的变体。
>
> - **从零开始照着做 → [START-HERE.md](START-HERE.md)**（建仓库、跑 CI、装驱动、测数据，10 步）
> - 为什么这么改、TurnipZ 到底能不能用 → [ANALYSIS.md](ANALYSIS.md)
> - **Eden（Switch）在这台机器上怎么调** → [EDEN-GUIDE.md](EDEN-GUIDE.md)
> - 怎么编译出来（GitHub Actions，不用本机 Linux）→ [FORK-HOWTO.md](FORK-HOWTO.md)
> - 怎么测、怎么读结果 → [TEST-PLAN.md](TEST-PLAN.md)
> - 改补丁前先离线验锚点 → `python tools/verify_anchors.py --mesa <mesa 目录>`
>
> 上游 README 原文见下。


Custom, hardware-verified Mesa Freedreno (Turnip) Vulkan driver engineered specifically for the Retroid Pocket Duo (Qualcomm Adreno 722 GPU).

---

## Target Hardware and Identity

* Device: Retroid Pocket Duo
* Chipset: Qualcomm Dragonwing Q7790 (CQ7790S)
* Platform / SoC ID: sun / SoC ID 732 (Codename: kera)
* GPU Model: Qualcomm Adreno (TM) 722
* GPU Chip ID: 0x43020100 (1124204800)
* Kernel Driver: msm_kgsl (adreno_gpu_core_gen7_17_0, gpurev 0x00071100)
* Operating System: Android 16 (API Level 36)

---

## Hardware Ground Truth

Parameters extracted and verified from physical Retroid Pocket Duo hardware via ADB kernel device trees, msm_kgsl.ko, vendor driver blobs, and stock_vkjson.json:

| Hardware Parameter | Value | Source / Verification |
| :--- | :--- | :--- |
| On-Chip GMEM | 1 MiB (0x100000) | Kernel core structure; queried directly via KGSL at runtime |
| Highest Bank Bit | 15 (0xf) | Device tree, verified against kernel RB_NC_MODE_CNTL = 0x814 (bits 2:1 = hbb - 13) |
| Compute Shared Memory | 32 KiB (32768 bytes) | Verified against OEM blob maxComputeSharedMemorySize; corrects community 64 KiB over-allocation |
| Subgroup Size | 64 | OEM blob reports subgroupSize = 64 |
| CCU Geometry | num_ccu = 1, tile_align_h = 16 | Upstream Mesa FD722 geometry, verified via vendor blob command-stream traces |
| Async Compute (LPAC) | Disabled | Blob-trace analysis: GPUProps(has_lpac = False), overriding generic a7xx_base |
| UBWC Configuration | Mode 4.0, 32-byte min access | Device tree (qcom,ubwc-mode = 4, qcom,min-access-length = 0x20) |
| Hardware Magic Registers | Dedicated a722_raw_magic_regs | 37-entry table extracted from 116 Qualcomm blob traces, correcting 12 inherited A730 registers |

---

## Performance and Compatibility

### 1. Eden (Nintendo Switch)
* Mario Kart 8 Deluxe: Locked 55 to 60 FPS in 1080p docked mode, locked 60 FPS in 720p handheld mode with zero stability crashes.
* Display Pipeline: Android 16 IMapper5 stable-C SP-HAL gralloc backend (Patch 15), eliminating the 30 FPS swapchain limitation.
* Frequency Lock: Patch 17 gates the KGSL governor via KGSL_PROP_PWRCTRL while queues are active, keeping the GPU at peak operating frequency during emulation.
* In-Race Item Roulette Note: Static 2D HUD components (minimap, coin counter, lap counter, position rank, and item container outline) and 3D geometry render cleanly. The internal spinning item texture inside the top-left circle is currently undergoing subpass investigation.

### 2. Cemu (Nintendo Wii U)
* The Legend of Zelda: The Wind Waker HD: Solid 30 FPS rendering with zero vertical purple or black grid artifacts, resolved by setting the correct UBWC highest bank bit (15).

### 3. Azahar (Nintendo 3DS)
* The Legend of Zelda: Ocarina of Time 3D: Locked 30 FPS at 4x native resolution with 1080p high-resolution custom texture packs enabled.

---

## Architecture and Patch Stack

Built on upstream Mesa 27.0.0-devel pinned to commit 74920caaa0be, using Android NDK r29 targeting Platform SDK 36.

* Patches 01 & 15: u_gralloc UBWC detection and Android 16 IMapper5 SP-HAL loader.
* Patch 16: UBWC-compressed swapchain framebuffers.
* Patch 17: KGSL governor lock (KGSL_PROP_PWRCTRL) and autotune bandwidth tuning.
* Patches 30-37: Turnip-Z engine (mutable-format UBWC, optimized texture sampling, sysmem rendering).
* Patch 56 (56-fd722-blob.py): Dedicated Adreno 722 magic register table and has_lpac = False from vendor blob analysis.
* Patch 57 (57-fd722-duo.py): Duo hardware profile enforcement (highest_bank_bit = 15, cs_shared_mem_size = 32 KiB, num_ccu = 1, tile_align_h = 16). Builds fail automatically if drifted values are detected.

---

## Installation

1. Navigate to the Releases section of this repository.
2. Download Turnip-Duo-v5.1.zip (or latest recommended release).
3. Open your emulator of choice (Eden, Cemu, Azahar).
4. Navigate to GPU Driver Manager and install the .adpkg.zip package.

---

## Recommended Device Configuration

* Retroid Pocket Duo System Settings: Performance Mode set to Performance or Extreme; Fan Mode set to Sport or Smart to prevent thermal throttling.
* Eden Settings: Graphics Accuracy set to Normal, VSync Mailbox / FIFO Relaxed, Window Adapting Filter set to Bilinear.

---

## Credits and Licenses

* Mesa Freedreno Project: Mesa graphics development team.
* Base Patch Set: vauzi (sw branch).
* Adreno 722 Hardware Profiling and Validation: sherft2607, validated on retail Retroid Pocket Duo hardware.
