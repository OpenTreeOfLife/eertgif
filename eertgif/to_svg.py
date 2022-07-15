#!/usr/bin/env python3
from __future__ import annotations

import html
import logging

from io import StringIO
from .util import DisplayMode

log = logging.getLogger("eertgif.to_svg")


# from https://gist.github.com/ollieglass/f6ddd781eeae1d24e391265432297538
kelly_colors = [
    "F2F3F4",
    "222222",
    "F3C300",
    "875692",
    "F38400",
    "A1CAF1",
    "BE0032",
    "C2B280",
    "848482",
    "008856",
    "E68FAC",
    "0067A5",
    "F99379",
    "604E97",
    "F6A600",
    "B3446C",
    "DCD300",
    "882D17",
    "8DB600",
    "654522",
    "E25822",
    "2B3D26",
]
non_white_kelly_colors = kelly_colors[1:]


class SVGStyling:
    color_list = [f"#{i}" for i in non_white_kelly_colors]

    def __init__(self):
        self.comp_idx2color = {}

    def color_for_el(self, el=None):
        def_color = "grey"
        def_highlight_color = "red"
        highlight_color = def_highlight_color
        if el is None:
            return def_color, highlight_color
        color = self.comp_idx2color.get(el.component_idx, def_color)
        return color, highlight_color


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
    if obj_container.display_mode == DisplayMode.CURVES_AND_TEXT:
        styling = styling if styling is not None else _def_style
        for n, o in enumerate(obj_container.nontext_objs):
            if isinstance(o, SafeCurve):
                curve_as_path(out, o, xfn, yfn, styling=styling)
            else:
                log.debug(f"Skipping {o} in SVG export...\n")
    else:
        log.debug(f"# components = {len(obj_container.forest.components)}")

        if styling is None:
            styling = SVGStyling()
        edge_set = set()
        if styling is None:
            styling = SVGStyling()
        by_comp_idx = {}
        for nd in obj_container.iter_nodes():
            by_comp_idx.setdefault(nd.component_idx, []).append(nd)
            for edge in nd.edges:
                if edge not in edge_set:
                    edge_set.add(edge)

        to_sort = []
        for comp_idx, nd_list in by_comp_idx.items():
            min_id = min([nd.eertgif_id for nd in nd_list])
            to_sort.append((len(nd_list), min_id, comp_idx, nd_list))

        styling.comp_idx2color = {}
        to_sort.sort(reverse=True)
        for n, tup in enumerate(to_sort):
            comp_idx, nd_list = tup[-2:]
            col_idx = n if n < len(styling.color_list) else -1
            color = styling.color_list[col_idx]
            styling.comp_idx2color[comp_idx] = color
            for nd in nd_list:
                node_as_circle(out, nd, xfn, yfn, styling=styling)
        for edge in edge_set:
            curve_as_path(out, edge.curve, xfn, yfn, styling=styling, edge=edge)

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


def node_as_circle(out, nd, xfn, yfn, styling):
    styling = styling if styling is not None else _def_style
    color, highlight_color = styling.color_for_el(nd)
    edge_refs = ",".join([str(i.eertgif_id) for i in nd.edges])
    log.debug(f"edge_refs = {edge_refs}")
    atts = [
        f'cx="{xfn(nd.x)}" cy="{yfn(nd.y)}" r="2" ',
        # f'stroke="black"'
        f'stroke="none" fill="{color}" nhcolor="{color}"',
        f'onmouseover="mouseOverNode(evt.target);"',
        f'onmouseout="mouseOutNode(evt.target);"',
    ]
    if edge_refs:
        atts.append(f'edges="{edge_refs}"')

    eertgif_id = getattr(nd, "eertgif_id", None)
    if eertgif_id is not None:
        atts.append(f'id="{eertgif_id}"')
    s = f' <circle {" ".join(atts)} />\n'
    out.write(s)


def curve_as_path(out, curve, xfn, yfn, styling=None, edge=None):
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
    id_owner = curve if edge is None else edge
    eertgif_id = getattr(id_owner, "eertgif_id", None)
    if eertgif_id is not None:
        atts.append(f'id="{eertgif_id}"')

    color, highlight_color = styling.color_for_el(edge)
    # if curve.stroke or plot_as_diag:
    if curve.linewidth:
        atts.append(f'stroke-width="{curve.linewidth}"')
    atts.append(f'stroke="{color}"')  # @TODO!
    # else:
    #    atts.append(f'stroke="none"')
    # log.debug(f"curve.fill = {curve.fill} curve.non_stroking_color = {curve.non_stroking_color}")
    filling = curve.non_stroking_color and curve.non_stroking_color != (0, 0, 0)
    if curve.fill and not plot_as_diag:
        atts.append(f'fill="grey"')
        atts.append(
            f"onmouseover=\"evt.target.setAttribute('stroke', '{highlight_color}');evt.target.setAttribute('fill', '{highlight_color}');\""
        )
        atts.append(
            f"onmouseout=\"evt.target.setAttribute('stroke', '{color}');evt.target.setAttribute('fill', '{color}');\""
        )
        if plot_as_diag:
            pref = f'd="M{simp_pt_str} Z" alt_d="M{full_pt_str} Z" '
        else:
            pref = f'd="M{simp_pt_str} Z" '
        s = f' <path {pref} {" ".join(atts)} />\n'
    else:
        atts.append('fill="none"')
        atts.append(
            f"onmouseover=\"evt.target.setAttribute('stroke', '{highlight_color}');\""
        )
        atts.append(f"onmouseout=\"evt.target.setAttribute('stroke', '{color}');\"")
        if plot_as_diag:
            pref = f'd="M{simp_pt_str}" alt_d="M{full_pt_str}" '
        else:
            pref = f'd="M{simp_pt_str}" '
        s = f' <path {pref} {" ".join(atts)} />\n'

    out.write(s)
