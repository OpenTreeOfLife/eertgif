#!/usr/bin/env python3
from __future__ import annotations

import sys
from collections import namedtuple
from typing import List, Any, Set, Tuple, Union
from pdfminer.high_level import extract_pages, LAParams
from pdfminer.layout import (
    LTChar,
    LTFigure,
    LTCurve,
    LTTextLine,
    LTTextLineHorizontal,
    LTTextLineVertical,
)
from pdfminer.utils import fsplit, Point, Rect
from math import sqrt
from enum import IntEnum

# Includes some code from pdfminer layout.py

VERBOSE = True


def debug(msg: str) -> None:
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


CARDINAL = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


################################################################################
# Code for Pt and PointMap modified from code by Ned Batchelder
#   https://nedbatchelder.com/blog/201707/finding_fuzzy_floats.html
# "I don’t have a formal license for most of this code. I post it here in the
# spirit of sharing. Use it for what you will. " https://nedbatchelder.com/code
class Pt(namedtuple("Pt", "x")):
    # no need for special __eq__ or __hash__
    pass


class PointMap:
    def __init__(self):
        self._items = {}
        self._rounded = {}

    ROUND_DIGITS = 6
    JITTERS = [0, 0.5 * 10 ** -ROUND_DIGITS]

    def _round(self, pt, jitter):
        return Pt(round(pt.x + jitter, ndigits=self.ROUND_DIGITS))

    def _get_impl(self, pt, default=None):
        if not isinstance(pt, Pt):
            pt = Pt(float(pt))
        if pt in self._items:
            return self._items[pt], True
        for jitter in self.JITTERS:
            pt_rnd = self._round(pt, jitter)
            pt0 = self._rounded.get(pt_rnd)
            if pt0 is not None:
                return self._items[pt0], True
        return default, False

    def get(self, pt: Union[int, float, Pt], default=None):
        return self._get_impl(pt, default=default)[0]

    def setdefault(self, pt: Union[int, float, Pt], default=None):
        val, was_found = self._get_impl(pt, default=default)
        if not was_found:
            self.__setitem__(pt, val)
        return val

    def __getitem__(self, pt):
        val, was_found = self._get_impl(pt)
        if not was_found:
            raise KeyError(pt)
        return val

    def __setitem__(self, pt, val):
        if not isinstance(pt, Pt):
            pt = Pt(float(pt))
        self._items[pt] = val
        for jitter in self.JITTERS:
            pt_rnd = self._round(pt, jitter)
            old = self._rounded.get(pt_rnd)
            store = True
            if old is not None:
                if old.x != pt.x:
                    del self._items[old]  # rounded key clash, replace old key in items
                else:
                    store = False  # Already stored
            if store:
                self._rounded[pt_rnd] = pt

    def __iter__(self):
        return iter(self._items)

    def items(self):
        return self._items.items()

    def keys(self):
        return [i.x for i in self._items.keys()]

    def values(self):
        return self._items.values()


################################################################################


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
    def __init__(self, curve: LTCurve, nd1: Node, nd2: Node):
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

    def add_curve(self, curve: LTCurve) -> Edge:
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


class Forest(object):
    def __init__(self, graph: GraphFromEdges):
        self.components = []
        self.graph = graph
        self.trees = []

    def interpret_as_tree(self, idx: int, text_lines: List[LTTextLine]) -> PhyloTree:
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
        text_lines: List[LTTextLine] = None,
    ):
        self.forest = forest
        self.used_text = set()
        int_nds, ext_nds = [], []
        lx, ly, hx, hy = float("inf"), float("inf"), float("-inf"), float("-inf")
        for nd in connected_nodes:
            cont = ext_nds if len(nd.edges) == 1 else int_nds
            cont.append(nd)
            lx = min(lx, nd.x)
            ly = min(ly, nd.y)
            hx = max(hx, nd.x)
            hy = max(hy, nd.y)
        nodes_bbox = (lx, ly, hx, hy)
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
            if isinstance(ltline, LTTextLineHorizontal):
                horiz_text.append(ltline)
            else:
                assert isinstance(ltline, LTTextLineVertical)
                vert_text.append(ltline)
        text_bbox = (lx, ly, hx, hy)
        print(
            f"nodes_bbox = {nodes_bbox} text_bbox={text_bbox} {len(horiz_text)}, {len(vert_text)}"
        )
        by_dir = [
            self._try_as_tips_to(i, int_nds, ext_nds, horiz_text, vert_text)
            for i in CARDINAL
        ]

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

    def _try_as_tips_to(
        self,
        tip_dir: Direction,
        internals: List[Node],
        externals: List[Node],
        horiz_text: List[LTTextLine],
        vert_text: List[LTTextLine],
    ):
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
        print(
            f"Trying DIR={repr(tip_dir)} ... len(externals) = {len(externals)}, len(inline_t)={len(inline_t)}"
        )
        by_lab, by_ext = {}, {}
        for label_t in inline_t:
            loc = (calc_x(label_t), calc_y(label_t))
            dist, ext = find_closest(loc, externals)
            by_lab[label_t] = (ext, dist)
            prev = by_ext.get(ext)
            if prev is None or dist < prev[-1]:
                by_ext[ext] = (label_t, dist)

        for label_t in inline_t:
            ext, dist = by_lab[label_t]
            if by_ext.get(ext, [None, None])[0] is label_t:
                print(f"{dist:6.3f} - matched - {repr(label_t.get_text())}")
            else:
                print(f"{dist:6.3f} - unmatched - {repr(label_t.get_text())}")


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
    for n, c in enumerate(forest.components):
        if len(c) > 4:
            tree = forest.interpret_as_tree(n, text_lines)
            extra_lines = extra_lines.difference(tree.used_text)


def analyze_figure(fig, params=None):
    if params is None:
        params = LAParams()
    (textobjs, otherobjs) = fsplit(lambda o: isinstance(o, LTChar), fig)
    textlines = list(fig.group_objects(params, textobjs))
    ftl, fc = [], []
    for line in textlines:
        # print(line.get_text(), f"@({line.x0}, {line.y0}) - ({line.x1}, {line.y1}) w={line.width} h={line.height}")
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
    return _analyze_text_and_curves(ftl, fc)


def main(fp):
    # params = LAParams()
    for page_layout in extract_pages(fp):
        for element in page_layout:
            if isinstance(element, LTFigure):
                analyze_figure(element)
            else:
                debug(f"Skipping non-figure {element}")
            # for sub in element:
            #
            #     try:
            #         for subsub in sub:
            #             print(f"    subsub = {subsub}")
            #     except TypeError:
            #         pass


if __name__ == "__main__":
    main(sys.argv[1])
