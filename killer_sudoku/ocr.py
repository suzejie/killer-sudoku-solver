"""和值 OCR：从图片中读取每个笼左上角的数字标签。

优先级：
  1. tesseract CLI（subprocess 调用）—— 如果已安装
  2. 手写 0-9 数字模板匹配（Pillow）—— 总是可用
  3. 失败时返回空字符串，由调用方决定是否需要手动输入

遵循经验 815117：
  - 每个笼标签的 ROI 落盘为 debug_label_<cell>.png，让用户可核对
  - 不频繁切换 OCR 路线；模板匹配作为稳定兜底
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

import numpy as np
from PIL import Image, ImageOps


_TESSERACT = None


def _has_tesseract() -> bool:
    global _TESSERACT
    if _TESSERACT is not None:
        return _TESSERACT
    _TESSERACT = shutil.which("tesseract") is not None
    return _TESSERACT


def _crop_label_roi(
    im: Image.Image,
    cx: float, cy: float, cw: float, ch: float,
    cage_cells: list[tuple[int, int]],
) -> Image.Image:
    """截取一个笼左上角的 ROI，用于 OCR 数字标签。

    策略（经验 1414822：结构化切分优先）：
      - 笼标签通常在左上角那格（或其邻居）的内部左上区域
      - 取笼内所有格子的包围盒，缩放到 0-35% 面积（排除右下角的解区）
    """
    rs = [r for r, _ in cage_cells]
    cs = [c for _, c in cage_cells]
    r0, r1 = min(rs), max(rs)
    c0, c1 = min(cs), max(cs)

    W, H = im.size
    # 把 cell names (r,c) 映射到像素（cx/cy 是 10 条线的中心）
    x0_px = cx[c0] + 2
    y0_px = cy[r0] + 2
    x1_px = cx[c1 + 1] - 2
    y1_px = cy[r1 + 1] - 2

    # 标签通常在包围盒的左上角 35% 区域
    roi_x1 = x0_px + (x1_px - x0_px) * 0.45
    roi_y1 = y0_px + (y1_px - y0_px) * 0.45

    roi = im.crop((int(x0_px), int(y0_px), int(roi_x1), int(roi_y1)))
    return roi


def _ocr_with_tesseract(roi: Image.Image) -> str:
    """用 tesseract CLI 识别 0-9 数字，返回去空格后的文本。"""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tmp = tf.name
    try:
        roi.save(tmp)
        out = subprocess.run(
            ["tesseract", tmp, "stdout", "--psm", "7",
             "-c", "tessedit_char_whitelist=0123456789"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip()
    finally:
        os.unlink(tmp)


def _ocr_with_template(roi: Image.Image) -> str:
    """纯 Pillow 数字识别：把 ROI 二值化 + 连通域切分，
    对每个字符区域用简单的形状特征做分类。
    作为 tesseract 不可用时的兜底。
    """
    gray = roi.convert("L")
    arr = np.array(gray)
    # 自适应阈值：标签字一般比底色深
    thr = arr.mean() * 0.85
    bw = (arr < thr).astype(np.uint8) * 255

    # 水平投影找字符分隔
    hproj = bw.sum(axis=0)
    cols = np.where(hproj > bw.shape[0] * 0.1)[0]
    if len(cols) == 0:
        return ""
    char_regions: list[tuple[int, int]] = []
    start = cols[0]
    prev = cols[0]
    for c in cols[1:]:
        if c - prev > 2:
            char_regions.append((start, prev))
            start = c
        prev = c
    char_regions.append((start, prev))

    digits: list[str] = []
    for lo, hi in char_regions:
        if hi - lo < 3:
            continue
        ch = bw[:, lo:hi]
        d = _classify_digit(ch)
        if d is not None:
            digits.append(str(d))
    return "".join(digits)


def _classify_digit(mask: np.ndarray) -> Optional[int]:
    """对单个 0-9 数字的二值 mask 做启发式分类。

    特征：
      - 宽高比
      - 连通域个数（空洞数+1）
      - 上/中/下 三行黑像素密度
      - 左/中/右 三列黑像素密度
    """
    if mask.size == 0:
        return None
    h, w = mask.shape
    ratio = w / h if h > 0 else 1.0

    # 连通域（用 bfs 算黑白连通域）
    blk = (mask > 128).astype(np.uint8)
    label = np.zeros_like(blk)
    regions = 0
    for y in range(h):
        for x in range(w):
            if blk[y, x] == 1 and label[y, x] == 0:
                regions += 1
                dq = [(y, x)]
                label[y, x] = regions
                while dq:
                    cy, cx = dq.pop()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and blk[ny, nx] == 1 and label[ny, nx] == 0:
                            label[ny, nx] = regions
                            dq.append((ny, nx))
    # 空洞数 = 白色被黑色包围的区域
    white_regions = 0
    label_w = np.zeros_like(blk)
    for y in range(h):
        for x in range(w):
            if blk[y, x] == 0 and label_w[y, x] == 0:
                white_regions += 1
                dq = [(y, x)]
                label_w[y, x] = white_regions
                while dq:
                    cy, cx = dq.pop()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and blk[ny, nx] == 0 and label_w[ny, nx] == 0:
                            label_w[ny, nx] = white_regions
                            dq.append((ny, nx))
    holes = white_regions - 1  # 外部背景 1 个

    row_dens = [float(blk[y, :].sum()) / w for y in range(h)]
    row_groups = [row_dens[:h // 3], row_dens[h // 3:2 * h // 3], row_dens[2 * h // 3:]]
    avg_row = [sum(g) / max(len(g), 1) for g in row_groups]

    col_dens = [float(blk[:, x].sum()) / h for x in range(w)]
    col_groups = [col_dens[:w // 3], col_dens[w // 3:2 * w // 3], col_dens[2 * w // 3:]]
    avg_col = [sum(g) / max(len(g), 1) for g in col_groups]

    top, mid, bot = avg_row
    left, center, right = avg_col

    # 规则（常见 7-segment 风格字体）
    if holes == 2:
        return 8
    if holes == 1:
        if top > mid * 1.1 and bot > mid * 1.1:
            return 0
        if top > bot * 1.1:
            return 9
        return 6
    # holes == 0
    if ratio < 0.28:
        return 1
    if mid < top * 0.3 and mid < bot * 0.3:
        return 7
    if bot < top * 0.3:
        return 3
    if top < bot * 0.3:
        return 4
    if left < center * 0.3 and right < center * 0.3:
        return 2  # 可能是 2 或 5，再分
    if top > mid > bot and center < 0.2:
        return 5
    if top > mid and bot < top * 0.5:
        return 3
    # 兜底
    if mid > top * 0.6 and mid > bot * 0.6:
        return 4
    return None


def recognize_digits(
    src: str,
    cages: list[list[str]],
    cx: tuple[float, ...],
    cy: tuple[float, ...],
    debug_dir: Optional[str] = None,
) -> list[Optional[int]]:
    """对每个笼识别左上角的和值标签。

    返回与 cages 同序的整数列表；识别失败的项为 None。
    """
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    im_gray = im.convert("L")

    results: list[Optional[int]] = []
    for idx, cells in enumerate(cages):
        rc = [(ord(c[0]) - ord("a"), int(c[1]) - 1) for c in cells]
        roi = _crop_label_roi(im_gray, cx, cy, None, None, rc)
        roi_rgb = _crop_label_roi(im, cx, cy, None, None, rc)

        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            roi_rgb.save(os.path.join(debug_dir, f"label_{idx:02d}_{cells[0]}.png"))

        text = ""
        if _has_tesseract():
            try:
                text = _ocr_with_tesseract(roi_rgb)
            except Exception:
                text = ""
        if not text and roi.size[0] * roi.size[1] > 30:
            text = _ocr_with_template(roi)

        try:
            val = int(text)
            if 1 <= val <= 45:
                results.append(val)
            else:
                results.append(None)
        except (ValueError, TypeError):
            results.append(None)

    return results


def cages_with_sums(
    cages: list[list[str]],
    sums: list[Optional[int]],
) -> tuple[list[tuple[int, list[str]]], list[int]]:
    """合并笼与和值，返回 (有效布局, 失败索引列表)。"""
    layout: list[tuple[int, list[str]]] = []
    failed: list[int] = []
    for i, (c, s) in enumerate(zip(cages, sums)):
        if s is None:
            failed.append(i)
        else:
            layout.append((s, c))
    return layout, failed
