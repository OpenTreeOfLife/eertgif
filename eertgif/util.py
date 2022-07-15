#!/usr/bin/env python3
from __future__ import annotations

import logging
from enum import IntEnum, Enum
from math import sqrt
from typing import List, Any, Tuple, Union
import re

from pdfminer.utils import Point, Rect

log = logging.getLogger(__name__)

COORD_TOL = 1.0e-3
DIM_TOL = COORD_TOL
MIN_BR_TOL = 1.0e-4
DEFAULT_LABEL_GAP = 10


class Direction(IntEnum):
    SAME = 0
    NORTH = 0x01
    NORTHEAST = 0x05
    EAST = 0x04
    SOUTHEAST = 0x06
    SOUTH = 0x02
    SOUTHWEST = 0x0A
    WEST = 0x08
    NORTHWEST = 0x09


class CurveShape(IntEnum):
    LINE = 0
    CORNER_LL = 1  # └
    CORNER_UL = 2  # ┌
    CORNER_UR = 3  # ┐
    CORNER_LR = 4  #  ┘
    LINE_LIKE = 5
    COMPLICATED = 6
    DOT = 7


class AxisDir(IntEnum):
    UNKNOWN = 0
    HORIZONTAL = 1
    VERTICAL = 2


CARDINAL = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


class DisplayMode:
    CURVES_AND_TEXT = 0  # Initial import, no analysis done
    COMPONENTS = 1  # creation of a forest based on node detection, but no tree
    PHYLO = 2  # tree has been extracted


class Penalty(Enum):
    LABEL_GAP_MEAN = 0
    LABEL_GAP_STD_DEV = 1
    UNMATCHED_LABELS = 2
    WRONG_DIR_TO_PAR = 3


def rotate_cw(tip_dir: Direction) -> Direction:
    deg_90 = {
        Direction.SAME: Direction.SAME,
        Direction.NORTH: Direction.EAST,
        Direction.NORTHEAST: Direction.SOUTHEAST,
        Direction.EAST: Direction.SOUTH,
        Direction.SOUTHEAST: Direction.SOUTHWEST,
        Direction.SOUTH: Direction.WEST,
        Direction.SOUTHWEST: Direction.NORTHWEST,
        Direction.WEST: Direction.NORTH,
        Direction.NORTHWEST: Direction.NORTHEAST,
    }
    return deg_90[tip_dir]


def midpoint(rect: Rect):
    x0, y0, x1, y1 = rect
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def calc_dist(pt1: Point, pt2: Point) -> float:
    xsq = (pt1[0] - pt2[0]) ** 2
    ysq = (pt1[1] - pt2[1]) ** 2
    return sqrt(xsq + ysq)


def find_closest(loc: Point, el_list: List[Any]) -> Tuple[float, Any]:
    dist, closest = float("inf"), None
    for el in el_list:
        d = calc_dist(loc, el.loc)
        if d < dist:
            dist = d
            closest = el
    return dist, closest


def find_closest_first(tup, tup_list):
    """assumes first element in tup and each tuple of tup_list is a loc.

    Returns the closest element from tup_list.
    """
    loc = tup[0]
    min_dist, closest = float("inf"), None
    for tl_el in tup_list:
        tl_loc = tl_el[0]
        d = calc_dist(loc, tl_loc)
        if d < min_dist:
            min_dist = d
            closest = tl_el
    return min_dist, closest


def avg_char_width(text_list: List) -> float:
    assert text_list
    sum_len, num_chars = 0.0, 0
    for label in text_list:
        sum_len += label.width
        num_chars += len(label.get_text())
    return sum_len / num_chars


def mean_var(flist: List[float]) -> Tuple[Union[float, None], Union[float, None]]:
    n = len(flist)
    if n < 2:
        if n == 0:
            return None, None
        return flist[0], None
    mean, ss = 0.0, 0.0
    for el in flist:
        mean += el
        ss += el * el
    mean = mean / n
    var_num = ss - n * mean * mean
    var = var_num / (n - 1)
    return mean, var


starts_num_pat = re.compile(r"^([-.eE0-9]+).*")


def as_numeric(label):
    m = starts_num_pat.match(label.strip())
    if m:
        g = m.group(1)
        try:
            n = int(g)
        except ValueError:
            pass
        else:
            return True, n
        try:
            f = float(g)
        except ValueError:
            pass
        else:
            return True, f
    return False, None


def bbox_to_corners(bbox: Rect) -> Tuple[Tuple[Point, Point]]:
    """Bounding box to 4 pairs of coordinates.
    assuming min x = left, and min y = Down
    Corners in (LowerLeft, UpperLeft, UpperRight, LowerRight)).
    """
    tx0, ty0, tx1, ty1 = bbox
    x0 = min(tx0, tx1)
    x1 = max(tx0, tx1)
    y0 = min(ty0, ty1)
    y1 = max(ty0, ty1)
    return ((x0, y0), (x0, y1), (x1, y1), (x1, y0))
