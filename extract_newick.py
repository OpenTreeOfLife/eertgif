#!/usr/bin/env python3
import sys

from pdfminer.high_level import extract_pages, LAParams
from pdfminer.layout import LTChar, LTFigure, LTCurve
from pdfminer.utils import fsplit
from math import sqrt
from enum import IntEnum

# Includes some code from pdfminer layout.py

VERBOSE = True


def debug(msg):
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


class Node(object):
    def __init__(self, x, y):
        debug(f"created node at {(x, y)}")
        self.x, self.y = x, y
        self.edges = set()

    def add_edge(self, edge):
        self.edges.add(edge)

    def __str__(self):
        return f"Node({self.x}, {self.y})"

    __repr__ = __str__

    def add_connected(self, nd_set, taboo=None):
        seen = taboo if taboo is not None else set()
        seen.add(self)
        nd_set.add(self)
        for edge in self.edges:
            for n in [edge.nd1, edge.nd2]:
                if (n is not self) and (n not in seen):
                    n.add_connected(nd_set, taboo=seen)

    def adjacent(self):
        return [i.other_node(self) for i in self.edges]

    @property
    def dir_from_adj(self):
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
    def __init__(self, curve, nd1, nd2):
        self.curve, self.nd1, self.nd2 = curve, nd1, nd2
        nd1.add_edge(self)
        nd2.add_edge(self)

    def __str__(self):
        return f"Edge({self.nd1} <==> {self.nd2})"

    __repr__ = __str__

    def other_node(self, nd):
        if nd is self.nd1:
            return self.nd2
        assert nd is self.nd2
        return self.nd1


def calc_dist(pt1, pt2):
    xsq = (pt1[0] - pt2[0]) ** 2
    ysq = (pt1[1] - pt2[1]) ** 2
    return sqrt(xsq + ysq)


class PlanarContainer(object):
    def __init__(self):
        self.by_x = []
        self._all_nodes = []

    def iter_nodes(self):
        return iter(self._all_nodes)

    def find_closest(self, point, tol):
        ptx, pty = point
        rows = self.find_closest_rows(ptx, tol)
        if not rows:
            return None
        min_diff = tol
        min_el = None
        for row in rows:
            for el in row:
                dist = calc_dist((ptx, pty), (el.x, el.y))
                if dist < min_diff:
                    min_diff = dist
                    min_el = el
        return min_el

    def find_exact(self, point):
        ptx, pty = point
        row = self.find_row_exact(ptx)
        if row is None:
            return None
        for el in row:
            if el.y == pty:
                return el
            if el.y > pty:
                break
        return None

    def find_row_exact(self, x):
        for row in self.by_x:
            if row[0].x == x:
                return row
            if row[0].x > x:
                break
        return None

    def find_closest_rows(self, x, tol):
        by_dist = []
        for n, row in enumerate(self.by_x):
            dist = abs(row[0].x - x)
            if dist < tol:
                by_dist.append((dist, n, row))
        by_dist.sort()
        return [i[-1] for i in by_dist]

    def new_at(self, pt):
        ptx = pt[0]
        pty = pt[1]
        dest_row = None
        bef_ind = None
        for n, row in enumerate(self.by_x):
            if row[0].x == ptx:
                dest_row = row
                break
            if row[0].x > ptx:
                bef_ind = n
                break
        nd = Node(ptx, pty)
        self._all_nodes.append(nd)
        if dest_row:
            bef_y_ind = None
            for n, el in enumerate(dest_row):
                if el.y >= pty:
                    bef_y_ind = n
                    break
            if bef_y_ind is not None:
                dest_row.insert(bef_y_ind, nd)
            else:
                dest_row.append(nd)
        elif bef_ind is not None:
            self.by_x.insert(bef_ind, [nd])
        else:
            self.by_x.append([nd])
        return nd


class GraphFromEdges(object):
    def __init__(self):
        self.nodes = PlanarContainer()
        self.edges = set()
        self.tol = 0.01

    def add_curve(self, curve):
        pt1, pt2 = curve.pts[0], curve.pts[-1]
        nd1 = self.find_or_insert_node(pt1)[0]
        nd2 = self.find_or_insert_node(pt2)[0]
        edge = Edge(curve, nd1, nd2)
        self.edges.add(edge)

    def find_or_insert_node(self, point, tol=None):
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

    def build_forest(self):
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
    def __init__(self, graph):
        self.components = []
        self.graph = graph
        self.trees = []

    def interpret_as_tree(self, idx, text_lines):
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
    def __init__(self, connected_nodes=None, forest=None, text_lines=None):
        self.forest = forest
        self.used_text = set()
        internals, externals = [], []
        for nd in connected_nodes:
            cont = externals if len(nd.edges) == 1 else internals
            cont.append(nd)
        north, east, south, west = [], [], [], []
        for ext in externals:
            d = ext.dir_from_adj
            # print(ext, "is", d, "from adjacent node, ", ext.adjacent()[0])
            if d & Direction.NORTH:
                north.append(d)
            if d & Direction.EAST:
                east.append(d)
            if d & Direction.SOUTH:
                south.append(d)
            if d & Direction.WEST:
                west.append(d)
        print(len(north), "nodes to the north of their neighbor")
        print(len(east), "nodes to the east of their neighbor")
        print(len(south), "nodes to the south of their neighbor")
        print(len(west), "nodes to the west of their neighbor")
        nblob = self._try_as_tips_to(Direction.NORTH, internals, externals, text_lines)
        eblob = self._try_as_tips_to(Direction.EAST, internals, externals, text_lines)
        sblob = self._try_as_tips_to(Direction.SOUTH, internals, externals, text_lines)
        wblob = self._try_as_tips_to(Direction.WEST, internals, externals, text_lines)
        blob_list = [(i[0], n, i) for n, i in enumerate([eblob, nblob, sblob, wblob])]
        blob_list.sort()
        best_blob = blob_list[0]
        self.tension_score = best_blob[0]
        self.root = best_blob[1]
        self.used_text.update(best_blob[2])
        self.num_tips = best_blob[3]
        s

    def _try_as_tips_to(self, tip_dir, internals, externals, text_lines):
        pass


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
