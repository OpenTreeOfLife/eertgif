#!/usr/bin/env python3
from __future__ import annotations

import html
import logging

from io import StringIO
from .util import DisplayMode

log = logging.getLogger("eertgif.to_svg")


DEF_COLOR = "grey"
DEF_LOW_PRIORITY_COLOR = "grey"
DEF_TREE_COMP_COLOR = "black"
DEF_TRASHED_COLOR = "cyan"
DEF_HIGHLIGHT_COLOR = "red"
DEF_LEGEND_COLOR = "blue"  # also in extract.pt

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

    def color_for_el(self, el=None, is_trashed=False):
        def_color = DEF_COLOR
        def_trashed = DEF_TRASHED_COLOR
        def_highlight_color = DEF_HIGHLIGHT_COLOR
        highlight_color = def_highlight_color
        if is_trashed:
            return def_trashed, highlight_color
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
    yfn = lambda y: cbb[3] - y  # pdf y=0 is bottom, but in svg it is is top

    min_dim = min(height, width)
    out.write(
        f"""<svg viewBox="0 0 {width} {height}" > 
"""
    )
    curve_mode = obj_container.display_mode == DisplayMode.CURVES_AND_TEXT
    phylo_mode = obj_container.display_mode == DisplayMode.PHYLO
    component_mode = obj_container.display_mode == DisplayMode.COMPONENTS
    # log.debug(f"obj_container.nontext_objs = {obj_container.nontext_objs}")
    if curve_mode:
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
        styling.min_fig_dim = min_dim
        styling.circle_size = max(min_dim / 500, 2)
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
        to_sort.sort(reverse=True)

        styling.comp_idx2color = {}
        if phylo_mode and obj_container.best_tree is not None:
            tree = obj_container.best_tree
            for n, tup in enumerate(to_sort):
                comp_idx = tup[-2]
                styling.comp_idx2color[comp_idx] = DEF_LOW_PRIORITY_COLOR
            styling.comp_idx2color[tree.component_idx] = DEF_TREE_COMP_COLOR
            if obj_container.best_legend and obj_container.best_legend.bar:
                leg_idx = obj_container.best_legend.bar.component_idx
                styling.comp_idx2color[leg_idx] = DEF_LEGEND_COLOR
        else:
            for n, tup in enumerate(to_sort):
                comp_idx = tup[-2]
                col_idx = n if n < len(styling.color_list) else -1
                color = styling.color_list[col_idx]
                styling.comp_idx2color[comp_idx] = color
        comp_path_events = {
            "onclick": '"handleClickOnGraph(evt);"',
            "onmouseover": '"mouseOverEdge(evt.target);"',
            "onmouseout": '"mouseOutEdge(evt.target);"',
        }
        phylo_path_events = {
            "onclick": '"handleClickOnGraph(evt);"',
            "onmouseover": '"mouseOverPairedEdge(evt.target);"',
            "onmouseout": '"mouseOutPairedEdge(evt.target);"',
        }
        comp_circ_events = {
            "onmouseover": '"mouseOverNode(evt.target);"',
            "onmouseout": '"mouseOutNode(evt.target);"',
        }
        phylo_circ_events = {
            "onmouseover": '"mouseOverPairedEdge(evt.target);"',
            "onmouseout": '"mouseOutPairedEdge(evt.target);"',
        }
        if phylo_mode:
            path_events, circ_events = phylo_path_events, phylo_circ_events
        else:
            path_events, circ_events = comp_path_events, comp_circ_events

        for edge in edge_set:
            curve_as_path(
                out,
                edge.curve,
                xfn,
                yfn,
                styling=styling,
                edge=edge,
                events=path_events,
            )

        for n, tup in enumerate(to_sort):
            nd_list = tup[-1]
            for nd in nd_list:
                node_as_circle(out, nd, xfn, yfn, styling=styling, events=circ_events)

        for curve in obj_container.trashed_nontext_objs:
            if isinstance(curve, SafeCurve):
                curve_as_path(
                    out,
                    curve,
                    xfn,
                    yfn,
                    styling=styling,
                    is_trashed=True,
                    events=path_events,
                )
            else:
                log.debug(f"Skipping {curve} in SVG export...\n")

    # log.debug(f"obj_container.text_lines = {obj_container.nontext_objs}")
    events = {"ondragover": ";"}
    phylo_text_events = {
        "ondragover": ";",
        "onmouseover": '"mouseOverPairedEdge(evt.target);"',
        "onmouseout": '"mouseOutPairedEdge(evt.target);"',
    }
    if phylo_mode:
        tree = obj_container.best_tree
        tr_unused = set() if tree is None else set(tree.unused_text)
        legend = obj_container.best_legend
        leg_unused = set() if legend is None else set(legend.unused_text)
        unused = tr_unused.intersection(leg_unused)
        u_atts = ['fill="grey"']
        tr_atts = ['fill="black"']
        leg_atts = ['fill="blue"']
        events = phylo_path_events
        for n, text in enumerate(obj_container.text_lines):
            if text in unused:
                ini_atts = u_atts
            elif text in tr_unused:
                ini_atts = leg_atts
            else:
                ini_atts = tr_atts
            text_as_text_el(out, text, xfn, yfn, styling, ini_atts, events=events)
        for n, text in enumerate(obj_container.trashed_text):
            text_as_text_el(
                out, text, xfn, yfn, styling, u_atts, is_trashed=True, events=events
            )
    else:
        for n, text in enumerate(obj_container.text_lines):
            text_as_text_el(out, text, xfn, yfn, styling, events=events)
        if not curve_mode:
            for n, text in enumerate(obj_container.trashed_text):
                text_as_text_el(
                    out, text, xfn, yfn, styling, is_trashed=True, events=events
                )
    out.write("</svg>")


def text_as_text_el(
    out, text, xfn, yfn, styling, ini_atts=None, is_trashed=False, events=None
):
    midheight = (yfn(text.y1) + yfn(text.y0)) / 2
    atts = [f'x="{xfn(text.x0)}"', f'y="{midheight}"']
    if ini_atts:
        atts.extend(ini_atts)
    eertgif_id = getattr(text, "eertgif_id", None)
    if eertgif_id is not None:
        atts.append(f'id="{eertgif_id}"')
    length = abs(xfn(text.x1) - xfn(text.x0))
    atts.append(f'textLength="{length}"')
    atts.append(f'textAdjust="spacingAndGlyphs"')
    atts.append(f'font-size="{int(text.height)}px"')
    atts.append(f'nhscolor="none"')
    if is_trashed:
        atts.append('trashed="yes"')
    if events:
        atts.extend([f"{k}={v}" for k, v in events.items()])
    # Deal with all-one-font text
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


def node_as_circle(out, nd, xfn, yfn, styling, events=None):
    styling = styling if styling is not None else _def_style
    color, highlight_color = styling.color_for_el(nd)
    edge_refs = ",".join([str(i.eertgif_id) for i in nd.edges])
    # log.debug(f"edge_refs = {edge_refs}")
    atts = [
        f'cx="{xfn(nd.x)}" cy="{yfn(nd.y)}" ',
        f'r="{styling.circle_size}" ',
        # f'stroke="black"'
        f'stroke="none" fill="{color}" nhscolor="none" nhfcolor="{color}"',
        f'component="{nd.component_idx}"',
    ]
    if edge_refs:
        atts.append(f'edges="{edge_refs}"')

    eertgif_id = getattr(nd, "eertgif_id", None)
    if eertgif_id is not None:
        atts.append(f'id="{eertgif_id}"')
    if events:
        atts.extend([f"{k}={v}" for k, v in events.items()])
    s = f' <circle {" ".join(atts)} />\n'
    out.write(s)


def curve_as_path(
    out, curve, xfn, yfn, styling=None, edge=None, is_trashed=False, events=None
):
    styling = styling if styling is not None else _def_style
    plot_as_diag = curve.eff_diagonal is not None
    full_coord_pairs = [f"{xfn(i[0])} {yfn(i[1])}" for i in curve.pts]
    if plot_as_diag:
        # log.debug(f"curve.eff_diagonal = {curve.eff_diagonal}")
        simp_coord_pairs = [f"{xfn(i[0])} {yfn(i[1])}" for i in curve.eff_diagonal]
    else:
        simp_coord_pairs = full_coord_pairs
    simp_pt_str = " L".join(simp_coord_pairs)
    if plot_as_diag:
        full_pt_str = " L".join(full_coord_pairs)
    else:
        full_pt_str = simp_pt_str

    atts = []
    id_owner = curve if edge is None else edge
    eertgif_id = getattr(id_owner, "eertgif_id", None)
    if eertgif_id is not None:
        atts.append(f'id="{eertgif_id}"')
    if edge:
        node_refs = ",".join(
            [str(i.eertgif_id) for i in (edge.nd1, edge.nd2) if i is not None]
        )
        if node_refs:
            atts.append(f'nodes="{node_refs}"')
        atts.append(f'component="{edge.component_idx}"')
        atts.append(f'curve_id="{curve.eertgif_id}"')

    color, highlight_color = styling.color_for_el(edge, is_trashed=is_trashed)
    if is_trashed:
        atts.append('trashed="yes"')
    # if curve.stroke or plot_as_diag:
    if curve.linewidth:
        atts.append(f'stroke-width="{curve.linewidth}"')
    atts.append(f'stroke="{color}"')  # @TODO!
    if events:
        atts.extend([f"{k}={v}" for k, v in events.items()])
    # else:
    #    atts.append(f'stroke="none"')
    # log.debug(f"curve.fill = {curve.fill} curve.non_stroking_color = {curve.non_stroking_color}")
    filling = curve.non_stroking_color and curve.non_stroking_color != (0, 0, 0)
    atts.extend([f'stroke="{color}"', f'nhscolor="{color}"'])
    if curve.fill and not plot_as_diag:
        atts.extend(['fill="{color}"', 'nhfcolor="{color}"'])
        pref = (
            f'd="M{simp_pt_str} Z" simp_d="M{simp_pt_str} Z" full_d="M{full_pt_str} Z" '
        )
        s = f' <path {pref} {" ".join(atts)} />\n'
    else:
        atts.extend(['fill="none"', 'nhfcolor="none"'])
        pref = f'd="M{simp_pt_str}" simp_d="M{simp_pt_str}" full_d="M{full_pt_str}" '
        s = f' <path {pref} {" ".join(atts)} />\n'

    out.write(s)
