#!/usr/bin/env python
from __future__ import annotations

import logging
from io import StringIO
from typing import List, Set

from .graph import Node, Forest, Edge
from .safe_containers import SafeTextLine
from .util import (
    find_closest_first,
    Penalty,
    COORD_TOL,
    as_numeric,
    DEFAULT_LABEL_GAP,
    Direction,
    AxisDir,
    rotate_cw,
    CARDINAL,
    midpoint,
    calc_dist,
)

log = logging.getLogger(__name__)


class CycleDetected(ValueError):
    def __init__(self, msg):
        ValueError.__init__(self, msg)


class PhyloTree(object):
    def __init__(
        self,
        connected_nodes: Set[Node] = None,
        forest: Forest = None,
        text_lines: List[SafeTextLine] = None,
        id_gen=None,
        tip_dir=None,
    ):
        log.debug(
            f"PhyloTree.__init__, tip_dir={repr(tip_dir)}, #connected_nodes = {len(connected_nodes)}"
        )

        # id_list = [i.eertgif_id for i in text_lines]
        # assert 136 not in id_list
        # assert 126 not in id_list
        # assert 123 not in id_list

        self.id_gen = id_gen
        self.eertgif_id = None if id_gen is None else id_gen.get_new_id()
        self.forest = forest
        self.used_text = set()
        self.root = None
        self.pma = None

        int_nds, ext_nds = [], []
        lx, ly, hx, hy = float("inf"), float("inf"), float("-inf"), float("-inf")
        for nd in connected_nodes:
            cont = ext_nds if len(nd.edges) == 1 else int_nds
            if len(nd.edges) > 1:
                log.debug(f"nd{(nd.x, nd.y)} seems internal: nd.edges = {nd.edges}")
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
        log.debug(
            f"PhyloTree.__init__ {len(ext_nds)} externals, {len(int_nds)} internals"
        )

        # text_bbox = (lx, ly, hx, hy)
        # print(
        #     f"nodes_bbox = {nodes_bbox} text_bbox={text_bbox} {len(horiz_text)}, {len(vert_text)}"
        # )
        dir_list = CARDINAL if tip_dir is None else [tip_dir]
        from .phylo_map_attempt import PhyloMapAttempt

        by_dir = [
            PhyloMapAttempt(
                id_gen=self.id_gen,
                tip_dir=i,
                internals=int_nds,
                externals=ext_nds,
                horiz_text=horiz_text,
                vert_text=vert_text,
            )
            for i in dir_list
        ]
        min_score, best_attempt = float("inf"), None
        for attempt in by_dir:
            s = attempt.score
            if s < min_score:
                min_score = s
                best_attempt = attempt
            # print(f"Attempt score = {attempt.score} from {attempt.penalties}")
        if best_attempt is None:
            best_attempt = by_dir[0]
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

    @property
    def matched_phy_leaves(self):
        if self.pma is None:
            return None
        return self.pma.matched_phy_leaves

    @property
    def component_idx(self):
        if self.root is None:
            return None
        return self.root.vnode.component_idx

    @property
    def unused_text(self):
        if self.pma is None:
            return []
        return self.pma.unused_text

    @property
    def num_tips(self):
        return len(self.tips())

    def tips(self):
        if self.root is None or self.pma is None:
            return []
        return [i for i in self.post_order() if i.is_tip]

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
                    while True:
                        nl = f"{label}-duplicate#{num}"
                        num += 1
                        if nl not in dup_labels:
                            nd._label = nl
                            break
                    log.debug(f'duplicate label. Renaming "{label}" to "{nl}"')

    def post_order(self):
        if self.root is None:
            return []
        return self.root.post_order()

    @property
    def score(self):
        return self.pma.score

    @property
    def attempt(self):
        return self.pma


def min_coord_north(n):
    return n.y


def min_coord_south(n):
    return -n.y


def min_coord_east(n):
    return n.x


def min_coord_west(n):
    return -n.x


class PhyloTreeData(object):
    """Blob of data common to all nodes/edges"""

    def __init__(self, tip_dir: Direction = None, attempt=None, id_gen=None):
        self.eertgif_id = None if id_gen is None else id_gen.get_new_id()
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
            Direction.NORTH: min_coord_north,
            Direction.SOUTH: min_coord_south,
            Direction.EAST: min_coord_east,
            Direction.WEST: min_coord_west,
        }
        self.pos_min_fn = dir2min_coord[tip_dir]
        dir_for_last_child = rotate_cw(tip_dir)
        self.child_pos_fn = dir2min_coord[dir_for_last_child]


class PhyloNode(object):
    def __init__(
        self,
        vnode: Node = None,
        label_obj: SafeTextLine = None,
        phy_ctx: PhyloTreeData = None,  # alias to mapping's data struct
        id_gen=None,
    ):
        self.eertgif_id = None if id_gen is None else id_gen.get_new_id()
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
            return self.label_obj.get_text().strip()
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
        wip = []
        for n, i in enumerate(self._unsorted_children):
            # log.warning(f"{n} {i}, {i.vnode}")
            tup = (csfn(i), n, i)
            wip.append(tup)
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

    def root_based_on_par(self, par: PhyloNode = None, seen=None) -> None:
        if seen is None:
            seen = set()
        pma = self.phy_ctx.attempt
        coord_fn = self.phy_ctx.pos_min_fn

        if self in seen:
            raise CycleDetected(f"node with edges {self.vnode.edges} in a cycle")
        seen.add(self)
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
            if adj is self:
                # raise CycleDetected("I'm just beside myself")
                log.debug("I'm just beside myself cycle, skipping edge")
                continue
            self._unsorted_children.append(adj)
            adj.root_based_on_par(par=self, seen=seen)
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


class PhyloLegend(object):
    def __init__(
        self,
        connected_nodes: Set[Node] = None,
        forest: Forest = None,
        text_lines: List[SafeTextLine] = None,
        id_gen=None,
    ):
        self.forest = forest
        self.eertgif_id = None if id_gen is None else id_gen.get_new_id()
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
        self.edge_len_scaler = None
        self.unused_text = set([i for i in text_lines if i is not self.legend_text])
        self.unused_nodes = [i for i in connected_nodes if i is not self.bar]
        self.score = abs(DEFAULT_LABEL_GAP - min_d)
        try:
            self.edge_len_scaler = as_numeric(min_el[0].get_text())[1] / self.bar.length
        except:
            self.score = float("inf")
