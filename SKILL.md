---
name: killer-sudoku-solver
description: Solve killer sudoku from cage sums and cells, report unique/multiple/no solution, and optionally fill answers onto a puzzle image. Use for 杀手数独求解, cage layout input, or solved grid images.
---

# Killer Sudoku Solver

根据笼布局直接求解杀手数独，输出唯一解 / 多解 / 无解。不要靠心算求解，始终运行脚本。

## 输入：笼布局

一格一个名字：行 `a`–`i`，列 `1`–`9`，如 `a1`、`b3`、`i9`。

一个笼 = 一个和值 + 它覆盖的若干格。合法布局必须满足：

- 每个格子恰好属于一个笼，合计 81 格；
- 所有笼和值之和等于 405（= 9×45）；
- 每个笼内数字互不重复，且该和值能用对应格数凑出。

## 运行

在本 skill 目录下执行（把 `<layout>` 换成实际布局）：

```bash
python3 scripts/solve_killer_sudoku.py --inline "22:a1,a2,a3,b3; 13:a4,a5; 3:b4,b5"
python3 scripts/solve_killer_sudoku.py --file layout.txt --explain
python3 scripts/solve_killer_sudoku.py --json layout.json --json-out
python3 scripts/solve_killer_sudoku.py --file layout.txt --image IMG_2978.jpeg --out solved.png
python3 scripts/solve_killer_sudoku.py --selftest
```

输入格式三选一：

1. `--inline` / `--file`：`和值:格子,格子; 和值:格子,格子; ...`，分号或换行分隔。
2. `--json`：文件路径，`-` 表示 stdin。结构为
   ```json
   {"cages": [{"sum": 22, "cells": ["a1", "a2", "a3", "b3"]}]}
   ```
   也接受 `[[22, ["a1","a2","a3","b3"]], ...]`。

常用参数：

- `--explain`：附带输出“仅求和约束”的方程数、秩和自由度。
- `--max-solutions N`：最多找 N 个解，默认 2，足够判定唯一性。
- `--node-limit N`：搜索节点上限，默认 500 万。
- `--json-out`：机器可读输出。
- `--image SRC`：把解逐格填回题目图片并保存。
- `--out PATH`：输出图片路径，默认 `<原图名>_solved.png`。
- `--grid left,top,right,bottom`：手动指定 9×9 外框；默认自动检测。
- `--font PATH` / `--font-size N`：自定义字体与字号。

图片模式说明：

- 只做“答案叠加”，不会从图片中识别笼布局；布局仍需先用 `--inline` / `--file` / `--json` 提供。
- 自动检测失败（例如截图无完整外框）时，用 `--grid` 指定外框坐标。
- 存在多解时，图片只填入第 1 个解，并在 stderr 提示。

## 解读结果

- `UNIQUE`：恰好 1 个解，退出码 0。
- `MULTIPLE`：找到至少 2 个解，布局约束不足，退出码 0。
- `NO_SOLUTION`：无解，退出码 1。优先检查某个笼的和值或边界是否转录错误。
- 校验失败：退出码 2，逐条列出格子重复、覆盖不足、和值不可能等问题。
- `ABORTED`：超过节点上限，退出码 3，通常是布局有误。

输出中的 `仅求和约束 ... 秩 ... 自由度` 用于解释：只靠笼和与行列和（45）是欠定的，自由度大于 0 时无法逐格确定，必须依赖 1–9 不重复的离散约束。

## 从图片转写布局

1. 按虚线边界逐笼记录和值与格子，确保每格只写一次。
2. 先自检总数：所有和值相加必须等于 405。
3. 有跨界笼时，以虚线为准，粗宫线不代表笼边界。
4. 转写完成后运行脚本；若 `NO_SOLUTION`，回头核对最可疑的笼（和值小、格数多的优先）。

## 示例

完整 9×9 布局较长时，写入文件再运行更稳妥：

```bash
python3 scripts/solve_killer_sudoku.py --file my_layout.txt --explain
```

脚本会用位掩码 + MRV 回溯，并对每个笼的剩余和做精确子集和剪枝；正常盘面通常在数千个节点内完成。
