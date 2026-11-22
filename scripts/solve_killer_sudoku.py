#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""杀手数独求解器。

输入：笼布局（每个笼的和值 + 该笼覆盖的格子集合）。
格子命名：行 a-i，列 1-9，例如 a1、b3、i9。
输出：唯一解 / 多解 / 无解，以及搜索统计；可选线性约束诊断。

用法示例：
  python3 solve_killer_sudoku.py --inline "22:a1,a2,a3,b3; 13:a4,a5; ..."
  python3 solve_killer_sudoku.py --file layout.txt
  python3 solve_killer_sudoku.py --json layout.json
  python3 solve_killer_sudoku.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import deque
from fractions import Fraction

ROWS = "abcdefghi"
CELLS = [f"{r}{c}" for r in ROWS for c in range(1, 10)]
CELL_ID = {name: i for i, name in enumerate(CELLS)}
ALL = (1 << 10) - 2  # 位 1..9 全部置 1

try:  # Python >= 3.8 一般都有 bit_count
    (0).bit_count
    def popcount(x: int) -> int:
        return x.bit_count()
except AttributeError:  # 兼容旧版本
    def popcount(x: int) -> int:
        return bin(x).count("1")


# ---------------------------------------------------------------------------
# 预计算：REACH[mask][k] 是一个位集，第 s 位为 1 表示“从 mask 中取 k 个不同
# 数字，可以凑出和 s”。用于对笼剩余部分做精确可行性剪枝（比最小/最大和更紧）。
# ---------------------------------------------------------------------------
def _build_reach() -> list[list[int]]:
    reach = [[0] * 10 for _ in range(1 << 10)]
    for mask in range(1 << 10):
        reach[mask][0] = 1  # 任何数字集合取 0 个数，和都为 0
    for mask in range(1, 1 << 10):
        low = mask & -mask
        d = low.bit_length() - 1
        prev = mask ^ low
        if d == 0:  # 位 0 不对应任何合法数字
            for k in range(10):
                reach[mask][k] = reach[prev][k]
            continue
        for k in range(1, 10):
            reach[mask][k] = reach[prev][k] | (reach[prev][k - 1] << d)
    return reach


REACH = _build_reach()


def can_form(mask: int, k: int, total: int) -> bool:
    """从 mask 中取恰好 k 个不同数字，能否凑出 total。"""
    if k < 0 or total < 0:
        return False
    if k == 0:
        return total == 0
    if total > 45:
        return False
    return bool((REACH[mask][k] >> total) & 1)


# ---------------------------------------------------------------------------
# 布局解析
# ---------------------------------------------------------------------------
def parse_inline(text: str) -> list[tuple[int, list[str]]]:
    """解析 "和值:格子,格子; ..." 形式。也接受换行分隔与空格分隔。"""
    layout: list[tuple[int, list[str]]] = []
    for token in re.split(r"[;\n]+", text):
        token = token.strip()
        if not token:
            continue
        m = re.match(r"^(\d+)\s*[:=]\s*(.+)$", token)
        if not m:
            raise ValueError(f"无法解析片段: {token!r}（应为 和值:格子,格子）")
        total = int(m.group(1))
        cells = [x for x in re.split(r"[,\s]+", m.group(2).strip()) if x]
        layout.append((total, cells))
    return layout


def parse_json_obj(obj) -> list[tuple[int, list[str]]]:
    arr = obj.get("cages") if isinstance(obj, dict) and "cages" in obj else obj
    if not isinstance(arr, list):
        raise ValueError("JSON 结构应为 {cages: [...]} 或直接是数组")
    layout: list[tuple[int, list[str]]] = []
    for item in arr:
        if isinstance(item, dict):
            if "sum" not in item or ("cells" not in item and "cell" not in item):
                raise ValueError(f"JSON 笼缺少 sum/cells: {item!r}")
            layout.append((int(item["sum"]), list(item.get("cells", item.get("cell")))))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            layout.append((int(item[0]), list(item[1])))
        else:
            raise ValueError(f"无法识别的笼项: {item!r}")
    return layout


def load_layout(args) -> list[tuple[int, list[str]]]:
    if args.inline is not None:
        return parse_inline(args.inline)
    if args.file is not None:
        with open(args.file, "r", encoding="utf-8") as f:
            return parse_inline(f.read())
    if args.json is not None:
        if args.json == "-":
            obj = json.load(sys.stdin)
        else:
            with open(args.json, "r", encoding="utf-8") as f:
                obj = json.load(f)
        return parse_json_obj(obj)
    raise ValueError("请提供 --inline / --file / --json 之一，或使用 --selftest")


# ---------------------------------------------------------------------------
# 布局校验
# ---------------------------------------------------------------------------
def is_connected(cells: list[str]) -> bool:
    s = set(cells)
    if not s:
        return False
    start = next(iter(s))
    seen = {start}
    dq = deque([start])
    while dq:
        cur = dq.popleft()
        r, c = ROWS.index(cur[0]), int(cur[1]) - 1
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < 9 and 0 <= nc < 9:
                nxt = f"{ROWS[nr]}{nc + 1}"
                if nxt in s and nxt not in seen:
                    seen.add(nxt)
                    dq.append(nxt)
    return len(seen) == len(s)


def validate(layout: list[tuple[int, list[str]]]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    owner: dict[str, int] = {}
    total_sum = 0
    for k, (s, cells) in enumerate(layout):
        tag = cells[0] if cells else f"#{k}"
        total_sum += s
        if not cells:
            errors.append(f"笼 {tag} 没有格子")
            continue
        if len(cells) > 9:
            errors.append(f"笼 {tag} 有 {len(cells)} 格，超过 9 格")
        if not (1 <= s <= 45):
            errors.append(f"笼 {tag} 和值 {s} 超出 1..45")
        for x in cells:
            if not re.fullmatch(r"[a-i][1-9]", x):
                errors.append(f"笼 {tag} 含非法格子名 {x!r}（应为 a1..i9）")
            elif x in owner:
                errors.append(f"格子 {x} 同时属于笼 {owner[x]} 与笼 {k}")
            else:
                owner[x] = k
        if not can_form(ALL, len(cells), s):
            errors.append(
                f"笼 {tag} 用 {len(cells)} 个不重复数字凑不出和 {s}"
                f"（可行范围 {_min_sum(len(cells))}..{_max_sum(len(cells))}）"
            )
        if not is_connected(cells):
            warnings.append(f"笼 {tag} 的格子不是四连通（可能是转录错误）")
    if len(owner) != 81:
        missing = [x for x in CELLS if x not in owner]
        errors.append(
            f"格子覆盖数为 {len(owner)}，应恰好 81；缺失示例: {', '.join(missing[:8])}"
        )
    if total_sum != 405:
        errors.append(f"所有笼和值为 {total_sum}，应等于 405（=9×45）")
    return errors, warnings


def _min_sum(k: int) -> int:
    return k * (k + 1) // 2


def _max_sum(k: int) -> int:
    return sum(range(10 - k, 10))


# ---------------------------------------------------------------------------
# 求解器
# ---------------------------------------------------------------------------
class KillerSudokuSolver:
    def __init__(self, layout, max_solutions=2, node_limit=5_000_000):
        self.layout = layout
        self.max_solutions = max_solutions
        self.node_limit = node_limit
        self.nodes = 0
        self.aborted = False
        self.solutions: list[list[int]] = []

        self.grid = [0] * 81
        self.used_row = [0] * 9
        self.used_col = [0] * 9
        self.used_box = [0] * 9

        self.cage_of = [0] * 81
        self.cage_cells: list[list[int]] = []
        self.cage_sum: list[int] = []
        for cid, (s, cells) in enumerate(layout):
            ids = [CELL_ID[x] for x in cells]
            self.cage_cells.append(ids)
            self.cage_sum.append(s)
            for i in ids:
                self.cage_of[i] = cid

        self.cage_used = [0] * len(layout)
        self.cage_left = [len(x) for x in self.cage_cells]
        self.cage_rem = self.cage_sum[:]

    # -- 候选 -------------------------------------------------------------
    def candidates(self, i: int) -> int:
        r, c = divmod(i, 9)
        box = (r // 3) * 3 + c // 3
        cid = self.cage_of[i]
        base = ALL & ~(self.used_row[r] | self.used_col[c] | self.used_box[box])
        base &= ~self.cage_used[cid]
        out = 0
        m = base
        while m:
            bit = m & -m
            m -= bit
            d = bit.bit_length() - 1
            na = (ALL & ~self.cage_used[cid]) & ~bit
            nk = self.cage_left[cid] - 1
            nr = self.cage_rem[cid] - d
            if nk == 0:
                if nr == 0:
                    out |= bit
            elif can_form(na, nk, nr):
                out |= bit
        return out

    # -- 落子 / 撤销 ------------------------------------------------------
    def place(self, i: int, d: int) -> None:
        r, c = divmod(i, 9)
        box = (r // 3) * 3 + c // 3
        bit = 1 << d
        self.grid[i] = d
        self.used_row[r] |= bit
        self.used_col[c] |= bit
        self.used_box[box] |= bit
        cid = self.cage_of[i]
        self.cage_used[cid] |= bit
        self.cage_left[cid] -= 1
        self.cage_rem[cid] -= d

    def unplace(self, i: int, d: int) -> None:
        r, c = divmod(i, 9)
        box = (r // 3) * 3 + c // 3
        bit = 1 << d
        self.grid[i] = 0
        self.used_row[r] ^= bit
        self.used_col[c] ^= bit
        self.used_box[box] ^= bit
        cid = self.cage_of[i]
        self.cage_used[cid] ^= bit
        self.cage_left[cid] += 1
        self.cage_rem[cid] += d

    # -- 搜索（MRV：优先展开候选最少的格子） ------------------------------
    def search(self) -> None:
        if self.aborted:
            return
        self.nodes += 1
        if self.nodes > self.node_limit:
            self.aborted = True
            return

        best, best_mask, best_n = -1, 0, 10
        for i in range(81):
            if self.grid[i] == 0:
                m = self.candidates(i)
                n = popcount(m)
                if n == 0:
                    return
                if n < best_n:
                    best, best_mask, best_n = i, m, n
                    if n == 1:
                        break
        if best < 0:
            self.solutions.append(self.grid[:])
            return

        m = best_mask
        while m:
            bit = m & -m
            m -= bit
            d = bit.bit_length() - 1
            self.place(best, d)
            self.search()
            self.unplace(best, d)
            if self.aborted or len(self.solutions) >= self.max_solutions:
                return

    def solve(self):
        self.search()
        return self.solutions


# ---------------------------------------------------------------------------
# 线性“求和约束”诊断：81 个未知数，行/列/笼求和方程的秩
# ---------------------------------------------------------------------------
def _rank(rows: list[list[Fraction]]) -> int:
    if not rows:
        return 0
    mat = [row[:] for row in rows]
    m, n = len(mat), len(mat[0])
    rank = 0
    for col in range(n):
        pivot = None
        for i in range(rank, m):
            if mat[i][col] != 0:
                pivot = i
                break
        if pivot is None:
            continue
        mat[rank], mat[pivot] = mat[pivot], mat[rank]
        pv = mat[rank][col]
        mat[rank] = [x / pv for x in mat[rank]]
        for i in range(m):
            if i != rank and mat[i][col] != 0:
                f = mat[i][col]
                mat[i] = [a - f * b for a, b in zip(mat[i], mat[rank])]
        rank += 1
        if rank == m:
            break
    return rank


def sum_only_diagnostics(layout):
    """返回 (方程数, 秩, 自由度)。用于说明“只靠求和”为何不足。"""
    rows: list[list[Fraction]] = []
    for r in range(9):
        row = [Fraction(0)] * 81
        for c in range(9):
            row[r * 9 + c] = Fraction(1)
        rows.append(row)
    for c in range(9):
        row = [Fraction(0)] * 81
        for r in range(9):
            row[r * 9 + c] = Fraction(1)
        rows.append(row)
    for s, cells in layout:
        row = [Fraction(0)] * 81
        for x in cells:
            row[CELL_ID[x]] = Fraction(1)
        rows.append(row)
    rank = _rank(rows)
    return len(rows), rank, 81 - rank


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def format_grid(sol: list[int]) -> str:
    lines = ["    " + " ".join(str(c) for c in range(1, 10))]
    lines.append("   " + "-" * 19)
    for r in range(9):
        vals = [str(sol[r * 9 + c]) for c in range(9)]
        lines.append(f" {ROWS[r]}  " + " ".join(vals))
        if r in (2, 5):
            lines.append("   " + "-" * 19)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 把解渲染回题目图片
# ---------------------------------------------------------------------------
def _group_centers(scores: list[float], threshold: float) -> list[float]:
    """把连续超过阈值的下标聚成组，返回每组中心。"""
    groups: list[list[int]] = []
    cur: list[int] = []
    for i, v in enumerate(scores):
        if v >= threshold:
            cur.append(i)
        elif cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return [sum(g) / len(g) for g in groups]


def detect_grid(src: str) -> tuple[float, float, float, float]:
    """自动检测 9×9 外框，返回 (left, top, right, bottom)。

    做法：缩小图像，统计每行/列暗像素比例；粗外框形成两条最强的长线，
    取最外侧两组线的中心作为外框。失败时由调用方提示用 --grid 手动指定。
    """
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(src)).convert("L")
    W, H = im.size
    scale = 400.0 / max(W, H)
    sw, sh = max(50, int(W * scale)), max(50, int(H * scale))
    small = im.resize((sw, sh), Image.NEAREST)
    px = small.load()

    colscore = [0.0] * sw
    for x in range(sw):
        c = sum(1 for y in range(sh) if px[x, y] < 160)
        colscore[x] = c / sh
    rowscore = [0.0] * sh
    for y in range(sh):
        c = sum(1 for x in range(sw) if px[x, y] < 160)
        rowscore[y] = c / sw

    for thr in (0.5, 0.35, 0.25, 0.18):
        cg = _group_centers(colscore, thr)
        rg = _group_centers(rowscore, thr)
        if len(cg) >= 2 and len(rg) >= 2:
            x0, x1 = cg[0] * W / sw, cg[-1] * W / sw
            y0, y1 = rg[0] * H / sh, rg[-1] * H / sh
            if x1 - x0 > W * 0.4 and y1 - y0 > H * 0.4:
                return (x0, y0, x1, y1)
    raise ValueError(
        "无法自动检测网格边界，请用 --grid left,top,right,bottom 指定"
    )


def parse_grid_spec(s: str) -> tuple[float, float, float, float]:
    parts = [p for p in re.split(r"[,\s]+", s.strip()) if p]
    if len(parts) != 4:
        raise ValueError("--grid 需要 4 个数: left,top,right,bottom")
    x0, y0, x1, y1 = (float(p) for p in parts)
    if not (x1 > x0 and y1 > y0):
        raise ValueError("--grid 要求 right>left 且 bottom>top")
    return (x0, y0, x1, y1)


def _find_font(size: int, font_path: str | None = None):
    from PIL import ImageFont

    candidates = []
    if font_path:
        candidates.append(font_path)
    candidates += [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # 旧版 Pillow 不支持 size
        return ImageFont.load_default()


def render_solution(
    src: str,
    out: str,
    sol: list[int],
    grid: tuple[float, float, float, float] | None = None,
    font_path: str | None = None,
    font_size: int | None = None,
) -> tuple[float, float, float, float]:
    """把解逐格填入图片并保存。返回实际使用的网格边界。"""
    from PIL import Image, ImageDraw, ImageOps

    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    g = grid or detect_grid(src)
    x0, y0, x1, y1 = g
    cw = (x1 - x0) / 9.0
    ch = (y1 - y0) / 9.0
    size = int(font_size) if font_size else int(min(cw, ch) * 0.56)
    font = _find_font(max(8, size), font_path)
    draw = ImageDraw.Draw(im)
    stroke = max(1, size // 32)
    for r in range(9):
        for c in range(9):
            draw.text(
                (x0 + (c + 0.5) * cw, y0 + (r + 0.5) * ch),
                str(sol[r * 9 + c]),
                font=font,
                fill=(20, 24, 40),
                anchor="mm",
                stroke_width=stroke,
                stroke_fill=(255, 255, 255),
            )
    parent = os.path.dirname(os.path.abspath(out))
    if parent:
        os.makedirs(parent, exist_ok=True)
    im.save(out)
    return g


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="杀手数独求解器：输入笼布局，输出唯一解/多解/无解。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "输入格式示例:\n"
            "  --inline \"22:a1,a2,a3,b3; 13:a4,a5; 3:b4,b5\"\n"
            "  --json layout.json   # {cages:[{sum:22,cells:[\"a1\",...]}, ...]}\n"
            "把答案填回图片:\n"
            "  --image IMG_2978.jpeg [--out solved.png]\n"
            "格子命名: 行 a-i, 列 1-9。\n"
            "退出码: 0 有解, 1 无解, 2 输入错误, 3 搜索超限。"
        ),
    )
    ap.add_argument("--inline", help="内联布局: 和值:格子,格子; ...")
    ap.add_argument("--file", help="从文本文件读取布局")
    ap.add_argument("--json", help="从 JSON 文件读取布局，'-' 表示 stdin")
    ap.add_argument("--max-solutions", type=int, default=2,
                    help="最多搜索多少个解（默认 2，用于判定唯一性）")
    ap.add_argument("--node-limit", type=int, default=5_000_000,
                    help="搜索节点上限（默认 500 万）")
    ap.add_argument("--explain", action="store_true",
                    help="附带输出“仅求和约束”的秩与自由度诊断")
    ap.add_argument("--json-out", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--image", help="把解叠加到该题目图片上并保存")
    ap.add_argument("--out", help="输出图片路径（默认 <原图名>_solved.png）")
    ap.add_argument("--grid", help="网格边界 left,top,right,bottom（默认自动检测）")
    ap.add_argument("--font", help="数字字体文件路径")
    ap.add_argument("--font-size", type=int, help="数字字号（默认按格子大小自动）")
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

    try:
        layout = load_layout(args)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"输入错误: {e}", file=sys.stderr)
        return 2

    errors, warnings = validate(layout)
    for w in warnings:
        print(f"[警告] {w}", file=sys.stderr)
    if errors:
        print("布局校验失败:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    solver = KillerSudokuSolver(
        layout, max_solutions=max(1, args.max_solutions), node_limit=args.node_limit
    )
    sols = solver.solve()

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
                grid_spec = parse_grid_spec(args.grid) if args.grid else None
                used_grid = render_solution(
                    args.image,
                    out_path,
                    sols[0],
                    grid=grid_spec,
                    font_path=args.font,
                    font_size=args.font_size,
                )
                image_out = out_path
                if status == "MULTIPLE":
                    print("[提示] 存在多解，图片只填入第 1 个解", file=sys.stderr)
                print("网格边界: %.1f,%.1f,%.1f,%.1f" % used_grid, file=sys.stderr)
            except Exception as e:  # 图片读写/字体/检测失败都归为输入错误
                print(f"生成图片失败: {e}", file=sys.stderr)
                code = 2

    diag = sum_only_diagnostics(layout) if args.explain else None

    if args.json_out:
        out = {
            "status": status,
            "solution_count": len(sols),
            "nodes": solver.nodes,
            "solutions": [
                [[sol[r * 9 + c] for c in range(9)] for r in range(9)] for sol in sols
            ],
            "image": image_out,
        }
        if diag:
            out["sum_only"] = {
                "equations": diag[0],
                "rank": diag[1],
                "degrees_of_freedom": diag[2],
            }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return code

    print(f"状态: {status}")
    print(f"找到解的数量: {len(sols)}   搜索节点: {solver.nodes}")
    if diag:
        print(
            f"仅求和约束: 方程 {diag[0]} 条，秩 {diag[1]}，自由度 {diag[2]}"
            "（>0 说明单靠求和无法逐格确定）"
        )
    for idx, sol in enumerate(sols, 1):
        print(f"\n解 {idx}:")
        print(format_grid(sol))
    if image_out:
        print(f"\n已生成图片: {image_out}")
    if status == "NO_SOLUTION":
        sys.stdout.flush()
        print(
            "\n提示: 无解通常是某个笼的和值/边界转录错误，或笼相互矛盾；"
            "请核对每个笼的和值与格子集合。",
            file=sys.stderr,
        )
    return code


# ---------------------------------------------------------------------------
# 自检：使用本项目图片 IMG_2978.jpeg 对应的 32 个笼
# ---------------------------------------------------------------------------
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
    print("自检通过：唯一解与预期一致")
    print(f"搜索节点: {solver.nodes}")
    print(f"仅求和诊断: 方程 {eq} 条，秩 {rank}，自由度 {dof}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
