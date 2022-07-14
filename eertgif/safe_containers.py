from __future__ import annotations

import logging
import re
from enum import IntEnum
from typing import Tuple, Optional
from pdfminer.utils import Point
from pdfminer.layout import LTChar, LTTextLineHorizontal, LTTextLineVertical, LTAnno
from .util import AxisDir, DIM_TOL, bbox_to_corners, calc_dist

log = logging.getLogger(__name__)


class CurveShape(IntEnum):
    LINE = 0
    CORNER_LL = 1  # └
    CORNER_UL = 2  # ┌
    CORNER_UR = 3  # ┐
    CORNER_LR = 4  #  ┘
    LINE_LIKE = 5
    COMPLICATED = 6
    DOT = 7


# pretty arbitrary guess, here. distance to count as "near" a corner
#   in curve shape diagnosis. Might need to depend on some scale of page or page element
CORNER_TOL = 2


def safe_number(x):
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float):
        return float(x)
    raise TypeError(f"Expected number got {type(x)} for {x}")


# See doc of bbox_to_corners
_corners_order = (
    CurveShape.CORNER_LL,
    CurveShape.CORNER_UL,
    CurveShape.CORNER_UR,
    CurveShape.CORNER_LR,
)


class SafeCurve(object):
    def __init__(self, lt_curve, eertgif_id):
        self.eertgif_id = eertgif_id
        self.x0 = safe_number(lt_curve.x0)
        self.y0 = safe_number(lt_curve.y0)
        self.x1 = safe_number(lt_curve.x1)
        self.y1 = safe_number(lt_curve.y1)
        self.width = safe_number(lt_curve.width)
        self.height = safe_number(lt_curve.height)
        self.linewidth = safe_number(lt_curve.linewidth)
        self.stroke = bool(lt_curve.stroke)
        self.fill = bool(lt_curve.fill)
        self.evenodd = bool(lt_curve.evenodd)
        if lt_curve.stroking_color is None:
            self.stroking_color = None
        else:
            self.stroking_color = [safe_number(i) for i in lt_curve.stroking_color]
        if lt_curve.non_stroking_color is None:
            self.non_stroking_color = None
        else:
            self.non_stroking_color = [
                safe_number(i) for i in lt_curve.non_stroking_color
            ]
        self.pts = [(safe_number(x), safe_number(y)) for x, y in lt_curve.pts]
        # Note eff_diagonal (the effective) may contain bounding box points, any member of pts
        self.shape, self.eff_diagonal = self._diagnose_shape()

    @property
    def bbox(self):
        return self.x0, self.y0, self.x1, self.y1

    def _diagnose_shape(
        self, in_corner_tol: float = CORNER_TOL
    ) -> Tuple[CurveShape, Optional[Tuple[Point, Point]]]:
        """called to fill in the "shape" attribute from bbox and points.

        """
        assert self.pts
        pts = self.pts
        if len(pts) == 1:
            return CurveShape.DOT, (pts[0], pts[0])
        if len(pts) == 2:
            return CurveShape.LINE, (pts[0], pts[1])
        corners = bbox_to_corners(self.bbox)
        is_corner_shaped, shape, eff_dir = _diagnose_corner_shaped(
            pts, corners, in_corner_tol=in_corner_tol
        )
        if is_corner_shaped or (shape in {CurveShape.DOT, CurveShape.LINE_LIKE}):
            return shape, eff_dir
        return _diagnose_line_like_not_cornered(pts, corners)


def _diagnose_corner_shaped(pts, corners, in_corner_tol=CORNER_TOL):
    all_close_to_corner = True
    closest_corners = set()
    max_dist = float("inf")
    for pt in pts:
        closest_dir = None
        closest_dist = max_dist
        for n, c in enumerate(corners):
            d = calc_dist(pt, c)
            if d <= in_corner_tol and d < closest_dist:
                closest_dist = d
                closest_dir = _corners_order[n]
        if closest_dir is None:
            return False, None, None
        else:
            closest_corners.add(closest_dir)
    if len(closest_corners) == 4:
        return False, CurveShape.COMPLICATED, None
    if len(closest_corners) == 1:
        # might happen due to dots with rounding error preferring same corner?
        cc = next(iter(closest_corners))
        idx = _corners_order.index(cc)
        cp = corners[idx]
        return False, CurveShape.DOT, None, (cp, cp)
    if len(closest_corners) == 3:
        if CurveShape.CORNER_LR not in closest_corners:
            return True, CurveShape.CORNER_UL, (corners[0], corners[2])
        if CurveShape.CORNER_LL not in closest_corners:
            return True, CurveShape.CORNER_UR, (corners[1], corners[3])
        if CurveShape.CORNER_UR not in closest_corners:
            return True, CurveShape.CORNER_LL, (corners[1], corners[3])
        assert CurveShape.CORNER_UL not in closest_corners
        return True, CurveShape.CORNER_LR, (corners[0], corners[2])
    assert len(closest_corners) == 2
    # all points close to corner, but
    first, second = list(closest_corners)
    fidx, sidx = _corners_order.index(first), _corners_order.index(second)
    return False, CurveShape.LINE_LIKE, (corners[fidx], corners[sidx])


def _diagnose_line_like_not_cornered(pts, corners):
    by_x_t = [(i[0], i) for i in pts]
    by_y_t = [(i[1], i) for i in pts]
    by_x_t.sort()
    by_y_t.sort()
    by_x = [i[1] for i in by_x_t]
    by_y = [i[1] for i in by_y_t]
    if by_x == by_y:
        return CurveShape.LINE_LIKE, (by_x[0], by_x[-1])
    rev_by_y = by_y[::-1]
    if by_x == rev_by_y:
        return CurveShape.LINE_LIKE, (by_x[0], by_x[-1])
    return CurveShape.COMPLICATED, None


class SafeFont(object):
    def __init__(self, font_desc):
        assert isinstance(font_desc, str)
        self.font_desc = font_desc
        self._lc_font_desc = font_desc.lower()
        if "+" in self.font_desc:
            self._after_plus = "+".join(self.font_desc.split("+")[1:])
        else:
            self._after_plus = self.font_desc
        self._bef_dash = self._after_plus.split("-")[0]
        self.font_style = "normal"
        if "italic" in self._lc_font_desc:
            self.font_style = "italic"
        elif "oblique" in self._lc_font_desc:
            self.font_style = "oblique"
        self.font_weight = "normal"
        if "bold" in self._lc_font_desc:
            self.font_weight = "bold"

    @property
    def font_family(self):
        return self._bef_dash


_cid_num_pat = re.compile(r"^[(]cid:(\d+)[)]$")
REPLACE_CHAR = "�"


def _safe_char(el):
    ch_text = el.get_text()
    if len(ch_text) == 1:
        return ch_text
    m = _cid_num_pat.match(ch_text)
    # matched_font = None
    # for v in pdf_interpret.fontmap.values():
    #     if v.fontname == f:
    #         matched_font = v
    #         break
    if m:
        cidn = int(m.group(1))
        log.debug(f"inserting missing char instead of cid:{cidn} code")
        return REPLACE_CHAR
    msg = f"multi-character LTChar/LTAnno text '{ch_text}' not matching cid pattern"
    log.debug(msg)
    raise RuntimeError(msg)


class SafeTextLine(object):
    """Slimmed down version of LTLine designed to be safe for pickling."""

    def __init__(self, lt_line, eertgif_id, font_dict, pdf_interpret=None):
        self.eertgif_id = eertgif_id
        self.x0 = safe_number(lt_line.x0)
        self.y0 = safe_number(lt_line.y0)
        self.x1 = safe_number(lt_line.x1)
        self.y1 = safe_number(lt_line.y1)
        assert abs(self.height - lt_line.height) < DIM_TOL
        assert abs(self.width - lt_line.width) < DIM_TOL
        self.word_margin = lt_line.word_margin
        if isinstance(lt_line, LTTextLineHorizontal):
            self.direction = AxisDir.HORIZONTAL
        elif isinstance(lt_line, LTTextLineVertical):
            self.direction = AxisDir.VERTICAL
        else:
            self.direction = AxisDir.UNKNOWN
        all_fonts = set()
        font_for_char = []
        prev_font = None
        el_count = 0
        char_list = []
        for el in lt_line:
            if isinstance(el, LTChar):
                f = el.fontname
                safe_font = font_dict.get(f)
                if safe_font is None:
                    safe_font = SafeFont(f)
                    font_dict[f] = safe_font
                all_fonts.add(safe_font)
                prev_font = safe_font
            else:
                assert isinstance(el, LTAnno)
            font_for_char.append(prev_font)
            char_list.append(_safe_char(el))
            el_count += 1
        self.text = "".join(char_list)

        if len(font_for_char) != len(self.text):
            tfel = []
            for el in lt_line:
                if isinstance(el, LTChar):
                    tfel.append(f" {el._text} ")
                else:
                    tfel.append(f"({el._text})")
            st = list(self.text)
            spaced = f" {'  '.join(st)} "
            log.debug(f"font, char mismatch\n  '{spaced}'\n  '{''.join(tfel)}'")

        if len(all_fonts) == 1:
            self.font = font_for_char[0]
        else:
            self.font = font_for_char
            if all_fonts:
                if font_for_char and font_for_char[0] is None:
                    fnnf = None
                    for f in font_for_char:
                        if f is not None:
                            fnnf = f
                            break
                    assert fnnf is not None
                    idx = 0
                    while True:
                        if font_for_char[idx] is None:
                            font_for_char[idx] = fnnf
                            idx += 1
                        else:
                            break
            else:
                log.debug("Text line lacking any font")
        if self.font is None:
            assert self.font is not None

    def get_text(self):
        return self.text

    @property
    def height(self):
        return self.y1 - self.y0

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def bbox(self):
        return self.x0, self.y0, self.x1, self.y1

    @property
    def is_all_one_font(self):
        return isinstance(self.font, SafeFont)

    def font_for_index(self, idx):
        if self.is_all_one_font:
            return self.font
        return self.font[idx]


def convert_to_safe_line(text_lines, eertgif_id, font_dict, pdf_interpret=None):
    sl = []
    for line in text_lines:
        sl.append(
            SafeTextLine(
                line,
                eertgif_id=eertgif_id,
                font_dict=font_dict,
                pdf_interpret=pdf_interpret,
            )
        )
        eertgif_id += 1
    return sl, eertgif_id


def convert_to_safe_curves(curves, eertgif_id):
    sl = []
    for curve in curves:
        sl.append(SafeCurve(curve, eertgif_id=eertgif_id))
        eertgif_id += 1
    return sl, eertgif_id


class UnprocessedRegion(object):
    def __init__(self, text_lines, nontext_objs, container, pdf_interpret=None):
        self.page_num = None
        self.subpage_num = None
        eertgif_id = 0
        self.font_dict = {}
        self.text_lines, eertgif_id = convert_to_safe_line(
            text_lines, eertgif_id, self.font_dict, pdf_interpret=pdf_interpret
        )
        self.nontext_objs, eertgif_id = convert_to_safe_curves(nontext_objs, eertgif_id)
        self.container_bbox = tuple(container.bbox)
        assert isinstance(self.container_bbox, tuple)
        assert len(self.container_bbox) == 4
        for el in self.container_bbox:
            assert isinstance(el, float) or isinstance(el, int)
        log.debug(f"UnprocessedRegion fonts descriptors={list(self.font_dict.keys())}")

    @property
    def has_content(self):
        return bool(self.text_lines) or bool(self.nontext_objs)

    @property
    def tag(self):
        if self.page_num is None:
            assert self.subpage_num is None
            return ""
        if self.subpage_num is not None:
            return f"{self.page_num}-{self.subpage_num}"
        return str(self.page_num)
