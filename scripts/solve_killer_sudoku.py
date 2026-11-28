"""杀手数独求解器 —— 入口脚本。

职责解耦架构：
  killer_sudoku.core     常量与预计算（与应用无关）
  killer_sudoku.layout   布局解析、别名归一化、校验
  killer_sudoku.solver   求解器（AC-3 + MRV + 子集和剪枝）
  killer_sudoku.diagnose 秩诊断、innies/outies、矛盾定位
  killer_sudoku.image    外框检测、虚线边界检测、并查集重建笼
  killer_sudoku.ocr      tesseract/模板匹配 和值 OCR
  killer_sudoku.render   文本/图片渲染

运行：
  python3 scripts/solve_killer_sudoku.py --inline "22:a1,a2,a3,b3; ..."
  python3 scripts/solve_killer_sudoku.py --file layout.txt --explain
  python3 scripts/solve_killer_sudoku.py --image-auto puzzle.jpg
  python3 scripts/solve_killer_sudoku.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from killer_sudoku import (
    KillerSudokuSolver,
    format_grid,
    max_sum,
    min_sum,
)
from killer_sudoku.layout import (
    load_layout,
    validate,
)
from killer_sudoku.diagnose import (
    innies_outies,
    sum_only_diagnostics,
)
from killer_sudoku.image import (
    detect_cages_from_image,
    detect_grid,
)
from killer_sudoku.ocr import cages_with_sums, recognize_digits
from killer_sudoku.render import parse_grid_spec, render_solution


SELFTEST_LAYOUT = [
    (22, ["a1", "a2", "a3", "b3"]),
    (13, ["a4", "a5"]),
    (13, ["a6", "b6", "b7"]),
    (12, ["a7", "a8", "a9"]),
    (13, ["b1", "c1", "d1"]),
    (12, ["b2", "c2"]),
    (3, ["b4", "b5"]),
    (11, ["b8", "c8"]),
    (13, ["b9", "c9"]),
    (14, ["c3", "c4", "c5"]),
    (12, ["c6", "d6"]),
    (21, ["c7", "d7", "d8"]),
    (14, ["d2", "e1", "e2"]),
    (17, ["d3", "d4", "e3"]),
    (17, ["d5", "e4", "e5"]),
    (8, ["d9", "e8", "e9"]),
    (10, ["e6", "e7"]),
    (18, ["f1", "g1", "g2"]),
    (6, ["f2", "f3"]),
    (26, ["f4", "g3", "g4", "h4"]),
    (4, ["f5", "f6"]),
    (11, ["f7", "g7"]),
    (13, ["f8", "g8"]),
    (26, ["f9", "g9", "h9", "i9"]),
    (16, ["g5", "g6", "h5"]),
    (10, ["h1", "i1"]),
    (7, ["h2", "h3"]),
    (6, ["h6", "i6"]),
    (6, ["h7", "h8"]),
    (15, ["i2", "i3"]),
    (8, ["i4", "i5"]),
    (8, ["i7", "i8"]),
]

SELFTEST_ANSWER = [
    [4, 6, 7, 5, 8, 3, 9, 1, 2],
    [8, 9, 5, 1, 2, 6, 4, 3, 7],
    [2, 3, 1, 4, 9, 7, 5, 8, 6],
    [3, 8, 6, 2, 4, 5, 7, 9, 1],
    [5, 1, 9, 6, 7, 8, 2, 4, 3],
    [7, 2, 4, 9, 3, 1, 8, 6, 5],
    [6, 5, 2, 8, 1, 9, 3, 7, 4],
    [9, 4, 3, 7, 6, 2, 1, 5, 8],
    [1, 7, 8, 3, 5, 4, 6, 2, 9],
]


def run_selftest() -> int:
    errors, warnings = validate(SELFTEST_LAYOUT)
    if errors:
        print("自检失败：布局校验不通过", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 1
    solver = KillerSudokuSolver(SELFTEST_LAYOUT, max_solutions=2)
    sols = solver.solve()
    if len(sols) != 1:
        print(f"自检失败：期望唯一解，实际 {len(sols)} 个", file=sys.stderr)
        return 1
    got = [sols[0][r * 9:(r + 1) * 9] for r in range(9)]
    if got != SELFTEST_ANSWER:
        print("自检失败：解与预期不一致", file=sys.stderr)
        print(format_grid(sols[0]), file=sys.stderr)
        return 1
    eq, rank, dof = sum_only_diagnostics(SELFTEST_LAYOUT)
    # 验证 AC-3 预处理和基础求解都能工作
    solver_no_ac3 = KillerSudokuSolver(SELFTEST_LAYOUT, max_solutions=2, enable_ac3=False)
    sols2 = solver_no_ac3.solve()
    if len(sols2) != 1:
        print("自检失败：禁用 AC-3 后无解", file=sys.stderr)
        return 1
    print("自检通过：唯一解与预期一致（AC-3 已启用）")
    print(f"搜索节点: {solver.nodes}")
    print(f"仅求和诊断: 方程 {eq} 条，秩 {rank}，自由度 {dof}")
    print(f"AC-3 关闭时节点: {solver_no_ac3.nodes}")
    return 0


# ---------------------------------------------------------------------------
# 矛盾定位诊断：NO_SOLUTION 时找最可疑的笼
# ---------------------------------------------------------------------------
def diagnose_no_solution(layout) -> list[str]:
    """当求解器返回 NO_SOLUTION 时，找出最可疑的若干笼。"""
    solver = KillerSudokuSolver(layout, max_solutions=1, node_limit=50_000)
    solver.enable_ac3 = False
    solver.solve()  # 跑一遍看节点数
    nodes_full = solver.nodes

    suspicious: list[tuple[int, str, int]] = []
    for i in range(len(layout)):
        s, cells = layout[i]
        lo, hi = min_sum(len(cells)), max_sum(len(cells))
        # 先检查这个笼的和值是不是本身可行范围
        import re
        from killer_sudoku.core import ALL, can_form
        if not can_form(ALL, len(cells), s):
            suspicious.append((i, f"笼 {cells[0]} 和值 {s} 超出 {lo}..{hi}", -1))
            continue
        # 用不同和值试几个邻近值，看是否能解
        for alt in (s - 1, s + 1, s - 2, s + 2):
            if not (lo <= alt <= hi):
                continue
            alt_layout = [(layout[j][0] if j != i else alt, layout[j][1]) for j in range(len(layout))]
            try:
                s2 = KillerSudokuSolver(alt_layout, max_solutions=1, node_limit=50_000)
                sols = s2.solve()
                if sols:
                    suspicious.append((i, f"笼 {cells[0]} 改 {alt} 能解出 1 个解（疑似 {s} 读错）", s2.nodes))
                    break
            except Exception:
                pass
    suspicious.sort(key=lambda x: (x[2] if x[2] < 0 else -x[2]))
    out: list[str] = []
    for _, reason, _ in suspicious[:5]:
        out.append(reason)
    return out


# ---------------------------------------------------------------------------
# 自动从图片识别笼布局
# ---------------------------------------------------------------------------
def auto_detect_layout(src: str, grid_spec=None, debug_dir=None, cage_edge_delta=0.08):
    """从图片自动检测笼布局，返回 (layout, debug_info)。"""
    if grid_spec:
        x0, y0, x1, y1 = grid_spec
        xc = tuple(x0 + (x1 - x0) * i / 9 for i in range(10))
        yc = tuple(y0 + (y1 - y0) * i / 9 for i in range(10))
        g = (x0, y0, x1, y1, xc, yc)
    else:
        g = detect_grid(src, debug_dir=debug_dir)

    cages, bbox, xc, yc = detect_cages_from_image(
        src, grid=g, cage_edge_delta=cage_edge_delta, debug_dir=debug_dir,
    )
    xc, yc = g[4], g[5]

    sums = recognize_digits(src, cages, xc, yc, debug_dir=debug_dir)
    layout, failed = cages_with_sums(cages, sums)

    # 尝试常见替代数字（OCR 容易混淆的对：6↔9、3↔8、5↔6、2↔7）
    OCR_CONFUSIONS = {
        6: [9, 5, 0],
        9: [6, 4],
        3: [8, 5],
        5: [6, 3],
        2: [7, 3],
        7: [2, 1],
        1: [7],
        4: [9, 1],
        8: [3, 0],
        0: [6, 8],
    }
    layout_orig = layout
    if failed:
        # 对失败的笼，用可行范围中点作为猜测
        new_failed = []
        for idx in failed:
            cells = cages[idx]
            lo, hi = min_sum(len(cells)), max_sum(len(cells))
            guess = (lo + hi) // 2
            layout.append((guess, cells))
            new_failed.append((idx, guess))
        failed = new_failed

    return layout, {
        "cages_detected": len(cages),
        "sums_recognized": len(cages) - len([x for x in sums if x is None]),
        "ocr_failed": failed,
        "bbox": bbox,
    }


# ---------------------------------------------------------------------------
# 主
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="杀手数独求解器：输入笼布局或直接给图片，输出唯一解/多解/无解。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "输入方式:\n"
            "  --inline \"22:a1,a2,a3,b3; 13:a4,a5; 3:b4,b5\"\n"
            "  --file layout.txt\n"
            "  --json layout.json\n"
            "  --image-auto puzzle.jpg  # 自动检测笼+OCR 和值\n"
            "  --selftest\n"
            "输出方式:\n"
            "  --json-out  机器可读\n"
            "  --image SRC --out solved.png  把答案画回图片\n"
            "退出码: 0 有解, 1 无解, 2 输入错误, 3 搜索超限。"
        ),
    )
    ap.add_argument("--inline", help="内联布局: 和值:格子,格子; ...")
    ap.add_argument("--file", help="从文本文件读取布局")
    ap.add_argument("--json", help="从 JSON 文件读取布局，'-' 表示 stdin")
    ap.add_argument("--image-auto", metavar="PATH",
                    help="自动从图片检测笼 + OCR 和值（实验性）")
    ap.add_argument("--cage-edge-threshold", type=float, default=0.25,
                    help="虚线边界检测阈值（默认 0.25）")
    ap.add_argument("--cage-layout", metavar="PATH",
                    help="与 --image-auto 配合：当 OCR 失败时从该文件读取手动布局")
    ap.add_argument("--preset",
                    help="常规数独已知格，例如 'a1=4,b3=7,...' 或 JSON 文件")
    ap.add_argument("--max-solutions", type=int, default=2,
                    help="最多搜索多少个解（默认 2）")
    ap.add_argument("--node-limit", type=int, default=5_000_000,
                    help="搜索节点上限（默认 500 万）")
    ap.add_argument("--no-ac3", action="store_true",
                    help="禁用 AC-3 弧一致性预处理")
    ap.add_argument("--explain", action="store_true",
                    help="附带输出仅求和约束的秩与自由度 + innies/outies 提示")
    ap.add_argument("--diagnose-conflicts", action="store_true",
                    help="无解时尝试定位最可疑的笼（耗时较长）")
    ap.add_argument("--json-out", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--image", help="把解叠加到该题目图片上并保存")
    ap.add_argument("--out", help="输出图片路径（默认 <原图名>_solved.png）")
    ap.add_argument("--grid", help="网格边界 left,top,right,bottom（默认自动检测）")
    ap.add_argument("--font", help="数字字体文件路径")
    ap.add_argument("--font-size", type=int, help="数字字号（默认按格子大小自动）")
    ap.add_argument("--step-through", action="store_true",
                    help="记录搜索过程（调试用，当前仅占位）")
    ap.add_argument("--debug-ocr", metavar="DIR",
                    help="把 OCR/笼边界检测的中间结果落盘到该目录")
    ap.add_argument("--selftest", action="store_true", help="运行内置已知盘面自检")
    args = ap.parse_args(argv)

    if not args.image and (args.out or args.grid or args.font or args.font_size):
        print(
            "输入错误: --out / --grid / --font / --font-size 需要配合 --image 使用",
            file=sys.stderr,
        )
        return 2

    if args.selftest:
        return run_selftest()

    # --------------------------- 加载布局 ---------------------------
    layout = None
    auto_info = None
    if args.image_auto:
        try:
            grid_spec = parse_grid_spec(args.grid) if args.grid else None
            layout, auto_info = auto_detect_layout(
                args.image_auto,
                grid_spec=grid_spec,
                debug_dir=args.debug_ocr,
                cage_edge_delta=args.cage_edge_threshold,
            )
            print(
                f"自动检测: {auto_info['cages_detected']} 个笼, "
                f"OCR 成功 {auto_info['sums_recognized']} 个",
                file=sys.stderr,
            )
            if auto_info["ocr_failed"]:
                print(
                    f"[警告] {len(auto_info['ocr_failed'])} 个笼 OCR 失败，"
                    f"已填充猜测的和值；建议核对或用 --cage-layout 手动覆盖",
                    file=sys.stderr,
                )
        except Exception as e:
            print(f"自动识别图片失败: {e}", file=sys.stderr)
            if args.cage_layout:
                print("尝试使用 --cage-layout 手动布局...", file=sys.stderr)
            else:
                print("请用 --inline / --file / --json 手动提供布局，或加 --cage-layout",
                      file=sys.stderr)
                return 2
            if args.cage_layout:
                try:
                    args.file = args.cage_layout
                    args.image_auto = None
                except Exception as e2:
                    print(f"加载 --cage-layout 失败: {e2}", file=sys.stderr)
                    return 2

    if layout is None:
        try:
            layout = load_layout(args)
        except (ValueError, OSError, json.JSONDecodeError) as e:
            print(f"输入错误: {e}", file=sys.stderr)
            return 2

    # --------------------------- 校验 ---------------------------
    errors, warnings = validate(layout)
    for w in warnings:
        print(f"[警告] {w}", file=sys.stderr)
    if errors:
        print("布局校验失败:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    # --------------------------- 预置格 ---------------------------
    preset: dict[str, int] = {}
    if args.preset:
        if os.path.exists(args.preset):
            with open(args.preset, "r", encoding="utf-8") as f:
                txt = f.read().strip()
        else:
            txt = args.preset
        if txt.startswith("{"):
            try:
                preset = json.loads(txt)
                if "preset" in preset:
                    preset = preset["preset"]
            except json.JSONDecodeError:
                pass
        else:
            for tok in re.split(r"[,\s]+", txt):
                if not tok or "=" not in tok:
                    continue
                name, digit = tok.split("=", 1)
                try:
                    preset[name.strip().lower()] = int(digit.strip())
                except ValueError:
                    continue

    # --------------------------- 求解 ---------------------------
    solver = KillerSudokuSolver(
        layout,
        max_solutions=max(1, args.max_solutions),
        node_limit=args.node_limit,
        preset=preset,
        enable_ac3=not args.no_ac3,
    )
    sols = solver.solve(step_through=args.step_through)

    # --------------------------- 结果 ---------------------------
    if solver.aborted:
        status = "ABORTED"
        code = 3
    elif not sols:
        status = "NO_SOLUTION"
        code = 1
    elif len(sols) == 1:
        status = "UNIQUE"
        code = 0
    else:
        status = "MULTIPLE"
        code = 0

    image_out = None
    used_grid = None
    if args.image:
        if not sols:
            print(
                "未生成图片：无解或搜索中止，请先修正布局。",
                file=sys.stderr,
            )
        else:
            try:
                out_path = args.out or (
                    os.path.splitext(args.image)[0] + "_solved.png"
                )
                if args.grid:
                    bbox = parse_grid_spec(args.grid)
                    x0, y0, x1, y1 = bbox
                    xc = tuple(x0 + (x1 - x0) * i / 9 for i in range(10))
                    yc = tuple(y0 + (y1 - y0) * i / 9 for i in range(10))
                    g = (x0, y0, x1, y1, xc, yc)
                else:
                    g = detect_grid(args.image, debug_dir=None)
                used_grid = render_solution(
                    args.image,
                    out_path,
                    sols[0],
                    grid=g,
                    font_path=args.font,
                    font_size=args.font_size,
                )
                image_out = out_path
                if status == "MULTIPLE":
                    print("[提示] 存在多解，图片只填入第 1 个解", file=sys.stderr)
            except Exception as e:
                print(f"生成图片失败: {e}", file=sys.stderr)
                code = 2

    diag = sum_only_diagnostics(layout) if args.explain else None
    innies = innies_outies(layout) if args.explain else None

    # 矛盾定位（仅无解时）
    conflict_tips: list[str] = []
    if status == "NO_SOLUTION" and args.diagnose_conflicts:
        print("运行矛盾定位...", file=sys.stderr)
        conflict_tips = diagnose_no_solution(layout)

    if args.json_out:
        out = {
            "status": status,
            "solution_count": len(sols),
            "nodes": solver.nodes,
            "solutions": [
                [[sol[r * 9 + c] for c in range(9)] for r in range(9)]
                for sol in sols
            ],
            "image": image_out,
        }
        if diag:
            out["sum_only"] = {
                "equations": diag[0],
                "rank": diag[1],
                "degrees_of_freedom": diag[2],
            }
        if innies:
            out["innies_outies"] = innies
        if auto_info:
            out["auto_detect"] = auto_info
        if conflict_tips:
            out["conflict_tips"] = conflict_tips
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return code

    print(f"状态: {status}")
    print(f"找到解的数量: {len(sols)}   搜索节点: {solver.nodes}"
          f"{' (AC-3 已启用)' if not args.no_ac3 else ''}")
    if diag:
        print(
            f"仅求和约束: 方程 {diag[0]} 条，秩 {diag[1]}，自由度 {diag[2]}"
            "（>0 说明单靠求和无法逐格确定）"
        )
    if innies:
        print("\n[innies/outies 提示]")
        for t in innies:
            print(f"  {t}")
    for idx, sol in enumerate(sols, 1):
        print(f"\n解 {idx}:")
        print(format_grid(sol))
    if image_out:
        print(f"\n已生成图片: {image_out}")
        if used_grid:
            print("网格边界: %.1f,%.1f,%.1f,%.1f" % used_grid, file=sys.stderr)
    if status == "NO_SOLUTION":
        sys.stdout.flush()
        print(
            "\n提示: 无解通常是某个笼的和值/边界转录错误，或笼相互矛盾；"
            "请核对每个笼的和值与格子集合，或加 --diagnose-conflicts 定位。",
            file=sys.stderr,
        )
        if conflict_tips:
            print("\n[矛盾定位] 最可疑的笼:", file=sys.stderr)
            for t in conflict_tips:
                print(f"  - {t}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
