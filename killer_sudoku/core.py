"""核心常量与预计算：与具体应用解耦。"""

from __future__ import annotations

ROWS = "abcdefghi"
CELLS = [f"{r}{c}" for r in ROWS for c in range(1, 10)]
CELL_ID = {name: i for i, name in enumerate(CELLS)}
ALL = (1 << 10) - 2  # 位 1..9 全部置 1


try:
    (0).bit_count

    def popcount(x: int) -> int:
        return x.bit_count()


except AttributeError:  # Python < 3.8
    def popcount(x: int) -> int:
        return bin(x).count("1")


# ---------------------------------------------------------------------------
# REACH[mask][k]：从 mask 中取 k 个不同数字，可以凑出的所有和的位集。
# 用于对笼剩余部分做精确可行性剪枝（比 min/max 和更紧）。
# ---------------------------------------------------------------------------
def _build_reach() -> list[list[int]]:
    reach = [[0] * 10 for _ in range(1 << 10)]
    for mask in range(1 << 10):
        reach[mask][0] = 1
    for mask in range(1, 1 << 10):
        low = mask & -mask
        d = low.bit_length() - 1
        prev = mask ^ low
        if d == 0:
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


def min_sum(k: int) -> int:
    return k * (k + 1) // 2


def max_sum(k: int) -> int:
    return sum(range(10 - k, 10))
