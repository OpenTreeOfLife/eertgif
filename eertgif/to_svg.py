#!/usr/bin/env python3
from __future__ import annotations

import html
import logging

from pdfminer.layout import LTCurve

log = logging.getLogger("eertgif.to_svg")


def to_html(out, unproc_region=None):
    out.write(
        f"""<!DOCTYPE html>
<html>
<body>
<div>
"""
    )
    to_svg(out, unproc_region=unproc_region)
    out.write(
        """</div>
</body>
</html>
"""
    )


def to_svg(out, unproc_region=None):
    assert unproc_region is not None
    cbb = unproc_region.container_bbox
    height = cbb[3] - cbb[1]
    width = cbb[2] - cbb[0]
    xfn = lambda x: x - cbb[0]
    yfn = lambda y: cbb[3] - y  # pdf y=0 is bottom, but svg is top

    out.write(
        f"""<svg viewBox="0 0 {width} {height}" > 
"""
    )
    # log.debug(f"unproc_region.nontext_objs = {unproc_region.nontext_objs}")
    for n, o in enumerate(unproc_region.nontext_objs):
        if isinstance(o, LTCurve):
            curve_as_path(out, o, xfn, yfn)
        else:
            log.debug(f"Skipping {o} in SVG export...\n")
    # log.debug(f"unproc_region.text_lines = {unproc_region.nontext_objs}")
    for n, text in enumerate(unproc_region.text_lines):
        text_as_text_el(out, text, xfn, yfn)
    out.write("</svg>")


def text_as_text_el(out, text, xfn, yfn):
    midheight = (yfn(text.y1) + yfn(text.y0)) / 2
    atts = [f'x="{xfn(text.x0)}"', f'y="{midheight}"']
    length = abs(xfn(text.x1) - xfn(text.x0))
    atts.append(f'textLength="{length}"')
    atts.append(f'textAdjust="spacingAndGlyphs"')
    atts.append(f'font-size="{int(text.height)}px"')
    proc = html.escape(text.get_text().strip())
    s = f' <text {" ".join(atts)} >{proc}</text>\n'
    out.write(s)


def curve_as_path(out, curve, xfn, yfn):
    coord_pairs = [f"{xfn(i[0])} {yfn(i[1])}" for i in curve.pts]
    pt_str = " L".join(coord_pairs)
    atts = []

    if curve.stroke:
        atts.append(f'stroke-width="{curve.linewidth}"')
        atts.append(f'stroke="black"')  # @TODO!
    else:
        atts.append(f'stroke="none"')
    filling = curve.non_stroking_color and curve.non_stroking_color != (0, 0, 0)
    if filling:
        atts.append(f'fill="black"')
        atts.append(
            "onmouseover=\"evt.target.setAttribute('stroke', 'red');evt.target.setAttribute('fill', 'red');\""
        )
        atts.append(
            "onmouseout=\"evt.target.setAttribute('stroke', 'black');evt.target.setAttribute('fill', 'black');\""
        )
        s = f' <path d="M{pt_str} Z" {" ".join(atts)} />\n'
    else:
        atts.append('fill="none"')
        atts.append("onmouseover=\"evt.target.setAttribute('stroke', 'red');\"")
        atts.append("onmouseout=\"evt.target.setAttribute('stroke', 'black');\"")
        s = f' <path d="M{pt_str}" {" ".join(atts)} />\n'

    out.write(s)
