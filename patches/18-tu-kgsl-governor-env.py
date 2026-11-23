#!/usr/bin/env python3
"""Keep the GPU governor off while our queue is open — but switchable at runtime.

v5.1 里有这条（legacy-patches/tu-kgsl-governor-off-env.patch，默认开）；v6.0 把它
塞进了 17 号脚本的 p2 分支，并且因为 BUILD_VARIANT 回退成 "p2"，所有变体都被
无提示地打开了。行为本身不算错（关掉 KGSL governor 后 GPU 钉在最高频），
但它和「帧数更低」这个现象有直接关系：持续满频会让机身先热起来，热到阈值后
系统 thermal 降频，长测下来的稳态帧数反而掉。所以它必须是一个**运行时**开关，
而不是编译期常量。

  TU_KGSL_GOVERNOR_OFF=1  默认。关掉 governor，GPU 钉最高频（v5.1 行为）
  TU_KGSL_GOVERNOR_OFF=0  交回系统 governor，按负载调频；机身更凉，长测更稳

测法：同一款游戏跑满 10 分钟，分别在 1 和 0 下记第 8~10 分钟的稳态帧数。
短测（2 分钟）几乎总是 1 更高，长测才看得出差别。

Run from the Mesa source root. All edits are applied or none.
"""
import sys

NAME = "18-tu-kgsl-governor-env.py"
MARKER = "kgsl_z_governor_off"
KGSL = "src/freedreno/vulkan/tu_knl_kgsl.cc"

HELPER = r'''DEBUG_GET_ONCE_BOOL_OPTION(kgsl_z_governor_off, "TU_KGSL_GOVERNOR_OFF", true)

static int kgsl_z_governor_off_queues;

static void
kgsl_z_set_governor(int fd, unsigned int enable)
{
   struct kgsl_device_getproperty prop = {
      .type = KGSL_PROP_PWRCTRL,
      .value = (void *)&enable,
      .sizebytes = sizeof(enable),
   };

   if (safe_ioctl(fd, IOCTL_KGSL_SETPROPERTY, &prop)) {
      mesa_logw("kgsl: failed to %s the GPU governor via KGSL_PROP_PWRCTRL: %s",
                enable ? "re-enable" : "disable", strerror(errno));
   }
}

'''

EDITS = [
    (KGSL,
     'static int\nkgsl_submitqueue_new(struct tu_device *dev, struct tu_queue *queue)\n{\n',
     HELPER +
     'static int\nkgsl_submitqueue_new(struct tu_device *dev, struct tu_queue *queue)\n{\n',
     1),
    (KGSL,
     '   queue->msm_queue_id = req.drawctxt_id;\n\n   return 0;\n}',
     '   queue->msm_queue_id = req.drawctxt_id;\n'
     '\n'
     '   if (debug_get_option_kgsl_z_governor_off() &&\n'
     '       p_atomic_inc_return(&kgsl_z_governor_off_queues) == 1)\n'
     '      kgsl_z_set_governor(dev->physical_device->local_fd, 0);\n'
     '\n'
     '   return 0;\n'
     '}',
     1),
    (KGSL,
     '   safe_ioctl(dev->physical_device->local_fd, IOCTL_KGSL_DRAWCTXT_DESTROY, &req);\n'
     '}\n',
     '   safe_ioctl(dev->physical_device->local_fd, IOCTL_KGSL_DRAWCTXT_DESTROY, &req);\n'
     '\n'
     '   if (debug_get_option_kgsl_z_governor_off() &&\n'
     '       p_atomic_dec_return(&kgsl_z_governor_off_queues) == 0)\n'
     '      kgsl_z_set_governor(dev->physical_device->local_fd, 1);\n'
     '}\n',
     1),
]


def main():
    try:
        src = open(KGSL, encoding="utf-8").read()
    except OSError as e:
        print(f"{NAME}: WARNING cannot read {KGSL}: {e}; skipped")
        return 0

    if MARKER in src:
        print(f"{NAME}: already applied")
        return 0

    # 17 号（p/p1/p2 变体）用的是另一个符号名，同一处代码块；它先跑的话这里
    # 的锚点就不存在了。此时安静跳过，不要刷 WARNING。
    if "wnturnip_set_pwrctrl_enabled" in src:
        print(f"{NAME}: p2 perf variant already owns the governor switch; skipped")
        return 0

    # 需要 p_atomic_* 与 debug_get_option_*
    if '"util/u_debug.h"' not in src:
        print(f"{NAME}: WARNING util/u_debug.h is not included by {KGSL}; skipped")
        return 0

    for path, old, new, count in EDITS:
        found = src.count(old)
        if found != count:
            print(f"{NAME}: WARNING anchor matched {found}x (want {count}) in {path}; "
                  f"upstream changed, patch skipped")
            return 0
        src = src.replace(old, new, 1)

    with open(KGSL, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    print(f"{NAME}: applied (TU_KGSL_GOVERNOR_OFF default 1, runtime switchable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
