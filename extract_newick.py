#!/usr/bin/env python3
import sys

from pdfminer.high_level import extract_pages, LAParams
from pdfminer.layout import LTChar, LTFigure, LTCurve
from pdfminer.utils import fsplit
from math import sqrt

# Includes some code from pdfminer layout.py

VERBOSE = True


def debug(msg):
    if VERBOSE:
        sys.stderr.write(f"{msg}\n")


class Node(object):
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.edges = set()

    def add_edge(self, edge):
        self.edges.add(edge)


class Edge(object):
    def __init__(self, curve, nd1, nd2):
        self.curve, self.nd1, self.nd2 = curve, nd1, nd2
        nd1.add_edge(self)
        nd2.add_edge(self)


def calc_dist(pt1, pt2):
    xsq = (pt1[0] - pt2[0]) ** 2
    ysq = (pt1[1] - pt2[1]) ** 2
    return sqrt(xsq + ysq)


class PlanarContainer(object):
    def __init__(self):
        self.by_x = []
        self._all_nodes = []

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


def _analyze_text_and_curves(text_lines, curves):
    graph = GraphFromEdges()
    for curve in curves:
        graph.add_curve(curve)


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
