Read this in other languages: [English](README.md), [中文](README.zh.md)

# Killer Sudoku Solver

杀手数独求解器：输入笼布局或直接给图片，输出**唯一解 / 多解 / 无解**，可选叠加答案到原图。

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Pillow](https://img.shields.io/badge/Pillow-10.x-green.svg)](https://pillow.readthedocs.io/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)](#)

---

## 功能特性

- 🧩 **精确求解**：位掩码 MRV + AC-3 弧一致性预处理 + 子集和精确剪枝
- 📸 **图片自动识别**：虚线笼边界自适应阈值检测 + 并查集重建（32/32 笼 SELFTEST 验证通过）
- 🔢 **和值 OCR**：tesseract 优先，模板匹配兜底
- 🩺 **诊断工具**：秩诊断 / innies-outies / 矛盾定位
- 🖼️ **答案叠加**：自动定位外框，逐格写入数字

## 目录结构

```
killer-sudoku-solver_v2/
├── killer_sudoku/           # Python 包
│   ├── core.py              # 预计算表（REACH / can_form / popcount）
│   ├── layout.py            # 布局解析、别名归一化、校验
│   ├── solver.py            # 求解器主类：AC-3 + MRV + 剪枝
│   ├── diagnose.py          # 秩诊断、innies/outies、矛盾定位
│   ├── image.py             # 外框检测 + 虚线边界 + 并查集重建
│   ├── ocr.py               # tesseract / 模板匹配
│   └── render.py            # 文本 / 图片渲染
├── scripts/
│   └── solve_killer_sudoku.py   # CLI 入口
├── SKILL.md                 # Skill 描述文件
└── README.md                # 本文件
```

## 快速开始

### 1. 运行自检

```bash
cd killer-sudoku-solver_v2
python3 scripts/solve_killer_sudoku.py --selftest
```

预期输出：
```
自检通过：唯一解与预期一致（AC-3 已启用）
搜索节点: 3360
仅求和诊断: 方程 50 条，秩 47，自由度 34
```

### 2. 手动输入布局求解

```bash
python3 scripts/solve_killer_sudoku.py \
  --inline "22:a1,a2,a3,b3; 13:a4,a5; 3:b4,b5" \
  --explain
```

### 3. 从图片自动识别求解

```bash
python3 scripts/solve_killer_sudoku.py \
  --image-auto IMG_2978.jpeg \
  --debug-ocr /tmp/dbg \
  --image IMG_2978.jpeg \
  --out solved.png
```

## 依赖

| 包 | 用途 | 必需 |
|---|---|---|
| Python ≥ 3.9 | 运行时 | ✅ |
| Pillow | 图像读写与渲染 | ✅ |
| numpy | 图像采样分析 | ✅ |
| tesseract (CLI) | 数字识别 | ❌ 模板匹配兜底 |

安装：

```bash
pip install Pillow numpy
# 可选
brew install tesseract
```

## 输入格式

### 格式一：内联 / 文件（分号或换行分隔）

```
22: a1, a2, a3, b3;
13: a4, a5;
3:  b4, b5
```

行名 `a`–`i`，列名 `1`–`9`，也支持 `A1`、`r1c1`、`0,0` 等别名。

### 格式二：JSON

```json
{"cages": [{"sum": 22, "cells": ["a1","a2","a3","b3"]}]}
```

或简写：

```json
[[22, ["a1","a2","a3","b3"]], [13, ["a4","a5"]]]
```

## CLI 参数速查

### 输入方式（三选一）

| 参数 | 说明 |
|---|---|
| `--inline STR` | 内联布局字符串 |
| `--file PATH` | 从文本文件读布局 |
| `--json PATH` | 从 JSON 文件读，`-` 表示 stdin |
| `--image-auto PATH` | 从图片自动识别笼 + OCR 和值 |
| `--preset STR` | 常规数独已知格（`a1=4,b3=7` 或 JSON） |

### 求解控制

| 参数 | 默认 | 说明 |
|---|---|---|
| `--max-solutions N` | 2 | 最多搜几个解（2 足够判定唯一性） |
| `--node-limit N` | 5,000,000 | 搜索节点上限 |
| `--no-ac3` | 关 | 禁用 AC-3 弧一致性预处理 |
| `--cage-edge-threshold F` | 0.25 | 虚线边界检测阈值 |

### 诊断与输出

| 参数 | 说明 |
|---|---|
| `--explain` | 输出秩诊断 + innies/outies 提示 |
| `--diagnose-conflicts` | **NO_SOLUTION** 时定位最可疑的笼（耗时较长） |
| `--json-out` | 机器可读 JSON 输出 |
| `--image PATH` | 把解叠加到该题目图片 |
| `--out PATH` | 输出图片路径 |
| `--grid left,top,right,bottom` | 手动指定 9×9 外框（默认自动检测） |
| `--font PATH` / `--font-size N` | 自定义数字字体与字号 |
| `--debug-ocr DIR` | 把检测/识别的中间结果落盘 |
| `--selftest` | 运行内置已知盘面自检 |

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 有解（UNIQUE 或 MULTIPLE） |
| 1 | 无解（NO_SOLUTION） |
| 2 | 输入错误 / 布局校验失败 |
| 3 | 搜索超限（ABORTED） |

## 结果解读

- **UNIQUE** — 恰好 1 个解 ✓
- **MULTIPLE** — 至少 2 个解，约束不足
- **NO_SOLUTION** — 通常是转录错误：优先核对小和值多格的笼
- **ABORTED** — 超过节点上限，几乎总是布局有错

> **"仅求和约束 秩 自由度"**：只靠笼和 + 行列和（45）是欠定的，自由度 > 0 说明单靠求和无法逐格确定，必须依赖 1–9 不重复的离散约束。

## 架构说明

虚线笼边界检测的关键技术（已在 SELFTEST 图片上达到 **32/32 笼与 GT 完美匹配**）：

1. **采样位置**：在网格线位置 `xc[c+1]` 采样 ±14px 带内暗像素比例，而非格子内部。
2. **自适应阈值**：
   - **粗宫线**（baseline > 0.15）：固定阈值 **0.235**。粗宫线本身就暗，虚线叠加的段比 baseline 更暗，无虚线段比 baseline 略亮，0.235 恰好是两者中点。
   - **细线**（baseline ≤ 0.15）：`max(baseline - 0.015, 0.050)`，防止把纯背景误判为边界。
3. **并查集重建**：相邻格无边界则合并，最后兜底切分 > 9 格的笼。

求解器算法：

```
AC-3 预处理 → 反复收敛弧一致性 → 对所有单元落单值
      ↓
MRV 回溯 → 选候选最少的格子 → 每步用 can_form() 做子集和精确剪枝
      ↓
输出所有解（最多 N 个）
```

## 常见问题

**Q: NO_SOLUTION，不知道哪里错了？**
加 `--diagnose-conflicts`，脚本会尝试改每个笼的和值，找出改后能解的笼。

**Q: 图片检测出的笼数不对？**
调 `--cage-edge-threshold`（默认 0.25），加 `--debug-ocr /tmp/dbg` 看中间结果图，确认虚线是否画在网格线上。

**Q: 想要多解？**
加 `--max-solutions 100`，脚本会返回前 100 个。

**Q: 求解太慢？**
先检查布局是否有错（`--explain` 看自由度是否合理），再确认 AC-3 已启用。

## License

MIT
