#!/usr/bin/env python3
from __future__ import annotations

import html
import logging

from io import StringIO

log = logging.getLogger("eertgif.to_svg")


class SVGStyling:
    def __init__(self):
        pass


# treat as immutable
_def_style = SVGStyling()


def to_html(out, obj_container=None, styling=None):
    out.write(
        f"""<!DOCTYPE html>
<html>
<body>
<div>
"""
    )
    to_svg(out, obj_container=obj_container, styling=styling)
    out.write(
        """</div>
</body>
</html>
"""
    )


def get_svg_str(obj_container=None, styling=None):
    x = StringIO()
    to_svg(x, obj_container=obj_container)
    return x.getvalue()


def to_svg(out, obj_container=None, styling=None):
    from .safe_containers import SafeCurve

    styling = styling if styling is not None else _def_style
    assert obj_container is not None
    cbb = obj_container.container_bbox
    height = cbb[3] - cbb[1]
    width = cbb[2] - cbb[0]
    xfn = lambda x: x - cbb[0]
    yfn = lambda y: cbb[3] - y  # pdf y=0 is bottom, but svg is top

    out.write(
        f"""<svg viewBox="0 0 {width} {height}" > 
"""
    )
    # log.debug(f"obj_container.nontext_objs = {obj_container.nontext_objs}")
    for n, o in enumerate(obj_container.nontext_objs):
        if isinstance(o, SafeCurve):
            curve_as_path(out, o, xfn, yfn, styling=styling)
        else:
            log.debug(f"Skipping {o} in SVG export...\n")
    # log.debug(f"obj_container.text_lines = {obj_container.nontext_objs}")
    for n, text in enumerate(obj_container.text_lines):
        text_as_text_el(out, text, xfn, yfn, styling)
    out.write("</svg>")


def text_as_text_el(out, text, xfn, yfn, styling):
    midheight = (yfn(text.y1) + yfn(text.y0)) / 2
    atts = [f'x="{xfn(text.x0)}"', f'y="{midheight}"']
    eertgif_id = getattr(text, "eertgif_id", None)
    if eertgif_id is not None:
        atts.append(f'eeertgif_id="{eertgif_id}"')
    length = abs(xfn(text.x1) - xfn(text.x0))
    atts.append(f'textLength="{length}"')
    atts.append(f'textAdjust="spacingAndGlyphs"')
    atts.append(f'font-size="{int(text.height)}px"')
    if text.is_all_one_font:
        _append_atts_for_font(text.font, atts)
        proc = html.escape(text.get_text().strip())
        s = f' <text {" ".join(atts)} >{proc}</text>\n'
        out.write(s)
        return
    prev_font = None
    out.write(f' <text {" ".join(atts)} >')
    curr_font_chars = []
    for idx, char in enumerate(text.get_text().strip()):
        f = text.font_for_index(idx)
        if f is None:
            log.debug(f"No font found for index {idx} of {text.get_text()}")
            curr_font_chars.append(char)
            continue
        if prev_font is None or f == prev_font:
            pass
        elif curr_font_chars:
            _write_tspan(out, prev_font, curr_font_chars)
            curr_font_chars = []
        curr_font_chars.append(char)
        prev_font = f
    if curr_font_chars:
        _write_tspan(out, prev_font, curr_font_chars)
    out.write("</text>")


def _write_tspan(out, font, char_list):
    atts = _append_atts_for_font(font, [])
    proc = html.escape("".join(char_list))
    out.write(f'<tspan {" ".join(atts)} >{proc}</tspan>\n')


def _append_atts_for_font(font, att_list):
    att_list.append(f'font-family="{font.font_family}"')
    n = font.font_weight
    if n != "normal":
        att_list.append(f'font-weight="{n}"')
    n = font.font_style
    if n != "normal":
        att_list.append(f'font-style="{n}"')
    return att_list


def curve_as_path(out, curve, xfn, yfn, styling):
    styling = styling if styling is not None else _def_style
    plot_as_diag = curve.eff_diagonal is not None
    full_coord_pairs = [f"{xfn(i[0])} {yfn(i[1])}" for i in curve.pts]
    if plot_as_diag:
        # log.debug(f"curve.eff_diagonal = {curve.eff_diagonal}")
        simp_coord_pairs = [f"{xfn(i[0])} {yfn(i[1])}" for i in curve.eff_diagonal]
    else:
        simp_coord_pairs = full_coord_pairs
    full_pt_str = " L".join(full_coord_pairs)
    simp_pt_str = " L".join(simp_coord_pairs)
    atts = []
    eertgif_id = getattr(curve, "eertgif_id", None)
    if eertgif_id is not None:
        atts.append(f'eeertgif_id="{eertgif_id}"')

    # if curve.stroke or plot_as_diag:
    if curve.linewidth:
        atts.append(f'stroke-width="{curve.linewidth}"')
    atts.append(f'stroke="grey"')  # @TODO!
    # else:
    #    atts.append(f'stroke="none"')
    # log.debug(f"curve.fill = {curve.fill} curve.non_stroking_color = {curve.non_stroking_color}")
    filling = curve.non_stroking_color and curve.non_stroking_color != (0, 0, 0)
    if curve.fill and not plot_as_diag:
        atts.append(f'fill="grey"')
        atts.append(
            "onmouseover=\"evt.target.setAttribute('stroke', 'red');evt.target.setAttribute('fill', 'red');\""
        )
        atts.append(
            "onmouseout=\"evt.target.setAttribute('stroke', 'grey');evt.target.setAttribute('fill', 'grey');\""
        )
        if plot_as_diag:
            pref = f'd="M{simp_pt_str} Z" alt_d="M{full_pt_str} Z" '
        else:
            pref = f'd="M{simp_pt_str} Z" '
        s = f' <path {pref} {" ".join(atts)} />\n'
    else:
        atts.append('fill="none"')
        atts.append("onmouseover=\"evt.target.setAttribute('stroke', 'red');\"")
        atts.append("onmouseout=\"evt.target.setAttribute('stroke', 'grey');\"")
        if plot_as_diag:
            pref = f'd="M{simp_pt_str}" alt_d="M{full_pt_str}" '
        else:
            pref = f'd="M{simp_pt_str}" '
        s = f' <path {pref} {" ".join(atts)} />\n'

    out.write(s)
