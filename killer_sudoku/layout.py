"""布局解析与校验。"""

from __future__ import annotations

import json
import re
import sys
from collections import deque

from .core import (
    ALL,
    CELL_ID,
    CELLS,
    ROWS,
    can_form,
    max_sum,
    min_sum,
)


def alias_normalize(name: str) -> str:
    """把 0–8 列或 A–I 列等别名归一化成 a1..i9。"""
    name = name.strip().lower()
    m = re.fullmatch(r"([a-i])\s*([1-9])", name)
    if m:
        return m.group(1) + m.group(2)
    m = re.fullmatch(r"([0-8])\s*([0-8])", name)  # 0-based 行列
    if m:
        return ROWS[int(m.group(1))] + str(int(m.group(2)) + 1)
    # 兼容 "r1c1"、"R1C1" 等
    m = re.fullmatch(r"r\s*([1-9])\s*c\s*([1-9])", name)
    if m:
        return ROWS[int(m.group(1)) - 1] + m.group(2)
    return name  # 原样返回，后续校验会报错


def parse_inline(text: str) -> list[tuple[int, list[str]]]:
    """解析 "和值:格子,格子; ..." 形式。分号或换行分隔。"""
    layout: list[tuple[int, list[str]]] = []
    for token in re.split(r"[;\n]+", text):
        token = token.strip()
        if not token:
            continue
        m = re.match(r"^(\d+)\s*[:=]\s*(.+)$", token)
        if not m:
            raise ValueError(f"无法解析片段: {token!r}（应为 和值:格子,格子）")
        total = int(m.group(1))
        cells = [alias_normalize(x) for x in re.split(r"[,\s]+", m.group(2).strip()) if x]
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
            cells = list(item.get("cells", item.get("cell")))
            cells = [alias_normalize(x) for x in cells]
            layout.append((int(item["sum"]), cells))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            cells = [alias_normalize(x) for x in list(item[1])]
            layout.append((int(item[0]), cells))
        else:
            raise ValueError(f"无法识别的笼项: {item!r}")
    return layout


def load_layout(args) -> list[tuple[int, list[str]]]:
    """按 argparse 命名空间的字段加载布局。"""
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
    raise ValueError("请提供 --inline / --file / --json 之一，或使用 --selftest / --image-auto")


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


def validate(
    layout: list[tuple[int, list[str]]],
) -> tuple[list[str], list[str]]:
    """校验布局，返回 (errors, warnings)。"""
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
        if len(cells) == 1 and s != int(
            re.fullmatch(r"[a-i]([1-9])", cells[0]).group(1)
        ):
            warnings.append(f"1 格笼 {tag} 和值 {s} 必须等于该格所在列数，检查 OCR")
        for x in cells:
            if not re.fullmatch(r"[a-i][1-9]", x):
                errors.append(f"笼 {tag} 含非法格子名 {x!r}（应为 a1..i9）")
            elif x in owner:
                errors.append(f"格子 {x} 同时属于笼 {owner[x]} 与笼 {k}")
            else:
                owner[x] = k
        if not can_form(ALL, len(cells), s):
            lo, hi = min_sum(len(cells)), max_sum(len(cells))
            errors.append(
                f"笼 {tag} 用 {len(cells)} 个不重复数字凑不出和 {s}"
                f"（可行范围 {lo}..{hi}）"
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
