#!/usr/bin/env python3
"""可选：把 FD722 的 cs_shared_mem_size 从 32 KiB 提到 64 KiB。

为什么这可能对 Eden 有用
------------------------
`cs_shared_mem_size` 在 Turnip 里只有一个用途（tu_device.cc:1246）：

    props->maxComputeSharedMemorySize = pdevice->info->cs_shared_mem_size;

它就是报给应用的「单个 compute workgroup 能用多少 shared memory」上限。
Eden 在 GPU 侧解码 ASTC / 转码 BCn 时走的就是 compute，workgroup 开多大受这个
上限约束。32 KiB 是 A6xx 的档位，A7xx 实际支持到 64 KiB，这里 32 KiB 更像是
从 a6xx 继承下来没改。

它不占 GMEM（Autotune 不用它算 tile 预算），所以代价基本为零——但它**只是抬高
一个查询上限**，Eden 是否因此变大 workgroup，取决于 Eden 自己的启发式。
也就是说：这是一条「可能有用、但极可能零变化」的改动。

为什么默认不启用
----------------
因为它和「A722 显存模式/几何参数对不对」不是同一个问题。一次只验一个变量。

怎么启用
--------
    mkdir -p patches/variants/tzcs64
    cp patches/variants/tzeden/* patches/variants/tzcs64/
    cp patches-optional/62-cs-shared-64k.py patches/variants/tzcs64/
    echo "cs_shared_mem 64K" > patches/variants/tzcs64/DESCRIPTION
然后在 Actions 里把 variants 写成 `tzeden tzcs64`，两个包只差这一项。

必须在 56-fd722-blob.py 之后运行（FD722 条目由它建立）。幂等。
"""
import re
import sys

NAME = "62-cs-shared-64k.py"
DEVICES = "src/freedreno/common/freedreno_devices.py"
MARKER = "GPUId(chip_id=0x43020100"
END = "\n    ))"
OLD = "cs_shared_mem_size = 32 * 1024,"
NEW = "cs_shared_mem_size = 64 * 1024,"


def fail(msg):
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
    if NEW in block:
        print(f"{NAME}: already applied")
        return 0
    if OLD not in block:
        # 上游把字面量改成了别的写法（比如 32*1024 无空格），不要静默跳过
        return fail(f"'{OLD}' not found in the FD722 block; upstream changed the literal")

    # 必须正好一处，否则说明 FD722 块里有多个字段被写成了同一字面量
    if block.count(OLD) != 1:
        return fail(f"'{OLD}' appears {block.count(OLD)}x in the FD722 block, expected 1")

    new_block = block.replace(OLD, NEW)
    open(DEVICES, "w", encoding="utf-8", newline="\n").write(src[:start] + new_block + src[end:])
    print(f"{NAME}: applied (FD722 cs_shared_mem_size 32K -> 64K)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
