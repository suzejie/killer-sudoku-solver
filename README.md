# killer-sudoku-solver

一个用于杀手数独求解 skill：输入笼布局，输出唯一解 / 多解 / 无解；可选把答案直接填回题目图片。

## 特性

- 位掩码 + MRV 回溯，配合每个笼的精确子集和剪枝
- 自动校验格子覆盖、和值总和 405、单笼和值是否可行
- 支持内联、文本文件、JSON 三种输入
- 可选把解逐格叠加到题目图片，自动检测 9×9 外框
- `--explain` 输出“仅求和约束”的秩与自由度，解释为什么单靠求和不够
- 内置已知盘面自检，方便回归

## 安装

全局安装：

```bash
git clone https://github.com/suziejie/killer-sudoku-solver.git \
  ~/.trae-cn/skills/killer-sudoku-solver
```

项目级安装：

```bash
git clone https://github.com/suziejie/killer-sudoku-solver.git \
  <项目目录>/.trae/skills/killer-sudoku-solver
```

> 克隆后的目录名必须是 `killer-sudoku-solver`，与 `SKILL.md` 中的 `name` 一致。

## 快速开始

```bash
# 自检（内置一份 32 笼盘面）
python3 scripts/solve_killer_sudoku.py --selftest

# 从文本布局求解，并输出线性诊断
python3 scripts/solve_killer_sudoku.py --file layout.txt --explain

# 内联布局
python3 scripts/solve_killer_sudoku.py --inline "22:a1,a2,a3,b3; 13:a4,a5; 3:b4,b5"

# JSON 输入 + 机器可读输出
python3 scripts/solve_killer_sudoku.py --json layout.json --json-out

# 求解并把答案填回图片
python3 scripts/solve_killer_sudoku.py --file layout.txt \
  --image puzzle.jpg --out solved.png
```

## 输入格式

格子命名：行 `a`–`i`，列 `1`–`9`，例如 `a1`、`b3`、`i9`。

文本格式（分号或换行分隔）：

```text
22:a1,a2,a3,b3; 13:a4,a5; 3:b4,b5; ...
```

JSON 格式：

```json
{
  "cages": [
    {"sum": 22, "cells": ["a1", "a2", "a3", "b3"]},
    {"sum": 13, "cells": ["a4", "a5"]}
  ]
}
```

合法布局需要满足：

- 每个格子恰好属于一个笼，合计 81 格
- 所有笼和值之和等于 405（= 9×45）
- 每个笼内数字互不重复，且该和值能用对应格数凑出

## 输出与退出码

| 状态 | 含义 | 退出码 |
|---|---|---|
| `UNIQUE` | 恰好一个解 | 0 |
| `MULTIPLE` | 至少两个解 | 0 |
| `NO_SOLUTION` | 无解 | 1 |
| 校验失败 | 输入不合法 | 2 |
| `ABORTED` | 超过节点上限 | 3 |

`--explain` 会额外输出类似：

```text
仅求和约束: 方程 50 条，秩 47，自由度 34
```

自由度大于 0 说明只靠笼和与行列和（45）无法逐格确定，必须依赖 1–9 不重复的离散约束。

## 图片模式

```bash
python3 scripts/solve_killer_sudoku.py --file layout.txt \
  --image puzzle.jpg --out solved.png
```

- 只负责把答案画到图上，**不会**从图片识别笼布局
- 默认自动检测 9×9 外框；失败时用 `--grid left,top,right,bottom` 手动指定
- 存在多解时，图片只填入第 1 个解并给出提示
- 可用 `--font` / `--font-size` 调整字体与字号

## 常用参数

| 参数 | 说明 |
|---|---|
| `--inline` | 内联布局字符串 |
| `--file` | 从文本文件读取布局 |
| `--json` | 从 JSON 文件读取布局，`-` 表示 stdin |
| `--max-solutions N` | 最多搜索 N 个解，默认 2 |
| `--node-limit N` | 搜索节点上限，默认 500 万 |
| `--explain` | 输出仅求和约束的秩与自由度 |
| `--json-out` | 以 JSON 输出结果 |
| `--image` | 把解叠加到题目图片 |
| `--out` | 输出图片路径，默认 `<原图名>_solved.png` |
| `--grid` | 手动指定网格边界 |
| `--font` / `--font-size` | 自定义字体与字号 |

## 开发

```bash
python3 scripts/solve_killer_sudoku.py --selftest
```

自检会验证内置盘面的唯一解、搜索节点数，以及仅求和约束的秩与自由度。

## License

[MIT](LICENSE)
