from __future__ import annotations

import logging
from typing import List, Tuple, Union, Optional

from pdfminer.utils import Point
from .point_map import PointMap
from .util import Direction, calc_dist
from .safe_containers import SafeCurve, SafeTextLine

log = logging.getLogger(__name__)


class Node(object):
    def __init__(
        self, x: float = None, y: float = None, loc: Point = None, id_gen=None
    ):
        self.eertgif_id = None if id_gen is None else id_gen.get_new_id()
        # debug(f"created node at {(x, y)}")
        if loc is None:
            assert x is not None
            assert y is not None
            self.loc = (x, y)
        else:
            self.loc = loc
        self.edges = set()
        self.component_idx = None

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
    def __init__(self, curve: SafeCurve, nd1: Node, nd2: Node, id_gen):
        self.curve, self.nd1, self.nd2 = curve, nd1, nd2
        self.eertgif_id = None if id_gen is None else id_gen.get_new_id()
        nd1.add_edge(self)
        nd2.add_edge(self)

    @property
    def component_idx(self):
        return self.nd1.component_idx

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
    def __init__(self, id_gen):
        self.id_gen = id_gen
        self.eertgif_id = None if id_gen is None else id_gen.get_new_id()
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
                dist = calc_dist((ptx, pty), (row_x, cell_y))
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

    def find_row_exact(self, x: float) -> Optional[PointMap]:
        return self.by_x.get(x)

    def _find_closest_rows(self, x: float, tol: float) -> List[PointMap]:
        by_dist = []
        for n, row_tup in enumerate(self.by_x.items()):
            row_x, row_map = row_tup
            dist = abs(row_x - x)
            if dist < tol:
                by_dist.append((dist, n, (row_x, row_map)))
        by_dist.sort()
        return [i[-1] for i in by_dist]

    def new_at(self, pt: Point) -> Node:
        ptx = pt[0]
        pty = pt[1]
        row_map = self.by_x.setdefault(ptx, PointMap())
        nd = Node(ptx, pty, id_gen=self.id_gen)
        self._all_nodes.append(nd)
        row_map.setdefault(pty, nd)
        return nd


class GraphFromEdges(object):
    def __init__(self, id_gen, node_merge_tol=0.01):
        self.nodes = PlanarContainer(id_gen)
        self.edges = set()
        self.tol = node_merge_tol
        self.eertgif_id = None if id_gen is None else id_gen.get_new_id()
        self.id_gen = id_gen

    def iter_nodes(self):
        return self.nodes.iter_nodes()

    def add_curve(self, curve: SafeCurve) -> Edge:
        pt1, pt2 = curve.pts[0], curve.pts[-1]
        nd1 = self.find_or_insert_node(pt1)[0]
        nd2 = self.find_or_insert_node(pt2)[0]
        edge = Edge(curve, nd1, nd2, id_gen=self.id_gen)
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
        forest = Forest(self, id_gen=self.id_gen)
        included = set()
        for nd in self.nodes.iter_nodes():
            if nd in included:
                continue
            nd_set = set()
            component_idx = len(forest.components)
            forest.components.append(nd_set)
            nd.add_connected(nd_set)
            for nn in nd_set:
                nn.component_idx = component_idx
            assert not included.intersection(nd_set)
            included.update(nd_set)
        return forest


class Forest(object):
    def __init__(self, graph: GraphFromEdges, id_gen):
        self.components = []
        self.graph = graph
        self.trees = []
        self.legends = []
        self.id_gen = id_gen
        self.eertgif_id = None if id_gen is None else id_gen.get_new_id()

    def interpret_as_legend(self, idx: int, text_lines: List[SafeTextLine]):
        from .phylo import PhyloLegend

        comp = self.components[idx]
        while len(self.legends) <= idx:
            self.legends.append(None)
        t = self.legends[idx]
        if t is not None:
            return t
        try:
            t = PhyloLegend(
                connected_nodes=comp,
                forest=self,
                text_lines=text_lines,
                id_gen=self.id_gen,
            )
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
        t = PhyloTree(
            connected_nodes=comp, forest=self, text_lines=text_lines, id_gen=self.id_gen
        )
        self.trees[idx] = t
        return t
