#!/usr/bin/env python3
"""Turnip-Z port: cheaper texture sampling, split into two independent knobs.

v5.1 的做法只有一条：给普通采样器加正 LOD 偏置（04-tu-z-sampler-lodbias.patch，
TU_Z_TEXFAST=1 / TU_Z_LODBIAS=45），三线性过滤和各向异性都不动。

v6.0 的 32 号把三件事绑在一起（aniso=0、miplinear=false、LOD 偏置），
其中 miplinear=false 是 v5.1 没有的——三线性变「最近 mip」以后，mip 之间直接
跳变，远景草地/地面在运动时抖动、边缘发毛，看起来就是"锯齿严重"。画质代价
远大于省下的带宽，所以 v6.1 把它拆成三个开关：

  TU_Z_TEXFAST=1   总开关（默认开）。关掉则完全回到上游采样行为。
  TU_Z_LODBIAS=0   额外 LOD 偏置，单位 1/100。默认 0 = 不加偏置（画质等同上游）。
                   25~45 才是"省带宽换远景糊"的区间，自己按需往上调。
  TU_Z_TEXMIP=0    默认关。开成 1 才会 aniso=0 + miplinear=false（v6.0 的行为）。
                   只在确认某个游戏带宽卡死、且能接受 mip 跳变时才开。

三个变量都可以在 Eden 的驱动设置里现场覆盖，不用重出包。

Run from the Mesa source root. All edits are applied or none.
"""
import sys

NAME = "32-tu-z-texfast.py"
MARKER = "TU_Z_TEXMIP"
SAMPLER = "src/freedreno/vulkan/tu_sampler.cc"

EDITS = [
    (SAMPLER,
     '#include "tu_util.h"\n',
     '#include "tu_util.h"\n'
     '#include "util/u_debug.h"\n'
     '\n'
     '/* v6.1: quality-safe defaults. TU_Z_LODBIAS=0 and TU_Z_TEXMIP=0 mean the\n'
     ' * sampler is bit-identical to upstream unless the user opts in.\n'
     ' */\n'
     'DEBUG_GET_ONCE_BOOL_OPTION(tu_z_texfast, "TU_Z_TEXFAST", true)\n'
     'DEBUG_GET_ONCE_BOOL_OPTION(tu_z_texmip, "TU_Z_TEXMIP", false)\n'
     'DEBUG_GET_ONCE_NUM_OPTION(tu_z_lodbias, "TU_Z_LODBIAS", 0)\n',
     1),
    (SAMPLER,
     '   float max_lod = CLAMP(pCreateInfo->maxLod, 0.0f, 4095.0f / 256.0f);\n',
     '   float max_lod = CLAMP(pCreateInfo->maxLod, 0.0f, 4095.0f / 256.0f);\n'
     '   float lod_bias = pCreateInfo->mipLodBias;\n'
     '\n'
     '   if (debug_get_option_tu_z_texfast() && !pCreateInfo->compareEnable &&\n'
     '       !ycbcr_conversion && !pCreateInfo->unnormalizedCoordinates) {\n'
     '      /* Only with TU_Z_TEXMIP=1: nearest mip + no aniso. Costs visible mip\n'
     '       * popping on distant grass/terrain; off by default in v6.1.\n'
     '       */\n'
     '      if (debug_get_option_tu_z_texmip()) {\n'
     '         aniso = 0;\n'
     '         miplinear = false;\n'
     '      }\n'
     '      if (debug_get_option_tu_z_lodbias()) {\n'
     '         lod_bias = CLAMP(lod_bias + debug_get_option_tu_z_lodbias() / 100.0f,\n'
     '                          -16.0f, 15.99f);\n'
     '      }\n'
     '   }\n',
     1),
    (SAMPLER,
     '_TEX_SAMP_0_LOD_BIAS(pCreateInfo->mipLodBias)',
     '_TEX_SAMP_0_LOD_BIAS(lod_bias)',
     2),
]


def main():
    files = {}
    for path, _, _, _ in EDITS:
        if path not in files:
            try:
                files[path] = open(path, encoding="utf-8").read()
            except OSError as e:
                print(f"{NAME}: WARNING cannot read {path}: {e}; skipped")
                return 0
    if any(MARKER in s for s in files.values()):
        print(f"{NAME}: already applied")
        return 0
    for path, old, new, count in EDITS:
        found = files[path].count(old)
        if found != count:
            print(f"{NAME}: WARNING anchor matched {found}x (want {count}) in {path}; "
                  f"upstream changed, patch skipped")
            return 0
        files[path] = files[path].replace(old, new)
    for path, s in files.items():
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(s)
    print(f"{NAME}: applied (TU_Z_TEXFAST=1 gate, TU_Z_LODBIAS=0, TU_Z_TEXMIP=0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
