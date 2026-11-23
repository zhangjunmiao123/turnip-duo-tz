#!/usr/bin/env python3
"""离线校验：这些补丁还能不能打在指定的 Mesa 源码上。

用途：改 mesa_ref、加新补丁、或者上游重构之后，先在这里跑一遍，
     不用等 CI 跑完 30 分钟才发现某个补丁静默 no-change。

用法（Windows / Linux 都行，只要有 python3）：
    python tools/verify_anchors.py --mesa ../mesa            # 整个 Mesa 检出
    python tools/verify_anchors.py --mesa mesa_ref           # 只放了几个文件的目录

它把 patches/ 和 patches/variants/*/ 里的 .py 补丁按构建顺序模拟执行
（只在内存里改文本，不写任何文件），报告每个锚点命中几次。
锚点命中数 != 期望值时，构建脚本会静默跳过那个补丁 —— 那就是这里要抓的东西。
"""
import argparse
import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH_DIR = ROOT / "patches"


def load_edits(path):
    """取出补丁脚本声明要做的文本替换，不执行它自己的 main()。

    有些补丁在模块层直接调用 main()/sys.exit(main())，所以先把这类
    顶层语句从 AST 里剔掉再 exec —— 否则校验会真的去改源文件。
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))

    def is_entry(node):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            return name in ("main", "exit", "run_all", "run")
        return False

    tree.body = [n for n in tree.body if not is_entry(n)]
    ns = {"__name__": "patchmod", "__file__": str(path)}
    exec(compile(tree, str(path), "exec"), ns)
    edits = ns.get("EDITS")
    if edits is None and "OLD" in ns:
        target = ns.get("IMAGE") or ns.get("AUTOTUNE") or ns.get("TARGET")
        edits = [(target, ns["OLD"], ns["NEW"], 1)]
    return edits or []


def active_py(folder):
    """构建设置只应用 .py/.sh/.patch/.diff，其它后缀（含 .off）忽略。"""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix in (".py", ".sh"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesa", required=True, help="Mesa 源码根目录（含 src/freedreno）")
    args = ap.parse_args()
    mesa = Path(args.mesa).resolve()
    full_tree = (mesa / "src" / "freedreno").is_dir()
    flat = any(mesa.glob("*.cc")) or any(mesa.glob("*.py"))
    if not (full_tree or flat):
        sys.exit(f"{mesa} 既不是 Mesa 检出，也不是放了源文件的平铺目录")

    texts = {}
    bad = []

    def load_file(rel):
        if rel not in texts:
            f = mesa / rel
            if f.exists():
                texts[rel] = f.read_text(encoding="utf-8")
            else:
                # 允许只放部分文件的目录：按文件名在 mesa 下递归找
                hit = next(iter(mesa.rglob(os.path.basename(rel))), None)
                texts[rel] = hit.read_text(encoding="utf-8") if hit else None
        return texts[rel]

    order = [("common", p) for p in active_py(PATCH_DIR)]
    vroot = PATCH_DIR / "variants"
    variants = sorted(d for d in vroot.iterdir() if d.is_dir()) if vroot.is_dir() else []
    for v in variants:
        order += [(v.name, p) for p in active_py(v)]

    print(f"Mesa: {mesa}")
    print(f"{'variant':10} {'patch':34} {'file':22} {'want':>4} {'found':>5}  verdict")
    print("-" * 96)
    current = None
    for variant, path in order:
        # 每个变体都是从干净 Mesa 树开始构建的，模拟状态必须跟着重置
        if variant != current:
            texts.clear()
            current = variant
        if path.suffix != ".py":
            print(f"{variant:10} {path.name:34} {'(.patch/.sh)':22} {'-':>4} {'-':>5}  not simulated")
            continue
        try:
            edits = load_edits(path)
        except (OSError, SystemExit):
            # 20-default-env.py / 15 / 16 / 17 这类脚本在模块层就要读写真实文件，
            # 平铺目录模拟不了，交给 CI 的 patches-<variant>.txt 去确认
            print(f"{variant:10} {path.name:34} {'(module-level IO)':22} {'-':>4} {'-':>5}  not simulated")
            continue
        except Exception as e:  # noqa: BLE001
            print(f"{variant:10} {path.name:34} {'-':22} {'-':>4} {'-':>5}  cannot load: {e}")
            bad.append((variant, path.name, "load error"))
            continue
        for rel, old, new, count in edits:
            if not rel:
                print(f"{variant:10} {path.name:34} {'?':22} {count:4} {'-':>5}  no target path")
                bad.append((variant, path.name, "no target path"))
                continue
            txt = load_file(rel)
            base = os.path.basename(rel)
            if txt is None:
                print(f"{variant:10} {path.name:34} {base:22} {count:4} {'--':>5}  file not found")
                bad.append((variant, path.name, "missing file"))
                continue
            if new in txt and old not in txt:
                print(f"{variant:10} {path.name:34} {base:22} {count:4} {'-':>5}  already applied")
                continue
            found = txt.count(old)
            if found == count:
                texts[rel] = txt.replace(old, new)
                print(f"{variant:10} {path.name:34} {base:22} {count:4} {found:5}  OK")
            else:
                print(f"{variant:10} {path.name:34} {base:22} {count:4} {found:5}  ANCHOR MISS")
                bad.append((variant, path.name, f"{found} != {count}"))

    print("-" * 96)
    if bad:
        print("会被静默跳过的补丁：")
        for v, n, why in bad:
            print(f"  - [{v}] {n}: {why}")
        return 1
    print("全部锚点命中。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
