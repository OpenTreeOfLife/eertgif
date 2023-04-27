#!/usr/bin/env python3
from __future__ import annotations

import logging
from enum import IntEnum
from math import sqrt
from typing import List, Any, Tuple, Union, Iterable
import re
import os
import time
from threading import Thread
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


orientation_to_direction = {
    "left": Direction.WEST,
    "right": Direction.EAST,
    "up": Direction.NORTH,
    "down": Direction.SOUTH,
}


class CurveShape(IntEnum):
    LINE = 0
    CORNER_LL = 1  # └
    CORNER_UL = 2  # ┌
    CORNER_UR = 3  # ┐
    CORNER_LR = 4  # ┘
    LINE_LIKE = 5
    COMPLICATED = 6
    DOT = 7


# See doc of bbox_to_corners
corners_order = (
    CurveShape.CORNER_LL,
    CurveShape.CORNER_UL,
    CurveShape.CORNER_UR,
    CurveShape.CORNER_LR,
)

all_corner_shapes = frozenset(corners_order)


class AxisDir(IntEnum):
    UNKNOWN = 0
    HORIZONTAL = 1
    VERTICAL = 2


CARDINAL = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
BOX_TO_LINE_TOL = 4.0


class DisplayMode(IntEnum):
    CURVES_AND_TEXT = 0  # Initial import, no analysis done
    COMPONENTS = 1  # creation of a forest based on node detection, but no tree
    PHYLO = 2  # tree has been extracted


class Penalty(IntEnum):
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


def find_closest(loc: Point, el_list: Iterable[Any]) -> Tuple[float, Any]:
    """Uses .loc of every el in el_list."""
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


def mean_vector(list_of_pairs):
    """Return mean of ((second[0] - first[0]), (second[1] - first[1])) for each (first, second) pair in `list_of_pairs`"""
    if not list_of_pairs:
        return 0.0, 0.0
    sum_x_diff, sum_y_diff = 0.0, 0.0
    for blob in list_of_pairs:
        first, second = blob[:2]
        x_off = second[0] - first[0]
        y_off = second[1] - first[1]
        sum_x_diff += x_off
        sum_y_diff += y_off
        log.debug(f'x_off={x_off}   y_off={y_off}, text="{blob[2].strip()}"')
    n = len(list_of_pairs)
    return sum_x_diff / n, sum_y_diff / n


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


class ExtractionConfig(object):
    choice_dict = {
        "orientation": ("right", "up", "down", "left"),
        "viz_highlight_mode": (
            "element",
            "neighbors",
            "neighbors-only",
            "component",
            "component-only",
        ),
    }
    non_bool_keys = ("display_mode", "force_trashed_ids")
    tol_keys = ("box_to_line_tol", "node_merge_tol", "rect_base_intercept_tol")
    bool_keys = (
        "is_rect_shape",
        "viz_hide_text",
        "viz_hide_nodes",
        "viz_hide_edges",
        "viz_simplify_curves",
        "viz_show_trashed",
    )
    defaults = {
        "orientation": "right",
        "display_mode": DisplayMode.CURVES_AND_TEXT,
        "force_trashed_ids": [],
        "is_rect_shape": False,
        "box_to_line_tol": BOX_TO_LINE_TOL,  # used in SafeCurve diagnose_shape
        "rect_base_intercept_tol": 0.01,
        "node_merge_tol": 0.01,
        "viz_hide_text": False,
        "viz_hide_nodes": False,
        "viz_hide_edges": False,
        "viz_highlight_mode": "element",
        "viz_simplify_curves": False,
        "viz_show_trashed": False,
    }
    all_keys = tuple(
        list(choice_dict.keys())
        + list(non_bool_keys)
        + list(tol_keys)
        + list(bool_keys)
    )

    def dict_for_json(self):
        d = {}
        for k in ExtractionConfig.all_keys:
            d[k] = getattr(self, k)
        d["display_mode"] = int(d["display_mode"])
        return d

    def __init__(self, obj=None, second_level=None):
        if obj is None:
            obj = {}
        if second_level is None:
            second_level = {}
        for key, choices in ExtractionConfig.choice_dict.items():
            self._init_set(
                key,
                obj,
                second_level,
                lambda val: isinstance(val, str) and (val in choices),
            )
        self._init_set(
            "display_mode", obj, second_level, transform=lambda val: DisplayMode(val)
        )
        self._init_set(
            "force_trashed_ids",
            obj,
            second_level,
            predicate=lambda val: isinstance(val, list),
            transform=lambda val: [int(i) for i in val],
        )

        for k in ExtractionConfig.tol_keys:
            self._init_set(
                k,
                obj,
                second_level,
                lambda val: (isinstance(val, float) or isinstance(val, int))
                and val >= 0.0,
            )
        for k in ExtractionConfig.bool_keys:
            self._init_set(k, obj, second_level, lambda val: isinstance(val, bool))

    def _init_set(self, attr, primary, secondary, predicate=None, transform=None):
        v = primary.get(attr)
        vs = secondary.get(attr)
        if v is None:
            if vs is None:
                setattr(self, attr, ExtractionConfig.defaults[attr])
                return
            v = vs
        assert v is not None
        if (predicate is not None) and (not predicate(v)):
            raise ValueError("attribute {attr} failed precondition test")
        if transform is not None:
            try:
                v = transform(v)
            except:
                raise ValueError("attribute {attr} failed transformation")
        setattr(self, attr, v)

    def get(self, key, default=None):
        if key not in ExtractionConfig.all_keys:
            raise KeyError(f"{key} is not supported by ExtractionConfig")
        return getattr(self, key, default)

    def __contains__(self, key):
        return hasattr(self, key)

    def __getitem__(self, key):
        if key not in ExtractionConfig.all_keys:
            raise KeyError(f"{key} is not supported by ExtractionConfig")
        return self.__dict__[key]

    def __setitem__(self, key, val):
        if key not in ExtractionConfig.all_keys:
            raise KeyError(f"{key} is not supported by ExtractionConfig")
        setattr(self, key, val)


def sleep_til_can_remove(fp):
    sleep_duration = 1
    while os.path.exists(fp):
        time.sleep(sleep_duration)
        try:
            os.remove(fp)
        except:
            pass
        else:
            return
        if sleep_duration < 1024:
            sleep_duration *= 2


def win_safe_rename(src, dest):
    try:
        os.rename(src, dest)
    except:
        if os.path.exists(src):
            shutil.copyfile(src, dest)
            x = Thread(target=sleep_til_can_remove, args=(os.path.abspath(src),))
            x.start()
        else:
            raise RuntimeError(f'"{src}" does not exist')


def win_safe_remove(fp):
    try:
        os.remove(fp)
    except:
        if os.path.exists(fp):
            x = Thread(target=sleep_til_can_remove, args=(os.path.abspath(fp),))
            x.start()


def next_uniq_fp(directory, prefix, suffix):
    start = os.path.join(directory, prefix)
    idx = 0
    while True:
        fp = f"{start}-v{idx}{suffix}"
        if not os.path.exists(fp):
            return fp
        idx += 1
