#!/usr/bin/env python3
"""FD722：改用外部独立逆向的 A722 设备条目（num_ccu=2 / tile_align_h=32 / hbb=16 + 其寄存器表）。

来源：Vauzi-17/710 的 A722 逆向（.rd cmdstream + cffdump 解码），
经 The412Banner/Banners-Turnip 的 patches/a710-720.py 分发。其说明称
"num_ccu = 2 ... tested on A720/A722 hardware"。

与本仓库 56 号补丁（Duo 自己的逆向，num_ccu=1 / tile_align_h=16 / hbb=15）相比：
  num_ccu          1  -> 2
  tile_align_h     16 -> 32
  highest_bank_bit 15 -> 16
  寄存器表 3 处取值不同：PC_MODE_CNTL(0x1f1f->0x3f)、UCHE_CACHE_WAYS(0x40004->0x0)、
  SP_UNKNOWN_AB01(0x0->0x1)，并补上 RB_RBP_CNTL。

这是一组"整套外部条目"的对照，不是单变量实验：用来回答
「Duo 那套保守参数 vs 外部那套实机验证过的参数，哪个更对」。
若出现花屏/横向条带，优先怀疑 highest_bank_bit 与 tile_align_h。

必须在本目录的 56-fd722-blob.py 之后运行（56 先建立 a722_raw_magic_regs 与 FD722 条目）。
幂等，可重复执行。
"""
import sys
from pathlib import Path

NAME = "61-adopt-external-a722-entry.py"
DEVICES = Path("src/freedreno/common/freedreno_devices.py")
MARKER = "FD722_VAUZI_ENTRY"
ANCHOR = "GPUId(chip_id=0x43020100"

REGS_NEW = r'''a722_raw_magic_regs = [
        [A6XXRegs.REG_A6XX_UCHE_CACHE_WAYS, 0x00000000],
        [A6XXRegs.REG_A6XX_TPL1_DBG_ECO_CNTL, 0x03000000],
        [A6XXRegs.REG_A6XX_TPL1_DBG_ECO_CNTL1, 0x00000700],

        [A6XXRegs.REG_A6XX_SP_CHICKEN_BITS, 0x00000400],
        [A6XXRegs.REG_A7XX_SP_CHICKEN_BITS_1, 0x01400400],
        [A6XXRegs.REG_A7XX_SP_CHICKEN_BITS_2, 0x00000010],
        [A6XXRegs.REG_A7XX_SP_CHICKEN_BITS_3, 0x00000000],

        [A6XXRegs.REG_A7XX_UCHE_UNKNOWN_0E10, 0x00000000],
        [A6XXRegs.REG_A7XX_UCHE_UNKNOWN_0E11, 0x00000000],
        [A6XXRegs.REG_A7XX_SP_HLSQ_DBG_ECO_CNTL, 0x00000000],
        [A6XXRegs.REG_A6XX_SP_DBG_ECO_CNTL, 0x11000000],

        [A6XXRegs.REG_A6XX_PC_MODE_CNTL, 0x0000003f],
        [A6XXRegs.REG_A6XX_PC_DBG_ECO_CNTL, 0x20100000],
        [A6XXRegs.REG_A7XX_PC_UNKNOWN_9E24, 0x01fc7f00],

        [A6XXRegs.REG_A7XX_VFD_DBG_ECO_CNTL, 0x00000000],
        [A6XXRegs.REG_A7XX_SP_ISDB_CNTL, 0x00000000],
        [A6XXRegs.REG_A7XX_SP_UNKNOWN_AE6A, 0x00000000],
        [A6XXRegs.REG_A7XX_SP_HLSQ_TIMEOUT_THRESHOLD_DP, 0x00000080],
        [A6XXRegs.REG_A7XX_SP_HLSQ_DBG_ECO_CNTL_1, 0x00000000],
        [A6XXRegs.REG_A7XX_SP_HLSQ_MODE_CNTL, 0x00000000],

        [A6XXRegs.REG_A7XX_SP_UNKNOWN_AB01, 0x00000001],
        [A6XXRegs.REG_A7XX_SP_UNKNOWN_AB22, 0x00000000],
        [A6XXRegs.REG_A7XX_SP_UNKNOWN_B310, 0x00000000],

        [A6XXRegs.REG_A7XX_SP_UNKNOWN_0CE2,   0x00000000],
        [A6XXRegs.REG_A7XX_SP_UNKNOWN_0CE2+1, 0x00000000],
        [A6XXRegs.REG_A7XX_SP_UNKNOWN_0CE4,   0x00000000],
        [A6XXRegs.REG_A7XX_SP_UNKNOWN_0CE4+1, 0x00000000],
        [A6XXRegs.REG_A7XX_SP_UNKNOWN_0CE6,   0x00000000],
        [A6XXRegs.REG_A7XX_SP_UNKNOWN_0CE6+1, 0x00000000],

        [A6XXRegs.REG_A7XX_GRAS_ROTATION_CNTL, 0x00000000],
        [A6XXRegs.REG_A6XX_GRAS_DBG_ECO_CNTL,  0x00000800],

        [A6XXRegs.REG_A7XX_RB_UNKNOWN_8E79, 0x00000000],
        [A6XXRegs.REG_A7XX_RB_LRZ_CNTL2, 0x00000000],
        [A6XXRegs.REG_A7XX_RB_CCU_DBG_ECO_CNTL, 0x00080000],
        [A6XXRegs.REG_A6XX_VPC_DBG_ECO_CNTL, 0x02000000],
        [A6XXRegs.REG_A6XX_UCHE_UNKNOWN_0E12, 0x03200000],

        # Were magic_regs (RB_DBG_ECO_CNTL / RB_RBP_CNTL = 0) before Mesa 17ca6174.
        [A6XXRegs.REG_A6XX_RB_RBP_CNTL,     0x0],
        [A6XXRegs.REG_A6XX_RB_DBG_ECO_CNTL, 0x0],
]'''

GPUS_NEW = r'''add_gpus([
        # FD722_VAUZI_ENTRY — 入口标记，勿删
        GPUId(chip_id=0x43020100, name="FD722"),
        GPUId(chip_id=0xffff43020100, name="FD722"),
    ], A6xxGPUInfo(
        CHIP.A7XX,
        [a7xx_base, a7xx_gen1],
        num_ccu = 2,
        tile_align_w = 64,
        tile_align_h = 32,
        tile_max_w = 1024,
        tile_max_h = 1024,
        num_vsc_pipes = 32,
        cs_shared_mem_size = 32 * 1024,
        wave_granularity = 2,
        fibers_per_sp = 128 * 2 * 16,
        highest_bank_bit = 16,
        raw_magic_regs = a722_raw_magic_regs,
    ))'''


def main():
    if not DEVICES.exists():
        print(f"{NAME}: WARNING {DEVICES} not found; skipped")
        return 0
    src = DEVICES.read_text(encoding="utf-8")

    if MARKER in src:
        print(f"{NAME}: already applied")
        return 0

    idx = src.find(ANCHOR)
    if idx < 0:
        print(f"{NAME}: WARNING FD722 entry not found (56-fd722-blob.py missing?); skipped")
        return 0

    # ---- 1. 换掉 add_gpus 设备块 ----
    start = src.rfind("add_gpus([", 0, idx)
    end = src.find("))", idx)
    if start < 0 or end < 0:
        print(f"{NAME}: WARNING cannot delimit FD722 add_gpus block; skipped")
        return 0
    end += 2
    out = src[:start] + GPUS_NEW + src[end:]

    # ---- 2. 换掉 a722_raw_magic_regs 寄存器表 ----
    r0 = out.find("a722_raw_magic_regs = [")
    if r0 < 0:
        print(f"{NAME}: WARNING a722_raw_magic_regs not found; skipped")
        return 0
    r1 = out.find(chr(10) + "]", r0)
    if r1 < 0:
        print(f"{NAME}: WARNING cannot delimit a722_raw_magic_regs; skipped")
        return 0
    out = out[:r0] + REGS_NEW + out[r1 + 2:]

    try:
        compile(out, str(DEVICES), "exec")
    except SyntaxError as e:
        print(f"{NAME}: FATAL syntax error after edit at line {e.lineno}: {e.msg}", file=sys.stderr)
        return 1

    DEVICES.write_text(out, encoding="utf-8")
    print(f"{NAME}: replaced FD722 entry (num_ccu=2 / tile_align_h=32 / hbb=16) + raw_magic_regs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
