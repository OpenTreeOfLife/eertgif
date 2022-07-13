#!/usr/bin/env python3
from __future__ import annotations

import logging
import re
import sys
from enum import IntEnum, Enum
from io import StringIO
from math import sqrt
from typing import List, Any, Dict, Set, Tuple, Union

from pdfminer.high_level import extract_pages, LAParams
from pdfminer.layout import (
    LTChar,
    LTFigure,
    LTCurve,
    LTTextLine,
    LTTextLineHorizontal,
    LTTextLineVertical,
    LTTextBox,
    LTImage,
)
from pdfminer.utils import Point, Rect
from .point_map import PointMap
from .to_svg import to_html

log = logging.getLogger("eertgif.extract")
# Includes some code from pdfminer layout.py

VERBOSE = True
COORD_TOL = 1.0e-3
DIM_TOL = COORD_TOL
MIN_BR_TOL = 1.0e-4
DEFAULT_LABEL_GAP = 10


def set_verbose(v):
    global VERBOSE
    VERBOSE = v


def debug(msg: str, msg_list: List[Any] = None) -> None:
    if msg_list is not None:
        msg_list.append(msg)
    if VERBOSE:
        sys.stderr.write(f"{msg}\n")


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


class AxisDir(IntEnum):
    UNKNOWN = 0
    HORIZONTAL = 1
    VERTICAL = 2


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


CARDINAL = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


class Node(object):
    def __init__(self, x: float = None, y: float = None, loc: Point = None):
        # debug(f"created node at {(x, y)}")
        if loc is None:
            assert x is not None
            assert y is not None
            self.loc = (x, y)
        else:
            self.loc = loc
        self.edges = set()

    def add_edge(self, edge: Edge) -> None:
        self.edges.add(edge)

    def __str__(self) -> str:
        return f"Node({self.loc})"

    __repr__ = __str__

    def add_connected(self, nd_set: set, taboo: set = None) -> None:
        seen = taboo if taboo is not None else set()
        seen.add(self)
        nd_set.add(self)
        for edge in self.edges:
            for n in [edge.nd1, edge.nd2]:
                if (n is not self) and (n not in seen):
                    n.add_connected(nd_set, taboo=seen)

    def adjacent(self) -> list:
        return [i.other_node(self) for i in self.edges]

    @property
    def x(self) -> float:
        return self.loc[0]

    @property
    def y(self) -> float:
        return self.loc[1]

    @property
    def dir_from_adj(self) -> Direction:
        assert len(self.edges) == 1
        e = next(iter(self.edges))
        other = e.other_node(self)
        if other.x == self.x:
            if other.y == self.y:
                return Direction.SAME
            if other.y < self.x:
                return Direction.NORTH
            return Direction.SOUTH
        if other.x < self.x:
            if other.y == self.y:
                return Direction.EAST
            if other.y < self.x:
                return Direction.NORTHEAST
            return Direction.SOUTHEAST
        if other.y == self.y:
            return Direction.WEST
        if other.y < self.x:
            return Direction.NORTHWEST
        return Direction.SOUTHWEST


class Edge(object):
    def __init__(self, curve: SafeCurve, nd1: Node, nd2: Node):
        self.curve, self.nd1, self.nd2 = curve, nd1, nd2
        nd1.add_edge(self)
        nd2.add_edge(self)

    def __str__(self) -> str:
        return f"Edge({self.nd1} <==> {self.nd2})"

    __repr__ = __str__

    def other_node(self, nd: Node) -> Node:
        if nd is self.nd1:
            return self.nd2
        assert nd is self.nd2
        return self.nd1

    @property
    def midpoint(self):
        return (self.nd1.x + self.nd2.x) / 2.0, (self.nd1.y + self.nd2.y) / 2.0

    @property
    def length(self):
        return calc_dist(self.nd1.loc, self.nd2.loc)


def midpoint(rect: Rect):
    x0, y0, x1, y1 = rect
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def calc_dist(pt1: Point, pt2: Point) -> float:
    xsq = (pt1[0] - pt2[0]) ** 2
    ysq = (pt1[1] - pt2[1]) ** 2
    return sqrt(xsq + ysq)


class PlanarContainer(object):
    def __init__(self):
        self.by_x = PointMap()
        self._all_nodes = []

    def iter_nodes(self):
        return iter(self._all_nodes)

    def find_closest(self, point: Point, tol: float) -> Union[None, Node]:
        ptx, pty = point
        rows = self._find_closest_rows(ptx, tol)
        if not rows:
            return None
        min_diff = tol
        min_el = None
        for row_x, row_map in rows:
            for cell_y, el in row_map.items():
                dist = calc_dist((ptx, pty), (row_x, cell_y.x))
                if dist < min_diff:
                    min_diff = dist
                    min_el = el
        return min_el

    def find_exact(self, point: Point) -> Union[None, Node]:
        ptx, pty = point
        row_map = self.find_row_exact(ptx)
        if row_map is None:
            return None
        return row_map.get(pty)
        # for el in row:
        #     if el.y == pty:
        #         return el
        #     if el.y > pty:
        #         break
        # return None

    def find_row_exact(self, x: float) -> Union[None, List[Node]]:
        return self.by_x.get(x)

    def _find_closest_rows(self, x: float, tol: float) -> List[List[Node]]:
        by_dist = []
        for n, row_tup in enumerate(self.by_x.items()):
            row_x, row_map = row_tup
            dist = abs(row_x.x - x)
            if dist < tol:
                by_dist.append((dist, n, (row_x.x, row_map)))
        by_dist.sort()
        return [i[-1] for i in by_dist]

    def new_at(self, pt: Point) -> Node:
        ptx = pt[0]
        pty = pt[1]
        row_map = self.by_x.setdefault(ptx, PointMap())
        # dest_row = None
        # bef_ind = None
        # for n, row in enumerate(self.by_x):
        #     if row[0].x == ptx:
        #         dest_row = row
        #         break
        #     if row[0].x > ptx:
        #         bef_ind = n
        #         break
        nd = Node(ptx, pty)
        self._all_nodes.append(nd)
        row_map.setdefault(pty, nd)
        # if dest_row:
        #     bef_y_ind = None
        #     for n, el in enumerate(dest_row):
        #         if el.y >= pty:
        #             bef_y_ind = n
        #             break
        #     if bef_y_ind is not None:
        #         dest_row.insert(bef_y_ind, nd)
        #     else:
        #         dest_row.append(nd)
        # elif bef_ind is not None:
        #     self.by_x.insert(bef_ind, [nd])
        # else:
        #     self.by_x.append([nd])
        return nd


class GraphFromEdges(object):
    def __init__(self):
        self.nodes = PlanarContainer()
        self.edges = set()
        self.tol = 0.01

    def add_curve(self, curve: SafeCurve) -> Edge:
        pt1, pt2 = curve.pts[0], curve.pts[-1]
        nd1 = self.find_or_insert_node(pt1)[0]
        nd2 = self.find_or_insert_node(pt2)[0]
        edge = Edge(curve, nd1, nd2)
        self.edges.add(edge)
        return edge

    def find_or_insert_node(
        self, point: Point, tol: float = None
    ) -> Tuple[Node, bool, bool]:
        """Returns (node, was_inserted, is_exact)"""
        t = tol if tol is not None else self.tol
        nd = self.nodes.find_exact(point)
        if nd is not None:
            return nd, False, True
        nd = self.nodes.find_closest(point, t)
        if nd is not None:
            return nd, False, False
        nd = self.nodes.new_at(point)
        return nd, True, True

    def build_forest(self) -> Forest:
        forest = Forest(self)
        included = set()
        for nd in self.nodes.iter_nodes():
            if nd in included:
                continue
            nd_set = set()
            forest.components.append(nd_set)
            nd.add_connected(nd_set)
            assert not included.intersection(nd_set)
            included.update(nd_set)
        return forest


class PhyloLegend(object):
    def __init__(
        self,
        connected_nodes: Set[Node] = None,
        forest: Forest = None,
        text_lines: List[SafeTextLine] = None,
    ):
        self.forest = forest
        self.score = None
        edges = set()
        for nd in connected_nodes:
            for edge in nd.edges:
                edges.add(edge)
        edge_list = [(i.midpoint, i) for i in edges]
        could_be_num = [i for i in text_lines if as_numeric(i.get_text())[0]]
        line_list = [(midpoint(i.bbox), i) for i in could_be_num]
        min_d, min_el = float("inf"), None
        for line_tup in line_list:
            dist, edge_tup = find_closest_first(line_tup, edge_list)
            if dist < min_d:
                min_d = dist
                min_el = (line_tup[1], edge_tup[1])
        if min_el is None:
            raise RuntimeError("Could not find a figure legend in nodes and text")
        self.legend_pair = min_el
        self.bar = min_el[1]
        self.legend_text = min_el[0]
        self.edge_len_scaler = as_numeric(min_el[0].get_text())[1] / self.bar.length
        self.unused_text = set([i for i in text_lines if i is not self.legend_text])
        self.unused_nodes = [i for i in connected_nodes if i is not self.bar]
        self.score = abs(DEFAULT_LABEL_GAP - min_d)


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


class Forest(object):
    def __init__(self, graph: GraphFromEdges):
        self.components = []
        self.graph = graph
        self.trees = []
        self.legends = []

    def interpret_as_legend(
        self, idx: int, text_lines: List[SafeTextLine]
    ) -> PhyloLegend:
        comp = self.components[idx]
        while len(self.legends) <= idx:
            self.legends.append(None)
        t = self.legends[idx]
        if t is not None:
            return t
        try:
            t = PhyloLegend(connected_nodes=comp, forest=self, text_lines=text_lines)
            self.legends[idx] = t
        except RuntimeError:
            pass
        return t

    def interpret_as_tree(self, idx: int, text_lines: List[SafeTextLine]) -> PhyloTree:
        comp = self.components[idx]
        while len(self.trees) <= idx:
            self.trees.append(None)
        t = self.trees[idx]
        if t is not None:
            return t
        t = PhyloTree(connected_nodes=comp, forest=self, text_lines=text_lines)
        self.trees[idx] = t
        return t


class PhyloTree(object):
    def __init__(
        self,
        connected_nodes: Set[Node] = None,
        forest: Forest = None,
        text_lines: List[SafeTextLine] = None,
    ):
        self.forest = forest
        self.used_text = set()
        self.root = None
        self.pma = None

        int_nds, ext_nds = [], []
        lx, ly, hx, hy = float("inf"), float("inf"), float("-inf"), float("-inf")
        for nd in connected_nodes:
            cont = ext_nds if len(nd.edges) == 1 else int_nds
            cont.append(nd)
            lx = min(lx, nd.x)
            ly = min(ly, nd.y)
            hx = max(hx, nd.x)
            hy = max(hy, nd.y)
        # nodes_bbox = (lx, ly, hx, hy)
        lx, ly, hx, hy = float("inf"), float("inf"), float("-inf"), float("-inf")
        th, tw = [], []
        horiz_text, vert_text = [], []
        for ltline in text_lines:
            th.append(ltline.height)
            tw.append(ltline.width)
            lbb = ltline.bbox
            lx = min(lx, lbb[0])
            ly = min(ly, lbb[1])
            hx = max(hx, lbb[2])
            hy = max(hy, lbb[3])
            if ltline.direction == AxisDir.HORIZONTAL:
                horiz_text.append(ltline)
            else:
                assert ltline.direction == AxisDir.VERTICAL
                vert_text.append(ltline)
        # text_bbox = (lx, ly, hx, hy)
        # print(
        #     f"nodes_bbox = {nodes_bbox} text_bbox={text_bbox} {len(horiz_text)}, {len(vert_text)}"
        # )
        by_dir = [
            self._try_as_tips_to(i, int_nds, ext_nds, horiz_text, vert_text)
            for i in CARDINAL
        ]
        min_score, best_attempt = float("inf"), None
        for attempt in by_dir:
            s = attempt.score
            if s < min_score:
                min_score = s
                best_attempt = attempt
            # print(f"Attempt score = {attempt.score} from {attempt.penalties}")
        self.pma = best_attempt
        self.root = best_attempt.root

        # north, east, south, west = [], [], [], []
        # for ext in externals:
        #     d = ext.dir_from_adj
        #     # print(ext, "is", d, "from adjacent node, ", ext.adjacent()[0])
        #     if d & Direction.NORTH:
        #         north.append(d)
        #     if d & Direction.EAST:
        #         east.append(d)
        #     if d & Direction.SOUTH:
        #         south.append(d)
        #     if d & Direction.WEST:
        #         west.append(d)
        # print(len(north), "nodes to the north of their neighbor")
        # print(len(east), "nodes to the east of their neighbor")
        # print(len(south), "nodes to the south of their neighbor")
        # print(len(west), "nodes to the west of their neighbor")
        # blob_list = [(i[0], n, i) for n, i in enumerate([eblob, nblob, sblob, wblob])]
        # blob_list.sort()
        # best_blob = blob_list[0]
        # self.tension_score = best_blob[0]
        # self.root = best_blob[1]
        # self.used_text.update(best_blob[2])
        # self.num_tips = best_blob[3]

    def clean_for_export(self):
        dup_labels = {}
        for nd in self.root.post_order():
            lab = nd.label
            if not lab:
                continue
            dup_labels.setdefault(lab, []).append(nd)
        for label, vals in dup_labels.items():
            if len(vals) > 1:
                num = 1
                for nd in vals:
                    nl = f"{label}-duplicate#{num}"
                    num += 1
                    if nl not in dup_labels:
                        nd._label = nl
                    debug(
                        f'duplicate label. Renaming "{label}" to "{nl}"',
                        self.pma.messages,
                    )

    @property
    def score(self):
        return self.pma.score

    @property
    def attempt(self):
        return self.pma

    def _try_as_tips_to(
        self,
        tip_dir: Direction,
        internals: List[Node],
        externals: List[Node],
        horiz_text: List[SafeTextLine],
        vert_text: List[SafeTextLine],
    ) -> PhyloMapAttempt:
        if tip_dir in (Direction.EAST, Direction.WEST):
            inline_t = horiz_text
            perpindic_t = vert_text
            if tip_dir == Direction.EAST:
                calc_x = lambda el: el.x0
            else:
                calc_x = lambda el: el.x1
            calc_y = lambda el: (el.y0 + el.y1) / 2.0
        else:
            inline_t = vert_text
            perpindic_t = horiz_text
            if tip_dir == Direction.SOUTH:
                calc_y = lambda el: el.y1
            else:
                calc_y = lambda el: el.y0
            calc_x = lambda el: (el.x0 + el.x1) / 2.0
        # debug(f"Trying DIR={repr(tip_dir)} ... len(externals) = {len(externals)}, len(inline_t)={len(inline_t)}")
        by_lab, by_ext = {}, {}
        for label_t in inline_t:
            loc = (calc_x(label_t), calc_y(label_t))
            dist, ext = find_closest(loc, externals)
            by_lab[label_t] = (ext, dist)
            prev = by_ext.get(ext)
            if prev is None or dist < prev[-1]:
                by_ext[ext] = (label_t, dist)
        matched_labels, orphan_labels = [], []
        matched_leaves = set()
        matched_dists = []
        for label_t in inline_t:
            ext, dist = by_lab[label_t]
            if by_ext.get(ext, [None, None])[0] is label_t:
                matched_labels.append(label_t)
                matched_dists.append(dist)
                matched_leaves.add(ext)
            else:
                orphan_labels.append(label_t)
        unmatched_ext = set()
        for nd in externals:
            if nd not in matched_leaves:
                unmatched_ext.add(nd)
        pma = PhyloMapAttempt()
        expected_def_gap = DEFAULT_LABEL_GAP
        if matched_labels:
            expected_def_gap = avg_char_width(matched_labels)
            mean_obs_gap, var_gap = mean_var(matched_dists)
            pma.add_penalty(Penalty.LABEL_GAP_MEAN, mean_obs_gap)
            if var_gap:
                pma.add_penalty(Penalty.LABEL_GAP_STD_DEV, sqrt(var_gap))
        pma.build_tree_from_tips(
            tip_dir=tip_dir,
            internals=internals,
            matched_lvs=matched_leaves,
            unmatched_lvs=unmatched_ext,
            tip_labels=matched_labels,
            label2leaf=by_lab,
        )
        pma.unmatched_ext_nodes = unmatched_ext
        pma.unused_perpindicular_text = perpindic_t
        pma.unused_inline_text = orphan_labels
        return pma


class Penalty(Enum):
    LABEL_GAP_MEAN = 0
    LABEL_GAP_STD_DEV = 1
    UNMATCHED_LABELS = 2
    WRONG_DIR_TO_PAR = 3


class PhyloTreeData(object):
    """Blob of data common to all nodes/edges"""

    def __init__(self, tip_dir: Direction = None, attempt: PhyloMapAttempt = None):
        self._tip_dir = None
        self.pos_min_fn = None
        self.child_pos_fn = None
        self.attempt = attempt
        self.tip_dir = tip_dir

    @property
    def tip_dir(self):
        return self._tip_dir

    @tip_dir.setter
    def tip_dir(self, tip_dir):
        self._tip_dir = tip_dir
        dir2min_coord = {
            Direction.NORTH: lambda n: n.y,
            Direction.SOUTH: lambda n: -n.y,
            Direction.EAST: lambda n: n.x,
            Direction.WEST: lambda n: -n.x,
        }
        self.pos_min_fn = dir2min_coord[tip_dir]
        dir_for_last_child = rotate_cw(tip_dir)
        self.child_pos_fn = dir2min_coord[dir_for_last_child]


class PhyloNode(object):
    def __init__(
        self,
        vnode: Node = None,
        label_obj: SafeTextLine = None,
        phy_ctx: PhyloTreeData = None,
    ):
        if vnode:
            assert isinstance(vnode, Node)
        self.vnode = vnode
        self.label_obj = label_obj
        self._unsorted_children = []
        self._adjacent_by_vedge = {}
        self._adjacent_by_phynode = {}
        self.par = None
        self.orig_vedge_to_par = None
        self.children = None
        self.is_root = False
        self.phy_ctx = phy_ctx
        self._collapsed = []
        self.merged = None
        self._label = None

    @property
    def label(self):
        if self._label:
            return self._label
        if self.label_obj is not None:
            return self.label_obj.get_text()
        return None

    @property
    def x(self):
        return self.vnode.x

    @property
    def y(self):
        return self.vnode.y

    @property
    def is_tip(self):
        return not bool(self._unsorted_children)

    def sort_children(self):
        csfn = self.phy_ctx.child_pos_fn
        if csfn is None:
            self.children = list(self._unsorted_children)
            return
        wip = [(csfn(i), n, i) for n, i in enumerate(self._unsorted_children)]
        wip.sort()
        self.children = [i[-1] for i in wip]

    def add_child(self, nd: PhyloNode) -> PhyloNode:
        assert nd.par is None
        nd.par = self
        self._unsorted_children.append(nd)
        return nd

    def add_adjacent(self, nd: PhyloNode, edge: Edge) -> PhyloNode:
        self._adjacent_by_vedge[edge] = nd
        self._adjacent_by_phynode[nd] = edge
        nd._adjacent_by_vedge[edge] = self
        nd._adjacent_by_phynode[self] = edge
        return nd

    def _collapse_into_par(self):
        par = self.par
        assert par is not None
        par._collapsed.extend(self._collapsed)
        par._collapsed.append(self)
        self._collapsed = []
        self.merged = par
        par._unsorted_children.extend(self._unsorted_children)
        idx = par._unsorted_children.index(self)
        par._unsorted_children.pop(idx)
        assert self not in par._unsorted_children
        for c in self._unsorted_children:
            c.par = par
        par.sort_children()

    def post_order(self) -> List[PhyloNode]:
        nd_list = []
        for c in self._unsorted_children:
            nd_list.extend(c.post_order())
        nd_list.append(self)
        return nd_list

    def collapse_short_internals(self, min_br):
        post_nds = self.post_order()
        for nd in post_nds:
            if nd.is_tip:
                continue
            elen = nd.edge_len()
            if (elen is not None) and (elen < min_br):
                assert nd.par is not None
                nd._collapse_into_par()

    def root_based_on_par(self, par: PhyloNode = None) -> None:
        pma = self.phy_ctx.attempt
        coord_fn = self.phy_ctx.pos_min_fn

        self.par = par
        if par is not None:
            self.orig_vedge_to_par = self._adjacent_by_phynode[par]
            sc = coord_fn(self)
            pc = coord_fn(par)
            if sc < pc and abs(pc - sc) > COORD_TOL:
                pma.add_penalty(Penalty.WRONG_DIR_TO_PAR, 1)
        for adj in self._adjacent_by_vedge.values():
            if adj is par:
                continue
            self._unsorted_children.append(adj)
            adj.root_based_on_par(self)
        self.sort_children()

    def get_newick(self, edge_len_scaler=None) -> str:
        ostr = StringIO()
        self.write_newick(ostr, edge_len_scaler=edge_len_scaler)
        ostr.write(";")
        return ostr.getvalue()

    def write_newick(self, out, edge_len_scaler=None):
        """Writes newick to `out` without the trailing ;"""
        assert self.merged is None
        if self.children:
            out.write("(")
            for n, child in enumerate(self.children):
                if n != 0:
                    out.write(",")
                child.write_newick(out, edge_len_scaler=edge_len_scaler)
            out.write(")")
        if self.label_obj:
            out.write(escape_newick(self.label))
        if self.par:
            elen = self.edge_len(scaler=edge_len_scaler)
            out.write(f":{elen}")

    def edge_len(self, scaler=None):
        p = self.par
        if p is None:
            return None
        td = self.phy_ctx.tip_dir
        if td in [Direction.EAST, Direction.WEST]:
            d = abs(self.x - p.x)  # x-offset only
        elif td in [Direction.NORTH, Direction.SOUTH]:
            d = abs(self.y - p.y)  # y-offset only
        else:
            d = calc_dist(
                (p.x, p.y), (self.x, self.y)
            )  # diagonal - this is an odd choice @TODO
        if scaler:
            return scaler * d
        return d


def escape_newick(s):
    e = "''".join(s.split("'"))
    return f"'{e}'"


class PhyloEdge(object):
    pass


class PhyloMapAttempt(object):
    def __init__(self):
        self.penalties = {}
        self.penalty_weights = {}
        self.root = None
        self.unmatched_ext_nodes = []
        self.unused_perpindicular_text = []
        self.unused_inline_text = []
        self.messages = []

    @property
    def unused_text(self):
        u = list(self.unused_perpindicular_text)
        u.extend(self.unused_inline_text)
        return u

    def add_penalty(self, ptype: Penalty, val: float) -> None:
        existing = self.penalties.get(ptype, 0.0)
        self.penalties[ptype] = existing + val

    @property
    def score(self):
        s = 0.0
        for k, v in self.penalties.items():
            w = self.penalty_weights.get(k, 1.0)
            s += w * v
        return s

    def build_tree_from_tips(
        self,
        tip_dir: Direction,
        internals: List[Node],
        matched_lvs: Set[Node],
        unmatched_lvs: Set[Node],
        tip_labels: List[SafeTextLine],
        label2leaf: Dict[SafeTextLine, Tuple[Node, float]],
    ) -> PhyloNode:
        node2phyn = self._build_adj(
            tip_dir=tip_dir,
            internals=internals,
            unmatched_lvs=unmatched_lvs,
            tip_labels=tip_labels,
            label2leaf=label2leaf,
        )
        root = self._root_by_position(tip_dir=tip_dir, node2phyn=node2phyn)
        for leaf in unmatched_lvs:
            phynd = node2phyn[leaf]
            if phynd is not root:
                self.add_penalty(Penalty.UNMATCHED_LABELS, 1)
        root.collapse_short_internals(MIN_BR_TOL)
        return root

    def _root_by_position(
        self, tip_dir: Direction, node2phyn: Dict[Node, PhyloNode]
    ) -> PhyloNode:
        # set up functions for returning a float to minimize during sort
        #   based on direction of the reading, and coordinates
        rootmost, rootmost_coord = None, float("inf")
        for nd, phynd in node2phyn.items():
            coord_fn = phynd.phy_ctx.pos_min_fn
            coord = coord_fn(nd)
            if coord < rootmost_coord:
                rootmost_coord = coord
                rootmost = phynd
        assert rootmost is not None
        rootmost.root_based_on_par(None)
        self.root = rootmost
        return rootmost

    def _build_adj(
        self,
        tip_dir: Direction,
        internals: List[Node],
        unmatched_lvs: Set[Node],
        tip_labels: List[SafeTextLine],
        label2leaf: Dict[SafeTextLine, Tuple[Node, float]],
    ) -> Dict[Node, PhyloNode]:
        node2phyn = {}
        leaves = set()
        phy_ctx = PhyloTreeData(tip_dir=tip_dir, attempt=self)
        for tl in tip_labels:
            ml = label2leaf[tl][0]
            phynd = PhyloNode(vnode=ml, label_obj=tl, phy_ctx=phy_ctx)
            node2phyn[ml] = phynd
            leaves.add(phynd)
        int_phylo = set()
        for ul in unmatched_lvs:
            assert ul not in node2phyn
            phynd = PhyloNode(vnode=ul, phy_ctx=phy_ctx)
            node2phyn[ul] = phynd
            leaves.add(phynd)
        for i_nd in internals:
            assert i_nd not in node2phyn
            phynd = PhyloNode(vnode=i_nd, phy_ctx=phy_ctx)
            node2phyn[i_nd] = phynd
            int_phylo.add(phynd)
        for phynd in leaves:
            par_v_nd = phynd.vnode.adjacent()[0]
            par_phy_nd = node2phyn[par_v_nd]
            par_phy_nd.add_adjacent(phynd, next(iter(phynd.vnode.edges)))
        for phynd in int_phylo:
            this_v_nd = phynd.vnode
            for edge in this_v_nd.edges:
                adj_v_nd = edge.other_node(this_v_nd)
                adj_phy_nd = node2phyn[adj_v_nd]
                adj_phy_nd.add_adjacent(phynd, edge)
        return node2phyn


def avg_char_width(text_list: List[SafeTextLine]) -> float:
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


def find_closest(loc: Point, el_list: List[Any]) -> Tuple[float, Any]:
    dist, closest = float("inf"), None
    for el in el_list:
        d = calc_dist(loc, el.loc)
        if d < dist:
            dist = d
            closest = el
    return dist, closest


def _analyze_text_and_curves(text_lines, curves):
    graph = GraphFromEdges()
    for curve in curves:
        graph.add_curve(curve)
    forest = graph.build_forest()
    extra_lines = set(text_lines)
    best_tree, best_score = None, float("inf")
    for n, c in enumerate(forest.components):
        if len(c) > 4:
            tree = forest.interpret_as_tree(n, text_lines)
            score = tree.score
            if score < best_score:
                best_score = score
                best_tree = tree
            extra_lines = extra_lines.difference(tree.used_text)
    if not best_tree:
        return
    pma = best_tree.attempt
    best_legend, best_leg_score = None, float("inf")
    for n, c in enumerate(forest.components):
        if len(c) <= 4:
            legend = forest.interpret_as_legend(n, pma.unused_text)
            if (legend is not None) and (legend.score < best_leg_score):
                best_leg_score = legend.score
                best_legend = legend
    edge_len_scaler = None
    if best_legend:
        edge_len_scaler = best_legend.edge_len_scaler
    best_tree.clean_for_export()
    print(best_tree.root.get_newick(edge_len_scaler))


_skip_types = {LTImage}


def find_text_and_curves(
    fig, params=None, image_writer=None
) -> Tuple[UnprocessedRegion, List[str]]:
    if params is None:
        params = LAParams()
    char_objs = []
    text_lines = []
    otherobjs = []
    image_paths = []
    for el in fig:
        if isinstance(el, LTChar):
            char_objs.append(el)
        elif isinstance(el, LTTextBox):
            t = el.get_text()
            for sel in el:
                if isinstance(sel, LTTextLine):
                    text_lines.append(sel)
        elif isinstance(el, LTTextLine):
            text_lines.append(el)
        elif type(el) not in _skip_types:
            otherobjs.append(el)
        else:
            if image_writer is not None and isinstance(el, LTImage):
                log.debug(f"Exporting {type(el)}")
                try:
                    name = image_writer.export_image(el)
                except:
                    log.exception("image export failed")
                else:
                    image_paths.append(name)
            else:
                log.debug(f"Skipping element of type {type(el)}")
    if char_objs:
        text_lines.extend(list(fig.group_objects(params, char_objs)))
    return UnprocessedRegion(text_lines, otherobjs, fig), image_paths


def filter_text_and_curves(text_lines, otherobjs):
    ftl, fc = [], []
    for line in text_lines:
        ftl.append(line)
    for obj in otherobjs:
        if isinstance(obj, LTCurve):
            if len(obj.pts) > 5:
                debug(f"ignoring curve with too many points: {obj}, {obj.__dict__}")
                continue
            elif len(obj.pts) < 2:
                debug(f"ignoring curve with too few points: {obj}, {obj.__dict__}")
                continue
            fc.append(obj)
            # print(f"curve from {obj.pts[0]} to {obj.pts[-1]}")
        else:
            print("Unknown", obj, obj.__dict__)
    return ftl, fc


def analyze_figure(fig, params=None):
    unproc_page = find_text_and_curves(fig, params=params)[0]
    return  # TEMP!
    with open("cruft/debug.html", "w") as svg_out:
        to_html(svg_out, unproc_region=unproc_page)
    ftl, fc = filter_text_and_curves(unproc_page.text_lines, unproc_page.nontext_objs)
    return _analyze_text_and_curves(ftl, fc)


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
        return (self.x0, self.y0, self.x1, self.y1)


class SafeTextLine(object):
    """Slimmed down version of LTLine designed to be safe for pickling."""

    def __init__(self, lt_line, eertgif_id):
        self.eertgif_id = eertgif_id
        self.x0 = safe_number(lt_line.x0)
        self.y0 = safe_number(lt_line.y0)
        self.x1 = safe_number(lt_line.x1)
        self.y1 = safe_number(lt_line.y1)
        assert abs(self.height - lt_line.height) < DIM_TOL
        assert abs(self.width - lt_line.width) < DIM_TOL
        self.word_margin = lt_line.word_margin
        self.text = str(lt_line.get_text())
        if isinstance(lt_line, LTTextLineHorizontal):
            self.direction = AxisDir.HORIZONTAL
        elif isinstance(lt_line, LTTextLineVertical):
            self.direction = AxisDir.VERTICAL
        else:
            self.direction = AxisDir.UNKNOWN
        self.all_fonts = []
        for el in lt_line:
            assert isinstance(el, LTChar) or isinstance(el, LTAnno)

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
        return (self.x0, self.y0, self.x1, self.y1)


def convert_to_safe_line(text_lines, eertgif_id):
    sl = []
    for line in text_lines:
        sl.append(SafeTextLine(line, eertgif_id=eertgif_id))
        eertgif_id += 1
    return sl, eertgif_id


def convert_to_safe_curves(curves, eertgif_id):
    sl = []
    for curve in curves:
        sl.append(SafeCurve(curve, eertgif_id=eertgif_id))
        eertgif_id += 1
    return sl, eertgif_id


class UnprocessedRegion(object):
    def __init__(self, text_lines, nontext_objs, container):
        self.page_num = None
        self.subpage_num = None
        eertgif_id = 0
        self.text_lines, eertgif_id = convert_to_safe_line(text_lines, eertgif_id)
        self.nontext_objs, eertgif_id = convert_to_safe_curves(nontext_objs, eertgif_id)
        self.container_bbox = tuple(container.bbox)
        assert isinstance(self.container_bbox, tuple)
        assert len(self.container_bbox) == 4
        for el in self.container_bbox:
            assert isinstance(el, float) or isinstance(el, int)

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


def get_regions_unprocessed(filepath, params=None, image_writer=None):
    ur = []
    image_paths = []
    for n, page_layout in enumerate(extract_pages(filepath)):
        figures = [el for el in page_layout if isinstance(el, LTFigure)]
        if figures:
            for fn, fig in enumerate(figures):
                unproc_page, imgs = find_text_and_curves(
                    fig, params=params, image_writer=image_writer
                )
                image_paths.extend(imgs)
                if unproc_page.has_content:
                    unproc_page.page_num = n
                    unproc_page.subpage_num = fn
                    ur.append(unproc_page)
        else:
            # try whole page as figure container
            unproc_page, imgs = find_text_and_curves(
                page_layout, params=params, image_writer=image_writer
            )
            image_paths.extend(imgs)
            if unproc_page.has_content:
                unproc_page.page_num = n
                ur.append(unproc_page)
    return ur, image_paths


def main(fp):
    # params = LAParams()
    for page_layout in extract_pages(fp):
        figures = [el for el in page_layout if isinstance(el, LTFigure)]
        if figures:
            for fig in figures:
                analyze_figure(fig)
        else:
            # try whole page as figure container
            analyze_figure(page_layout)
        # for element in page_layout:
        #     if isinstance(element, LTFigure):
        #         analyze_figure(element)
        #     else:
        #         debug(f"Skipping non-figure {element}")
        # for sub in element:
        #
        #     try:
        #         for subsub in sub:
        #             print(f"    subsub = {subsub}")
        #     except TypeError:
        #         pass


if __name__ == "__main__":
    main(sys.argv[1])
