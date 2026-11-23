#!/usr/bin/env python3
"""tzccu2: switch the FD722 descriptor to num_ccu = 2 / tile_align_h = 32.

57-fd722-duo.py pins the Duo profile to (1, 16). The other pipeline in this
repository (build-turnip.yml) uses (2, 32) for the same GPU, so one of the two
is wrong. This script only flips those two numbers and touches nothing else,
so the resulting zip differs from tzqual in exactly one variable.

Both values are written into the colour/depth bin geometry, so a wrong value
costs either half the binning parallelism (num_ccu too low) or visible bin
banding (tile_align_h wrong). Test, do not guess.

Run from the Mesa source root. Idempotent, safe to rerun.
"""
import re
import sys

NAME = "60-ccu2-duo.py"
SUMMARY = "tzccu2: FD722 num_ccu=2, tile_align_h=32 (A/B against the v5.1 1/16 profile)"
DEVICES = "src/freedreno/common/freedreno_devices.py"
MARKER = "GPUId(chip_id=0x43020100"
END = "\n    ))"
CCU = 2
ALIGN_H = 32


def fail(msg):
    """A no-op here would ship a zip identical to tzqual, so fail the build."""
    print(f"{NAME}: ERROR {msg}", file=sys.stderr)
    return 1


def main():
    try:
        src = open(DEVICES, encoding="utf-8").read()
    except OSError as e:
        return fail(f"cannot read {DEVICES}: {e}")

    start = src.find(MARKER)
    if start < 0:
        return fail("FD722 block not found (56-fd722-blob.py missing?)")
    end = src.find(END, start)
    if end < 0:
        return fail("end of FD722 block not found")
    end += len(END)

    block = src[start:end]
    if f"num_ccu = {CCU}," in block and f"tile_align_h = {ALIGN_H}," in block:
        print(f"{NAME}: already applied")
        return 0

    new = re.sub(r"\bnum_ccu\s*=\s*\d+", f"num_ccu = {CCU}", block)
    new = re.sub(r"\btile_align_h\s*=\s*\d+", f"tile_align_h = {ALIGN_H}", new)
    if new == block:
        return fail("neither value present in the FD722 block")

    open(DEVICES, "w", encoding="utf-8", newline="\n").write(src[:start] + new + src[end:])
    got_ccu = re.search(r"\bnum_ccu\s*=\s*(\d+)", new).group(1)
    got_align = re.search(r"\btile_align_h\s*=\s*(\d+)", new).group(1)
    print(f"{NAME}: applied (FD722 num_ccu={got_ccu}, tile_align_h={got_align})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
