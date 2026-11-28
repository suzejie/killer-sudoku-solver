"""渲染：把解填入题目图片 + 文本格式化。"""

from __future__ import annotations

import os
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .core import ROWS


def _find_font(size: int, font_path: str | None = None):
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
    except TypeError:
        return ImageFont.load_default()


def render_solution(
    src: str,
    out: str,
    sol: list[int],
    grid,  # (x0,y0,x1,y1,x_centers,y_centers) 或 (x0,y0,x1,y1)
    font_path: str | None = None,
    font_size: int | None = None,
) -> tuple[float, float, float, float]:
    """把解逐格填入图片并保存，返回 (x0,y0,x1,y1)。"""
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    if len(grid) == 6:
        x0, y0, x1, y1, cx, cy = grid
    else:
        x0, y0, x1, y1 = grid
        cx = tuple(x0 + (x1 - x0) * i / 9 for i in range(10))
        cy = tuple(y0 + (y1 - y0) * i / 9 for i in range(10))

    cw = (x1 - x0) / 9.0
    ch = (y1 - y0) / 9.0
    size = int(font_size) if font_size else int(min(cw, ch) * 0.56)
    font = _find_font(max(8, size), font_path)
    draw = ImageDraw.Draw(im)
    stroke = max(1, size // 32)
    for r in range(9):
        for c in range(9):
            draw.text(
                ((cx[c] + cx[c + 1]) / 2, (cy[r] + cy[r + 1]) / 2),
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
    return (x0, y0, x1, y1)


def format_grid(sol: list[int]) -> str:
    lines = ["    " + " ".join(str(c) for c in range(1, 10))]
    lines.append("   " + "-" * 19)
    for r in range(9):
        vals = [str(sol[r * 9 + c]) for c in range(9)]
        lines.append(f" {ROWS[r]}  " + " ".join(vals))
        if r in (2, 5):
            lines.append("   " + "-" * 19)
    return "\n".join(lines)


def parse_grid_spec(s: str) -> tuple[float, float, float, float]:
    parts = [p for p in re.split(r"[,\s]+", s.strip()) if p]
    if len(parts) != 4:
        raise ValueError("--grid 需要 4 个数: left,top,right,bottom")
    x0, y0, x1, y1 = (float(p) for p in parts)
    if not (x1 > x0 and y1 > y0):
        raise ValueError("--grid 要求 right>left 且 bottom>top")
    return (x0, y0, x1, y1)
