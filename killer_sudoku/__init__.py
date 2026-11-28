"""杀手数独求解器 —— 职责分离的模块化实现。"""

from .core import (
    ROWS,
    CELLS,
    CELL_ID,
    ALL,
    popcount,
    REACH,
    can_form,
    min_sum,
    max_sum,
)
from .layout import (
    parse_inline,
    parse_json_obj,
    load_layout,
    validate,
    is_connected,
    alias_normalize,
)
from .solver import KillerSudokuSolver
from .diagnose import sum_only_diagnostics, find_conflicts, innies_outies
from .image import (
    detect_grid,
    detect_cages_from_image,
    group_centers,
)
from .ocr import recognize_digits
from .render import render_solution, format_grid

__all__ = [
    "ROWS",
    "CELLS",
    "CELL_ID",
    "ALL",
    "popcount",
    "REACH",
    "can_form",
    "min_sum",
    "max_sum",
    "parse_inline",
    "parse_json_obj",
    "load_layout",
    "validate",
    "is_connected",
    "alias_normalize",
    "KillerSudokuSolver",
    "sum_only_diagnostics",
    "find_conflicts",
    "innies_outies",
    "detect_grid",
    "detect_cages_from_image",
    "group_centers",
    "recognize_digits",
    "render_solution",
    "format_grid",
]
