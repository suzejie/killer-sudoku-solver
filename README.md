Read this in other languages: [English](README.md), [中文](README.zh.md)

# Killer Sudoku Solver

A Python solver for Killer Sudoku puzzles. Given a cage layout or an image of a puzzle, it outputs **UNIQUE / MULTIPLE / NO_SOLUTION** and can optionally overlay the answer back onto the original image.

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Pillow](https://img.shields.io/badge/Pillow-10.x-green.svg)](https://pillow.readthedocs.io/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)](#)

---

## Features

- 🧩 **Exact solver**: bitmask MRV + AC-3 arc consistency + precise subset-sum pruning
- 📸 **Automatic cage detection**: adaptive threshold for dashed cage boundaries + union-find reconstruction (32/32 cages verified on SELFTEST image)
- 🔢 **Sum OCR**: tesseract first, template-matching fallback
- 🩺 **Diagnostic toolkit**: rank analysis, innies-outies, conflict localization
- 🖼️ **Answer overlay**: auto-detect board, draw digits into each cell

## Directory Structure

```
killer-sudoku-solver_v2/
├── killer_sudoku/
│   ├── core.py              # Precomputed tables (REACH / can_form / popcount)
│   ├── layout.py            # Layout parsing, alias normalization, validation
│   ├── solver.py            # Solver class: AC-3 + MRV + pruning
│   ├── diagnose.py          # Rank diagnostics, innies/outies, conflict lookup
│   ├── image.py             # Board detection + dashed cage edges + union-find
│   ├── ocr.py               # tesseract / template matching
│   └── render.py            # Text / image rendering
├── scripts/
│   └── solve_killer_sudoku.py   # CLI entry point
├── SKILL.md
├── README.md                # This file (Chinese)
└── README.en.md             # English
```

## Quick Start

### 1. Run the built-in selftest

```bash
cd killer-sudoku-solver_v2
python3 scripts/solve_killer_sudoku.py --selftest
```

Expected output:
```
自检通过：唯一解与预期一致（AC-3 已启用）
搜索节点: 3360
仅求和诊断: 方程 50 条，秩 47，自由度 34
```

### 2. Solve from a manual layout

```bash
python3 scripts/solve_killer_sudoku.py \
  --inline "22:a1,a2,a3,b3; 13:a4,a5; 3:b4,b5" \
  --explain
```

### 3. End-to-end from an image

```bash
python3 scripts/solve_killer_sudoku.py \
  --image-auto IMG_2978.jpeg \
  --debug-ocr /tmp/dbg \
  --image IMG_2978.jpeg \
  --out solved.png
```

## Dependencies

| Package | Purpose | Required |
|---|---|---|
| Python ≥ 3.9 | Runtime | Yes |
| Pillow | Image I/O & rendering | Yes |
| numpy | Image sampling analysis | Yes |
| tesseract (CLI) | Digit OCR | No — template fallback |

Installation:

```bash
pip install Pillow numpy
# Optional
brew install tesseract
```

## Input Formats

### Option A: inline / file (semicolons or newlines)

```
22: a1, a2, a3, b3;
13: a4, a5;
3:  b4, b5
```

Row names `a`–`i`, columns `1`–`9`. Also accepts aliases: `A1`, `r1c1`, `0,0`.

### Option B: JSON

```json
{"cages": [{"sum": 22, "cells": ["a1","a2","a3","b3"]}]}
```

Or the shorthand:

```json
[[22, ["a1","a2","a3","b3"]], [13, ["a4","a5"]]]
```

## CLI Reference

### Input

| Flag | Description |
|---|---|
| `--inline STR` | Inline layout string |
| `--file PATH` | Layout from text file |
| `--json PATH` | Layout from JSON file, `-` for stdin |
| `--image-auto PATH` | Detect cages + OCR sums from image (experimental) |
| `--preset STR` | Known cells for regular sudoku (`a1=4,b3=7` or JSON) |

### Solver Control

| Flag | Default | Description |
|---|---|---|
| `--max-solutions N` | 2 | How many solutions to find (2 is enough for uniqueness) |
| `--node-limit N` | 5,000,000 | Search node ceiling |
| `--no-ac3` | off | Disable AC-3 arc consistency preprocessing |
| `--cage-edge-threshold F` | 0.25 | Detection threshold for dashed cage edges |

### Diagnostics & Output

| Flag | Description |
|---|---|
| `--explain` | Print rank analysis + innies/outies tips |
| `--diagnose-conflicts` | When NO_SOLUTION, try to locate the most suspicious cage (slower) |
| `--json-out` | Machine-readable JSON output |
| `--image PATH` | Overlay solution onto the given puzzle image |
| `--out PATH` | Output image path |
| `--grid left,top,right,bottom` | Manually specify the 9×9 board corners (auto-detected by default) |
| `--font PATH` / `--font-size N` | Custom digit font and size |
| `--debug-ocr DIR` | Dump OCR / detection intermediate results to this directory |
| `--selftest` | Run the built-in known-board selftest |

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Solutions found (UNIQUE or MULTIPLE) |
| 1 | No solution |
| 2 | Input error / layout validation failed |
| 3 | Search aborted (node limit reached) |

## Interpreting Results

- **UNIQUE** — exactly one solution ✓
- **MULTIPLE** — at least two solutions; constraints are insufficient
- **NO_SOLUTION** — almost always a transcription error; check small-sum / multi-cell cages first
- **ABORTED** — node limit exceeded; virtually always a broken layout

> **"Sum-only constraint: equations, rank, degrees of freedom"** — the cage-sum plus row/column sums (= 45) is underdetermined. A positive degrees-of-freedom means you can't pin down every cell with sums alone; the discrete 1–9 no-repeat constraint is essential.

## How the Cage Detection Works

This is the trickiest part of the pipeline. It achieves **32/32 cage match with ground truth** on the SELFTEST image.

1. **Sampling position**: sample the dark-pixel fraction in a ±14px band centered on each *grid line* `xc[c+1]`, not the cell midlines.
2. **Adaptive threshold per line**:
   - **Thick palace lines** (baseline > 0.15): fixed threshold **0.235**. These lines are already dark from the board's major grid; dashed edges make them *darker*, while plain segments are slightly brighter. 0.235 sits exactly between them.
   - **Thin lines** (baseline ≤ 0.15): `max(baseline - 0.015, 0.050)`. Prevents pure background from being mistaken for a cage boundary.
3. **Union-find rebuild**: merge adjacent cells without a detected border, then auto-split any cage larger than 9 cells as a safety net.

The solver side:

```
AC-3 preprocessing → iteratively propagate arc consistency → fix singletons
        ↓
MRV backtracking → pick the cell with fewest candidates → can_form() subset-sum pruning at every step
        ↓
Output all solutions (up to N)
```

## FAQ

**Q: NO_SOLUTION and I don't know where the typo is.**
Add `--diagnose-conflicts`. The script tries small perturbations to each cage's sum and reports which ones make the puzzle solvable.

**Q: Wrong number of cages detected from my image?**
Tune `--cage-edge-threshold` (default 0.25) and add `--debug-ocr /tmp/dbg` to inspect the intermediate cage-edge image. Confirm the dashed edges are drawn *on* the grid lines.

**Q: I want more than 2 solutions.**
Use `--max-solutions 100`. The solver will return the first 100 it finds.

**Q: Solver is too slow.**
First run `--explain` and check that the degrees of freedom look sensible. Then confirm AC-3 is enabled (default).

## License

MIT
