from __future__ import annotations

import logging
from typing import List, Tuple, Union, Optional

from pdfminer.utils import Point
from .point_map import PointMap
from .util import Direction, calc_dist
from .safe_containers import SafeCurve, SafeTextLine

log = logging.getLogger(__name__)


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

    def find_row_exact(self, x: float) -> Optional[PointMap]:
        return self.by_x.get(x)

    def _find_closest_rows(self, x: float, tol: float) -> List[PointMap]:
        by_dist = []
        for n, row_tup in enumerate(self.by_x.items()):
            row_x, row_map = row_tup
            dist = abs(row_x - x)
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


class Forest(object):
    def __init__(self, graph: GraphFromEdges):
        self.components = []
        self.graph = graph
        self.trees = []
        self.legends = []

    def interpret_as_legend(self, idx: int, text_lines: List[SafeTextLine]):
        from .phylo import PhyloLegend

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

    def interpret_as_tree(self, idx: int, text_lines: List[SafeTextLine]):
        from .phylo import PhyloTree

        comp = self.components[idx]
        while len(self.trees) <= idx:
            self.trees.append(None)
        t = self.trees[idx]
        if t is not None:
            return t
        t = PhyloTree(connected_nodes=comp, forest=self, text_lines=text_lines)
        self.trees[idx] = t
        return t