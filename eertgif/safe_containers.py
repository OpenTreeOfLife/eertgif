from __future__ import annotations

import logging
import re

from pdfminer.layout import LTChar, LTTextLineHorizontal, LTTextLineVertical, LTAnno
from .util import AxisDir, DIM_TOL

log = logging.getLogger(__name__)


def safe_number(x):
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float):
        return float(x)
    raise TypeError(f"Expected number got {type(x)} for {x}")


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

    @property
    def bbox(self):
        return self.x0, self.y0, self.x1, self.y1


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
