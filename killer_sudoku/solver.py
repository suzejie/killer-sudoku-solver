"""求解器：位掩码 + MRV 回溯 + 精确子集和剪枝 + AC-3 预处理。"""

from __future__ import annotations

from collections import deque

from .core import (
    ALL,
    CELL_ID,
    ROWS,
    can_form,
    popcount,
)


class KillerSudokuSolver:
    def __init__(
        self,
        layout,
        max_solutions: int = 2,
        node_limit: int = 5_000_000,
        preset: dict[str, int] | None = None,
        enable_ac3: bool = True,
    ):
        """
        layout: [(sum, [cell_name, ...]), ...]
        preset: 常规数独的已知格 {"a1": 4, ...}，会作为附加约束。
        """
        self.layout = layout
        self.max_solutions = max_solutions
        self.node_limit = node_limit
        self.enable_ac3 = enable_ac3
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

        self.steps: list[str] = []  # --step-through 时记录

        if preset:
            for name, digit in preset.items():
                idx = CELL_ID[name]
                if self.grid[idx] != 0:
                    raise ValueError(f"已知格 {name} 重复设置")
                self.place(idx, digit)

    # ------------------------------------------------------------------
    # 候选值
    # ------------------------------------------------------------------
    def _box_of(self, i: int) -> int:
        r, c = divmod(i, 9)
        return (r // 3) * 3 + c // 3

    def base_mask(self, i: int) -> int:
        r, c = divmod(i, 9)
        return (
            ALL
            & ~(self.used_row[r] | self.used_col[c] | self.used_box[(r // 3) * 3 + c // 3])
            & ~self.cage_used[self.cage_of[i]]
        )

    def candidates(self, i: int) -> int:
        """精确候选：对每个 base 值，检查笼剩余部分能否凑出剩余和。"""
        base = self.base_mask(i)
        cid = self.cage_of[i]
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

    # ------------------------------------------------------------------
    # 落子 / 撤销
    # ------------------------------------------------------------------
    def place(self, i: int, d: int) -> None:
        r, c = divmod(i, 9)
        box = self._box_of(i)
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
        box = self._box_of(i)
        bit = 1 << d
        self.grid[i] = 0
        self.used_row[r] ^= bit
        self.used_col[c] ^= bit
        self.used_box[box] ^= bit
        cid = self.cage_of[i]
        self.cage_used[cid] ^= bit
        self.cage_left[cid] += 1
        self.cage_rem[cid] += d

    # ------------------------------------------------------------------
    # AC-3 弧一致性预处理
    # ------------------------------------------------------------------
    def ac3(self) -> bool:
        """对所有空格做候选值一致性检查。
        返回 True 表示找到至少一个确定值（落子了），False 表示没进展。
        若发现矛盾返回 None（用 False 表示无进展，用 True 表示有更新）。
        真正失败时抛 RuntimeError。"""
        progress = False
        queue = deque([i for i in range(81) if self.grid[i] == 0])
        changed: set[int] = set()
        while queue:
            i = queue.popleft()
            if self.grid[i] != 0:
                continue
            cand = self.candidates(i)
            n = popcount(cand)
            if n == 0:
                raise RuntimeError(f"AC-3: 格子 {i} 候选为空")
            if n == 1:
                d = cand.bit_length() - 1
                self.place(i, d)
                progress = True
                changed.add(i)
                # 与该格同约束的空格加入队列
                r, c = divmod(i, 9)
                box = self._box_of(i)
                cid = self.cage_of[i]
                for j in range(81):
                    if j == i or self.grid[j] != 0:
                        continue
                    jr, jc = divmod(j, 9)
                    jbox = self._box_of(j)
                    jcid = self.cage_of[j]
                    if (
                        jr == r
                        or jc == c
                        or jbox == box
                        or jcid == cid
                    ):
                        queue.append(j)
        return progress

    def ac3_fixpoint(self) -> None:
        """反复跑 AC-3 直到稳定。"""
        for _ in range(100):
            if not self.ac3():
                break

    # ------------------------------------------------------------------
    # 搜索（MRV：候选最少优先）
    # ------------------------------------------------------------------
    def _search(self, step_through: bool = False) -> None:
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

        if step_through and self.steps:
            pass  # hook for step log

        m = best_mask
        while m:
            bit = m & -m
            m -= bit
            d = bit.bit_length() - 1
            self.place(best, d)
            self._search(step_through)
            self.unplace(best, d)
            if self.aborted or len(self.solutions) >= self.max_solutions:
                return

    def solve(self, step_through: bool = False):
        if self.enable_ac3:
            try:
                self.ac3_fixpoint()
            except RuntimeError as e:
                # AC-3 直接发现矛盾，视为无解
                return self.solutions
        self._search(step_through)
        return self.solutions
