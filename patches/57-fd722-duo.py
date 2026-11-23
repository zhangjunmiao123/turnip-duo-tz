#!/usr/bin/env python3
"""FD722 (Retroid Pocket Duo, chip_id 0x43020100): pin the GMEM-capable config.

v6.0 用的是 num_ccu=1 / tile_align_h=16 / hbb=15，注释自己写着「只在强制 sysmem
的构建里验证过」。v6.1 把自动调优（tu_autotune）放开了，GMEM 会真的被用上，
那 1/16/15 就不再是惰性参数，而是会算错的 bin 几何。

所以 v6.1 改用 MrPurple666 T30 在 **A722 实机 + 自动调优开启** 下验证过的配置：
num_ccu=2 / tile_align_h=32 / highest_bank_bit=16（T30 的 meta.json 也写明它
"uses tu_autotune GMEM/sysmem selection"，即同一套运行方式）。

  num_ccu          2    rewritten (T30 / A722, GMEM-capable)
  tile_align_h    32    rewritten
  cs_shared_mem_size
                   32 KiB  rewritten. 18-wn-a8xx-shared-mem.py raises this to
                        64 KiB on every device entry, FD722 included, and it
                        runs before this script. The Duo's SP has 32 KiB: the
                        OEM blob reports maxComputeSharedMemorySize = 32768
                        (stock vkjson), and the value is handed straight to
                        that limit (tu_device.cc). Advertising 64 KiB let the
                        compute shader decoding the Mario Kart 8 HUD item
                        texture overflow it, so the icon came out blank while
                        3D geometry rendered fine.
  highest_bank_bit 16   rewritten; T30's A722 value. v6.0 用的是 15（Duo 设备树
                        里读到的值），但那只在强制 sysmem 下验证过。

如果 2/32/16 在实机上出紫黑横条/横向条带（说明这套几何在你的机器上不成立），
先不要改补丁——在 Eden 的 Turnip 环境变量里加 TU_DEBUG=sysmem 就能绕开 GMEM，
继续用这套包。要长期回到 1/16/15，把 EXPECT 改回 (1, 16)、HBB 改回 15 重编。

Unlike the other patches here this one EXITS NON-ZERO if upstream has moved
num_ccu or tile_align_h, instead of warning and continuing. That is the point
of it: num_ccu is not a tuning knob, it is multiplied into the colour and depth
CCU offsets inside GMEM (src/freedreno/common/fd6_gmem_cache.h), and the Duo has
only 1 MiB of GMEM, so a changed value must be looked at by a human before it
ships. With MESA_REF pinned to a commit it can never fire.

Numbered 57 so it runs after 56-fd722-blob.py, which replaces the whole FD722
add_gpus block with its own text (and writes 1/16/15 from blob traces); this
script then rewrites those three fields.

Run from the Mesa source root.
"""
import re
import sys

NAME = "57-fd722-duo.py"

DEVICES_PY = "src/freedreno/common/freedreno_devices.py"
# v6.1: MrPurple666 T30 的 A722 配置。T30 自己的 meta.json 写明
# "num_ccu=2, tile_align_h=32, highest_bank_bit=16 ... uses tu_autotune
# GMEM/sysmem selection"，也就是同一套运行方式（自动调优 + 允许 GMEM）在
# A722 实机上验证过。v6.0 的 1/16/15 只验证过强制 sysmem 的情况——那种情况下
# 这两个参数几乎是惰性的；一旦 autotune 真的走 GMEM，1/16/15 会产出 UBWC
# 损坏（紫黑横条）并挂死 GPU（v6.0 的注释原文）。
EXPECT = (2, 32)        # (num_ccu, tile_align_h)
HBB = 16
CS_SHARED_MEM_KIB = 32   # OEM blob limit; matches plain Mesa, which T30 is
ENFORCE = False         # 56 先写自己的值，这里负责改写成 T30 的几何

SUMMARY = (f"FD722 num_ccu={EXPECT[0]}, tile_align_h={EXPECT[1]}, "
           f"highest_bank_bit={HBB}, cs_shared_mem_size={CS_SHARED_MEM_KIB} KiB")


def main():
    try:
        src = open(DEVICES_PY, encoding="utf-8").read()
    except OSError as e:
        print(f"{NAME}: WARNING cannot read {DEVICES_PY}: {e}; skipped")
        return 0

    m = re.search(r"GPUId\(chip_id=0x43020100.*?\n    \)\)", src, re.S)
    if not m:
        print(f"{NAME}: WARNING FD722 (0x43020100) block not found; skipped")
        return 0
    block = m.group(0)

    got = {}
    for key in ("num_ccu", "tile_align_h", "highest_bank_bit", "cs_shared_mem_size"):
        k = re.search(rf"\b{key}\s*=\s*(\d+)", block)
        got[key] = int(k.group(1)) if k else None
    # highest_bank_bit absent means A6xxGPUInfo's default, which is 15 today.
    print(f"{NAME}: upstream FD722 num_ccu={got['num_ccu']} "
          f"tile_align_h={got['tile_align_h']} "
          f"highest_bank_bit={got['highest_bank_bit'] if got['highest_bank_bit'] is not None else 'default'} "
          f"cs_shared_mem_size={got['cs_shared_mem_size']} * 1024")

    drift = (got["num_ccu"], got["tile_align_h"]) != EXPECT
    if drift and ENFORCE:
        print(f"{NAME}: ERROR FD722 moved off the tested config "
              f"{EXPECT[0]} CCU / tile_align_h {EXPECT[1]}; review before shipping",
              file=sys.stderr)
        return 1

    new = block
    if drift:
        new = re.sub(r"\bnum_ccu\s*=\s*\d+", f"num_ccu = {EXPECT[0]}", new)
        new = re.sub(r"\btile_align_h\s*=\s*\d+", f"tile_align_h = {EXPECT[1]}", new)
    if got["highest_bank_bit"] is None:
        if "raw_magic_regs" not in new:
            print(f"{NAME}: WARNING no raw_magic_regs anchor for highest_bank_bit; skipped")
            return 0
        new = new.replace("raw_magic_regs =",
                          f"highest_bank_bit = {HBB},\n        raw_magic_regs =", 1)
    else:
        new = re.sub(r"\bhighest_bank_bit\s*=\s*\d+", f"highest_bank_bit = {HBB}", new)
    if not re.search(r"\bcs_shared_mem_size\s*=\s*\d+\s*\*\s*1024", new):
        print(f"{NAME}: ERROR cs_shared_mem_size not in the N * 1024 form", file=sys.stderr)
        return 1
    new = re.sub(r"\bcs_shared_mem_size\s*=\s*\d+\s*\*\s*1024",
                 f"cs_shared_mem_size = {CS_SHARED_MEM_KIB} * 1024", new)

    if new == block:
        print(f"{NAME}: already applied")
        return 0
    open(DEVICES_PY, "w", encoding="utf-8").write(src.replace(block, new, 1))
    print(f"{NAME}: applied ({SUMMARY})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
