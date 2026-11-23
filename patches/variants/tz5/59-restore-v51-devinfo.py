#!/usr/bin/env python3
"""FD722: restore the v5.1 device entry, which is the one that measures fastest.

56-fd722-blob.py rebuilds the FD722 A6xxGPUInfo block from blob traces and, in
doing so, changes three things that v5.1 never did:

  1. enable_tp_ubwc_flag_hint = False
     The texture processor stops taking the UBWC flag hint. BWX/BWZ compressed
     fetches then fall back to the less compressed path, so texture reads cost
     more bandwidth. On a part with ~17 GB/s of LPDDR4X, in a texture-heavy
     title, this is the wrong direction. v5.1 leaves it at the upstream default
     (True).
  2. has_lpac = False
     No low-priority async compute queue. Harmless when nothing uses one, but
     it is not v5.1's value either.
  3. raw_magic_regs = a722_raw_magic_regs (a locally written block) instead of
     a730_raw_magic_regs, which is what v5.1 ships
     (legacy-patches/a722_duo_hbb15.patch). These are TPL1 / SP "chicken bit"
     style registers set once at context init; a wrong value here shows up as a
     framerate difference rather than as a visible artifact, which is exactly
     the failure mode being chased.

57-fd722-duo.py runs before this and rewrites the geometry to 2/32/16 so that
autotune may legitimately pick GMEM. This variant pins sysmem instead
(35b-a722-force-sysmem.py), and with sysmem the CCU geometry is close to inert
- num_ccu is multiplied into the colour/depth bin offsets inside GMEM, which is
not used at all. So the geometry goes back to the device values 1/16/15, which
is also what keeps the "1/16/15 + GMEM = UBWC corruption" warning from ever
applying.

Everything here is a compile-time value; there is no runtime override.

Run from the Mesa source root.
"""
import re
import sys

NAME = "59-restore-v51-devinfo.py"
TARGET = "src/freedreno/common/freedreno_devices.py"
MARKER = 'GPUId(chip_id=0x43020100, name="Adreno (TM) 722")'

REPL = [
    (r"\[a7xx_base, a7xx_gen1, GPUProps\([^)]*\)\]", "[a7xx_base, a7xx_gen1]"),
    (r"\bnum_ccu\s*=\s*\d+", "num_ccu = 1"),
    (r"\btile_align_h\s*=\s*\d+", "tile_align_h = 16"),
    (r"\bhighest_bank_bit\s*=\s*\d+", "highest_bank_bit = 15"),
    (r"\braw_magic_regs\s*=\s*a722_raw_magic_regs", "raw_magic_regs = a730_raw_magic_regs"),
]


def main():
    try:
        with open(TARGET, encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        print(f"{NAME}: {TARGET} not found - run from the Mesa source root")
        return 1

    i = src.find(MARKER)
    if i < 0:
        print(f"{NAME}: ERROR FD722 GPUId block not found (56-fd722-blob.py did not run?)")
        return 1

    start = src.find("A6xxGPUInfo(", i)
    end = src.find("\n    ))", start)
    if start < 0 or end < 0:
        print(f"{NAME}: ERROR could not delimit the FD722 A6xxGPUInfo block")
        return 1
    end += len("\n    ))")

    block = src[start:end]
    new = block
    for pat, rep in REPL:
        new = re.sub(pat, rep, new, count=1)

    changed = new != block
    if changed:
        src = src[:start] + new + src[end:]
        with open(TARGET, "w", encoding="utf-8", newline="\n") as f:
            f.write(src)

    got = {}
    for key, pat in (
        ("num_ccu", r"\bnum_ccu\s*=\s*(\d+)"),
        ("tile_align_h", r"\btile_align_h\s*=\s*(\d+)"),
        ("highest_bank_bit", r"\bhighest_bank_bit\s*=\s*(\d+)"),
    ):
        m = re.search(pat, new)
        got[key] = int(m.group(1)) if m else None
    props = "GPUProps" in new
    magic = "a730_raw_magic_regs" if "raw_magic_regs = a730_raw_magic_regs" in new else "?"

    print(f"{NAME}: {'applied' if changed else 'no-change'} - "
          f"num_ccu={got['num_ccu']} tile_align_h={got['tile_align_h']} "
          f"hbb={got['highest_bank_bit']} raw_magic_regs={magic} "
          f"GPUProps={'yes' if props else 'none'}")

    if props or magic != "a730_raw_magic_regs":
        print(f"{NAME}: ERROR device entry is not in v5.1 shape")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
