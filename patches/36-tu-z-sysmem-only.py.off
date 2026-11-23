#!/usr/bin/env python3
"""【v6.1 已停用，改名为 .off】原因见下，保留文件只为留档。

为什么停用：PREFER_SYSMEM 在 tu_autotune::get_optimal_mode() 里是**提前返回**
（tu_autotune.cc 里 `early_return_mode` 那一支），也就是说它不是"倾向"，而是
"所有 render pass 一律走系统内存"。Adreno 722 只有 1 MiB GMEM，1080p 一帧本来
就该切多 bin；但把整帧颜色/深度全部压到 DDR 上，在 Duo 这种带宽 ~17 GB/s、
双屏 120Hz 还要扣掉 1.58 GB/s 的机器上，是纯粹的反向优化。荒野之息这类高
overdraw 场景掉帧最明显。

更重要的是：上游本来就有**运行时**开关 `TU_AUTOTUNE_ALGO`（bandwidth /
profiled / profiled_imm / prefer_sysmem / prefer_gmem），在 tu_autotune.cc 的
get_env_config() 里解析。所以想要 v5.1 那种强制 sysmem，只要在 Eden 的 Turnip
环境变量里写 `TU_AUTOTUNE_ALGO=prefer_sysmem` 即可，不需要在编译期钉死。

v6.1 因此回到上游默认（BANDWIDTH，按估算带宽逐个 render pass 自己选），
把选择权交给运行时。

--- 以下为原文件内容（已停用）---

Default tu_autotune algorithm to PREFER_SYSMEM on Adreno 722 (1 MiB GMEM).

In upstream Mesa, tu_autotune::algorithm::PREFER_SYSMEM:
1. Still honors all GMEM-required paths in tu_autotune::get_optimal_mode():
   - sysmem_single_prim_mode (subpass feedback loops) -> GMEM
   - pass->has_fdm (fragment density map) -> GMEM
   - pass->has_msrtss (multisampled render to single sampled) -> GMEM
2. Uses SYSMEM for normal 1080p render passes so the 1 MiB GMEM on Adreno 722
   does not thrash into multi-bin tiling passes.
3. Leaves tu6_init_static_regs() and emit_rb_ccu_cntl() 100% unmodified upstream Mesa.
"""
import sys

NAME = "36-tu-z-sysmem-only.py"
AUTOTUNE = "src/freedreno/vulkan/tu_autotune.cc"

OLD = "   DEFAULT = BANDWIDTH, /* Default algorithm, used if no other is specified. */\n"
NEW = "   DEFAULT = PREFER_SYSMEM, /* Default algorithm for Adreno 722 1 MiB GMEM. */\n"


def main():
    try:
        s = open(AUTOTUNE, encoding="utf-8").read()
    except OSError as e:
        print(f"{NAME}: WARNING cannot read {AUTOTUNE}: {e}; skipped")
        return 0

    if NEW in s:
        print(f"{NAME}: already applied")
        return 0

    if s.count(OLD) != 1:
        print(f"{NAME}: WARNING anchor matched {s.count(OLD)}x in {AUTOTUNE}; skipped")
        return 0

    s = s.replace(OLD, NEW, 1)
    with open(AUTOTUNE, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)

    print(f"{NAME}: applied (tu_autotune DEFAULT = PREFER_SYSMEM)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
