from __future__ import annotations

import logging
from typing import List, Tuple, Union, Optional

from pdfminer.utils import Point
from .point_map import PointMap
from .util import Direction, calc_dist, all_corner_shapes, AxisDir
from .safe_containers import SafeCurve, SafeTextLine, CurveShape

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

    def __getitem__(self, idx):
        if idx == 0 or idx == -2:
            return self.x
        if idx == 1 or idx == -1:
            return self.y
        raise IndexError(f"{idx} is out of range for a Node/point.")

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

    def most_extreme_vis_point(self, direction):
        c = self.curve
        me_pt = None
        find_max = True
        idx = 0
        if direction == Direction.EAST:
            pass

            find_max = True
        elif direction == Direction.EAST:
            find_max = False

        else:
            idx = 1
            if direction == Direction.SOUTH:
                find_max = False
            else:
                assert direction == Direction.NORTH
        if find_max:
            me = float("-inf")
            for pt in c.pts:
                if pt[idx] > me:
                    me_pt = pt
                    me = pt[idx]
        else:
            me = float("inf")
            for pt in c.pts:
                if pt[idx] < me:
                    me_pt = pt
                    me = pt[idx]
        return me_pt

    def axis_contains(self, axis, point, tol):
        """
        Uses effective diganal and shape to find axes.
        returns:
            False, None, None  or
            True, list of lenght 2 of coordinates with variable coord None, dixt
        """
        c = self.curve
        false_ret = False, None, None
        if (c.eff_diagonal is None) or (c.shape not in all_corner_shapes):
            # No axis unless a corner
            return false_ret
        eff_d1, eff_d2 = c.eff_diagonal
        if axis == AxisDir.VERTICAL:
            cidx = 0
            if c.shape == CurveShape.CORNER_LL or c.shape == CurveShape.CORNER_UL:
                ext_fn = min
            else:
                ext_fn = max
        else:
            assert axis == AxisDir.HORIZONTAL
            cidx = 0
            if c.shape == CurveShape.CORNER_LL or c.shape == CurveShape.CORNER_LR:
                ext_fn = min
            else:
                ext_fn = max
        ax_const_coord = ext_fn(eff_d1[cidx], eff_d2[cidx])
        pc = point[cidx]
        cdist = abs(pc - ax_const_coord)
        if cdist > tol:
            # constant coord not within TOL
            return false_ret
        vidx = 1 - cidx
        ax_var = (eff_d1[vidx], eff_d2[vidx])
        if ax_var[0] > ax_var[1]:
            ax_var = (ax_var[1], ax_var[0])
        vc = point[vidx]
        if (ax_var[0] - vc) > tol or (vc - ax_var[1]) > tol:
            # point's variable coord more than TOL outside of the endpoints
            return false_ret
        ret_coord = [None, None]
        ret_coord[cidx] = ax_const_coord
        if ax_var[0] < vc < ax_var[1]:
            # const withing TOL, variable witin axis
            return True, ret_coord, cdist
        # variable coordinate outside of axis, but coudl be within TOL
        #   of the endpoints
        ex_point = [None, None]
        ex_point[cidx] = ax_const_coord
        if vc < ax_var[0]:
            ex_point[vidx] = ax_var[0]
            dist = calc_dist(point, tuple(ex_point))
            if dist <= tol:
                return True, ret_coord, dist
        elif vc > ax_var[1]:
            ex_point[vidx] = ax_var[1]
            dist = calc_dist(point, tuple(ex_point))
            if dist <= tol:
                return True, ret_coord, dist
        return false_ret


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

    def remove_node(self, nd):
        del_top_key = None
        for x, row in self.by_x.items():
            del_y_key = None
            for y, nd_ref in row.items():
                if nd_ref is nd:
                    del_y_key = y
            if del_y_key:
                del row[del_y_key]
            if not row:
                del_top_key = x
        if del_top_key is not None:
            del self.by_x[del_top_key]
        self._all_nodes.remove(nd)


class GraphFromEdges(object):
    def __init__(self, id_gen, node_merge_tol=0.01):
        self.nodes = PlanarContainer(id_gen)
        self.edges = set()
        self.tol = node_merge_tol
        self.eertgif_id = None if id_gen is None else id_gen.get_new_id()
        self.id_gen = id_gen

    def debug_check(self):
        evisited = set()
        nds_visited = set()
        for nd in self.nodes._all_nodes:
            nds_visited.add(nd)
            for edge in nd.edges:
                assert (
                    nd == edge.nd1 or nd == edge.nd2
                ), f"node{nd.eertgif_id} ({nd}), not in edge {edge.eertgif_id} {str(edge)}"
                evisited.add(edge)
        if evisited != self.edges:
            d = evisited - self.edges
            if d:
                assert False, f"Edges {d} visited but not in self.edges"
            d = self.edges - evisited
            if d:
                assert False, f"Edges {d} in self.edges, but not visited."

        for edge in evisited:
            assert edge.nd1 in nds_visited
            assert edge.nd2 in nds_visited

    def iter_nodes(self):
        return self.nodes.iter_nodes()

    def add_curve(self, curve: SafeCurve) -> Edge:
        assert curve.eff_diagonal is not None
        pt1, pt2 = curve.eff_diagonal[0], curve.eff_diagonal[-1]
        nd1 = self.find_or_insert_node(pt1)[0]
        nd2 = self.find_or_insert_node(pt2)[0]
        edge = Edge(curve, nd1, nd2, id_gen=self.id_gen)
        self.edges.add(edge)
        return edge

    def force_merge(
        self,
        edge1,  # edge that holds a Node to be merged
        most_extreme_pt_edge1,  # Point, not Node
        edge2,
        var_coord,
    ):
        self.debug_check()
        log.warning(f"Force merge {edge1} and {edge2}")
        # find closest node in edge1
        dist_n1_1 = calc_dist(most_extreme_pt_edge1, (edge1.nd1.x, edge1.nd1.y))
        dist_n1_2 = calc_dist(most_extreme_pt_edge1, (edge1.nd2.x, edge1.nd2.y))
        rep_1_in_1 = dist_n1_1 <= dist_n1_2
        if rep_1_in_1:
            cn1 = edge1.nd1
        else:
            cn1 = edge1.nd2
        log.warning(f"  Force merge cn1={cn1}")
        # find closest node in edge2
        if var_coord[0] is None:
            idx = 1
        else:
            idx = 0
            assert var_coord[1] is None
        vc = var_coord[idx]
        assert vc is not None
        cn2 = edge2.nd1
        if abs(edge2.nd1[idx] - vc) > abs(edge2.nd1[idx] - vc):
            cn2 = edge2.nd2
        log.warning(f"  Force merge cn2={cn2}")
        # Now remove edge1 from cn1
        cn1.edges.remove(edge1)
        # move other edges attached to that node, and attach them to cn2
        other = list(cn1.edges) + [edge1]
        for other_edge in other:
            if other_edge is edge2:
                continue
            if cn1 is other_edge.nd1:
                other_edge.nd1 = cn2
                if cn1 is other_edge.nd2:
                    other_edge.nd2 = cn2
            else:
                assert cn1 is other_edge.nd2
                other_edge.nd2 = cn2
            cn2.edges.add(other_edge)
            if other_edge is not edge1:
                cn1.edges.remove(other_edge)
        if len(cn1.edges) == 0:
            log.warning(f"    Force merge removing cn1={cn1}")
            self.nodes.remove_node(cn1)
        else:
            log.warning(f"    Force merge retaining cn1={cn1}")

        self.debug_check()

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
        self.rect_base_intercept_tol = None

    def _post_merge_hook(self, edge1, edge2):
        c1_idx = edge1.component_idx
        c2_idx = edge2.component_idx
        assert c1_idx != c2_idx
        min_idx, max_idx = min(c1_idx, c2_idx), max(c1_idx, c2_idx)
        to_die_list = self.components[max_idx]
        to_grow_list = self.components[min_idx]
        for nd in to_die_list:
            nd.component_idx = min_idx
            to_grow_list.append(nd)
        self.components.pop(max_idx)
        for to_decr_list in self.components[max_idx:]:
            assert to_decr_list
            bef_idx = to_decr_list[0].component_idx
            new_idx = bef_idx - 1
            for nd in to_decr_list:
                nd.component_idx = new_idx
        return len(self.components)

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
