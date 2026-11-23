#!/usr/bin/env python3
"""FD722 (Retroid Pocket Duo): default every render pass to system memory.

This reinstates the v5.1 behaviour (legacy-patches/a722-sysmem.patch), which
v6.0/v6.1 dropped. On the Duo it is not a tuning preference, it is the fastest
setting measured on the device:

  * A722 has 1 MiB of GMEM. A 1080p colour+depth pass does not fit, so the
    driver splits it into many bins; every bin then loads its tile from DDR
    and stores it back, and the bin overhead (visibility stream, restore,
    resolve) is paid per bin. When the pass is small enough to fit, GMEM wins;
    at 1080p on this part it loses.
  * v5.1 pinned sysmem in three places (this hook, TU_Z_SYSMEM_ONLY and
    tu_autotune's PREFER_SYSMEM) and that is the build that reaches the
    framerates the user compares against.
  * v6.1 removed all three and let tu_autotune::get_optimal_mode() choose.
    Measured result: lower framerate than v5.1 on the same scene.

TU_Z_FORCE_GMEM=1 puts the old choice back at runtime, so the two paths can be
compared without rebuilding. TU_DEBUG=gmem still wins over this hook because
the TU_DEBUG check runs earlier in use_sysmem_rendering().

Run from the Mesa source root.
"""
import sys

NAME = "35b-a722-force-sysmem.py"
TARGET = "src/freedreno/vulkan/tu_cmd_buffer.cc"
CHIP = "0x43020100"

ANCHOR = """   /* can't fit attachments into gmem */
   if (!cmd->state.tiling->possible) {"""

INSERT = """   /* WN-Turnip: Adreno 722 (Retroid Pocket Duo). 1 MiB of GMEM cannot hold a
    * 1080p pass, so binning costs more than it saves - keep colour and depth in
    * system memory, which is what v5.1 does and what measures fastest here.
    * TU_Z_FORCE_GMEM=1 opts back into the autotune / GMEM path.
    */
   if ((cmd->device->physical_device->dev_id.chip_id & 0xffffffff) == CHIP_ID &&
       !debug_get_bool_option("TU_Z_FORCE_GMEM", false)) {
      cmd->state.rp.force_render_mode_reason = "Adreno 722 sysmem default";
      return true;
   }

""".replace("CHIP_ID", CHIP)


def main():
    try:
        with open(TARGET, encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        print(f"{NAME}: {TARGET} not found - run from the Mesa source root")
        return 1

    if "TU_Z_FORCE_GMEM" in src:
        print(f"{NAME}: already applied")
        return 0

    if src.count(ANCHOR) != 1:
        print(f"{NAME}: ERROR anchor found {src.count(ANCHOR)} times, expected 1")
        return 1

    src = src.replace(ANCHOR, INSERT + ANCHOR, 1)

    with open(TARGET, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)

    print(f"{NAME}: applied - chip {CHIP} now defaults to sysmem rendering "
          f"(TU_Z_FORCE_GMEM=1 restores GMEM)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
