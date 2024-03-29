#!/usr/bin/env python
from __future__ import annotations

import logging
from math import sqrt
from typing import List, Dict, Set, Tuple, Optional

from .phylo import PhyloNode, PhyloTreeData, CycleDetected
from .graph import Node
from .safe_containers import SafeTextLine
from .util import (
    avg_char_width,
    Penalty,
    MIN_BR_TOL,
    mean_var,
    mean_vector,
    Direction,
    find_closest,
)

log = logging.getLogger(__name__)

MAX_MATCHABLE_SCORE = 100.0  # IDK about this...


class LocLabWrap(object):
    def __init__(self, loc, label):
        self.loc = loc
        self.label = label


def east_calc_x(el):
    return el.x0


def west_calc_x(el):
    return el.x1


def east_west_calc_y(el):
    return (el.y0 + el.y1) / 2.0


def south_calc_y(el):
    return el.y1


def north_calc_y(el):
    return el.y0


def north_south_calc_x(el):
    return (el.x0 + el.x1) / 2.0


class PhyloMapAttempt(object):
    def __init__(
        self,
        id_gen,
        tip_dir: Direction,
        internals: List[Node],
        externals: List[Node],
        horiz_text: List[SafeTextLine],
        vert_text: List[SafeTextLine],
    ):
        self.id_gen = id_gen
        self.eertgif_id = None if id_gen is None else id_gen.get_new_id()
        self.penalties = {}
        self.penalty_weights = {}
        self.root = None
        self.unmatched_ext_nodes = []
        self.unused_perpindicular_text = []
        self.unused_inline_text = []
        self.messages = []
        self.matched_phy_leaves = set()
        self.phy_ctx = None
        self.tip_dir = tip_dir
        if tip_dir in (Direction.EAST, Direction.WEST):
            inline_t = horiz_text
            perpindic_t = vert_text
            if tip_dir == Direction.EAST:
                self.calc_x = east_calc_x
            else:
                self.calc_x = west_calc_x
            self.calc_y = east_west_calc_y
        else:
            inline_t = vert_text
            perpindic_t = horiz_text
            if tip_dir == Direction.SOUTH:
                self.calc_y = south_calc_y
            else:
                self.calc_y = north_calc_y
            self.calc_x = north_south_calc_x
        self._finish_init(tip_dir, internals, externals, inline_t, perpindic_t)

    def _finish_init(
        self,
        tip_dir: Direction,
        internals: List[Node],
        externals: List[Node],
        inline_t: List[SafeTextLine],
        perpindic_t: List[SafeTextLine],
    ):
        log.debug(
            f"_try_as_tips_to DIR={repr(tip_dir)} {len(externals)} externals, len(inline_t)={len(inline_t)}"
        )
        blob = self._try_match_text(inline_t, externals)
        (
            matched_labels,
            orphan_labels,
            matched_dists,
            matched_leaves,
            unmatched_ext,
            by_lab,
        ) = blob
        if matched_labels:
            expected_def_gap = avg_char_width(matched_labels)
            mean_obs_gap, var_gap = mean_var(matched_dists)
            self.add_penalty(Penalty.LABEL_GAP_MEAN, mean_obs_gap)
            if var_gap:
                self.add_penalty(Penalty.LABEL_GAP_STD_DEV, sqrt(var_gap))
            self.build_tree_from_tips(
                internals=internals,
                matched_lvs=matched_leaves,
                unmatched_lvs=unmatched_ext,
                tip_labels=matched_labels,
                label2leaf=by_lab,
                unmatched_labels=orphan_labels,
            )
        else:
            # If there are no labels matched, there isn't much point of building a tree...
            self.add_penalty(Penalty.UNMATCHED_LABELS, float("inf"))
        self.unmatched_ext_nodes = unmatched_ext
        self.unused_perpindicular_text = perpindic_t

    def _try_match_text(self, inline_t: List[SafeTextLine], externals: List[Node]):
        if not (inline_t and externals):
            return [], [], [], [], set(externals), {}
        # first level matching:
        #   if an external node and a text object are
        #   closest to each other, then we call them a match
        blob = self._match_by_mutual_closest(inline_t, externals)
        (
            match_pairs,
            matched_labels,
            matched_leaves,
            matched_dists,
            unmatched_labels,
            unmatched_lvs,
            by_lab,
            by_ext,
        ) = blob

        self._match_more_using_offsets(
            match_pairs,
            matched_labels,
            matched_leaves,
            matched_dists,
            unmatched_labels=unmatched_labels,
            unmatched_lvs=unmatched_lvs,
            by_lab=by_lab,
            by_ext=by_ext,
        )

        self._match_all_acceptable_by_score(
            match_pairs,
            matched_labels,
            matched_leaves,
            matched_dists,
            unmatched_labels=unmatched_labels,
            unmatched_lvs=unmatched_lvs,
            by_lab=by_lab,
            by_ext=by_ext,
        )

        # unmatched_ext = set()
        # for nd in externals:
        #     if nd not in matched_leaves:
        #         unmatched_ext.add(nd)
        return (
            matched_labels,
            unmatched_labels,
            matched_dists,
            matched_leaves,
            unmatched_lvs,
            by_lab,
        )

    def _match_by_mutual_closest(
        self, unmatched_labels: List[SafeTextLine], externals: List[Node]
    ):
        calc_x, calc_y = self.calc_x, self.calc_y
        by_lab = {}
        label_wrappers = []
        for label_t in unmatched_labels:
            loc = (calc_x(label_t), calc_y(label_t))
            dist, ext = find_closest(loc, externals)
            assert ext is not None
            by_lab[label_t] = (ext, dist)
            label_wrappers.append(LocLabWrap(loc=loc, label=label_t))
        by_ext = {}
        for ext in externals:
            dist, lw = find_closest(ext.loc, label_wrappers)
            # log.debug(f"first level register {label_t.get_text().strip()} with dist={dist} {(ext.x, ext.y)} -> {loc}")
            by_ext[ext] = (lw.label, dist)

        matched_labels, lev1_orphans = [], []
        matched_leaves = set()
        matched_dists = []
        match_pairs = []
        unmatched_lvs = set(externals)
        to_remove = []
        for label_t in unmatched_labels:
            ext, dist = by_lab[label_t]
            if by_ext.get(ext, [None, None])[0] is label_t:
                matched_labels.append(label_t)
                lt = (calc_x(label_t), calc_y(label_t))
                log.debug(
                    f"primary match {label_t.get_text().strip()} with dist={dist} {ext} <=> {lt}"
                )
                matched_dists.append(dist)
                matched_leaves.add(ext)
                match_pairs.append((ext, label_t))
                unmatched_lvs.remove(ext)
                to_remove.append(label_t)
            else:
                lev1_orphans.append(label_t)
        for label_t in to_remove:
            unmatched_labels.remove(label_t)
        return (
            match_pairs,
            matched_labels,
            matched_leaves,
            matched_dists,
            lev1_orphans,
            unmatched_lvs,
            by_lab,
            by_ext,
        )

    def _match_all_acceptable_by_score(
        self,
        match_pairs: List[Tuple[Node, SafeTextLine]],
        matched_labels: List[SafeTextLine],
        matched_leaves: Set[Node],
        matched_dists: List[float],
        unmatched_labels: List[SafeTextLine],
        unmatched_lvs: Set[Node],
        by_lab,
        by_ext,
    ):
        if (not unmatched_lvs) or (not unmatched_labels):
            return unmatched_labels
        matching_stats = MatchingStats(match_pairs, self)
        sc_leaf_label = []

        for leaf in unmatched_lvs:
            sc_leaf_label.append(
                self._find_best_match(leaf, unmatched_labels, matching_stats)
            )

        while unmatched_labels and unmatched_lvs:
            sc_leaf_label.sort()
            best = sc_leaf_label.pop(0)
            score, leaf, label = best
            if score > MAX_MATCHABLE_SCORE:
                break
            log.debug(f"Score matching: {score}, {leaf} <=> {label.get_text().strip()}")

            match_pairs.append((leaf, label))
            matched_labels.append(label)
            matched_leaves.add(leaf)
            unmatched_labels.remove(label)
            unmatched_lvs.remove(leaf)
            by_lab[label] = (leaf, None)
            by_ext[leaf] = (label, None)

            # build list of indices in highest to lowest, to pop in the correct order below
            idx_to_pop = []
            for n, sc_lv_lab in enumerate(sc_leaf_label):
                if label is sc_lv_lab[-1]:
                    idx_to_pop.insert(0, n)
            for idx in idx_to_pop:
                sc_lv_lab = sc_leaf_label.pop(idx)
                leaf = sc_lv_lab[1]
                sc_leaf_label.append(
                    self._find_best_match(leaf, unmatched_labels, matching_stats)
                )
        return unmatched_labels

    def _find_best_match(self, leaf, unmatched_labels, matching_stats):
        min_score, min_score_label = float("inf"), None
        for label in unmatched_labels:
            score = matching_stats.score(leaf, label)
            log.debug(f"Score of {score} for {leaf} <==> {label.get_text().strip()}")
            if score < min_score:
                log.debug("New best")
                min_score, min_score_label = score, label
        return min_score, leaf, min_score_label

    def _match_more_using_offsets(
        self,
        match_pairs: List[Tuple[Node, SafeTextLine]],
        matched_labels: List[SafeTextLine],
        matched_leaves: Set[Node],
        matched_dists: List[float],
        unmatched_labels: List[SafeTextLine],
        unmatched_lvs: Set[Node],
        by_lab,
        by_ext,
    ):
        """Second-level matching using the mean offset of primary matches
        to find more cases of an external node and a text element being each
        other's closest match."""
        calc_x, calc_y = self.calc_x, self.calc_y

        # Level 2 matching.
        # Use the average offset between matched text and tips
        # to provide a better expected location for a tip's text
        offset_vec = [
            (ext.loc, (calc_x(text), calc_y(text)), text.get_text())
            for ext, text in match_pairs
        ]
        mean_x_off, mean_y_off = mean_vector(offset_vec)
        log.debug(f"mean_offset = {(mean_x_off, mean_y_off)}")

        for label_t in unmatched_labels:
            loc = (calc_x(label_t) - mean_x_off, calc_y(label_t) - mean_y_off)
            dist, ext = find_closest(loc, unmatched_lvs)
            old = by_lab[label_t]
            if dist > 2 * old[1]:
                # TODO make more generic. currently "not worse than twice as far..."
                continue
            by_lab[label_t] = (ext, dist)
            prev = by_ext.get(ext)
            if prev is None or (prev[0] not in unmatched_labels) or (dist < prev[-1]):
                by_ext[ext] = (label_t, dist)
        to_remove = []
        for label_t in unmatched_labels:
            ext, dist = by_lab[label_t]
            if ext not in unmatched_lvs:
                pass
            elif by_ext.get(ext, [None, None])[0] is label_t:
                log.debug(f"Offset matching: {ext} <=> {label_t.get_text().strip()}")

                matched_labels.append(label_t)
                matched_dists.append(dist)
                matched_leaves.add(ext)
                match_pairs.append((ext, label_t))
                unmatched_lvs.remove(ext)
                to_remove.append(label_t)
        for label_t in to_remove:
            unmatched_labels.remove(label_t)

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
        if self.root is None:
            return float("inf")
        s = 0.0
        for k, v in self.penalties.items():
            w = self.penalty_weights.get(k, 1.0)
            s += w * v
        return s

    def build_tree_from_tips(
        self,
        internals: List[Node],
        matched_lvs: Set[Node],
        unmatched_lvs: Set[Node],
        tip_labels: List[SafeTextLine],
        label2leaf: Dict[SafeTextLine, Tuple[Node, float]],
        unmatched_labels: List[SafeTextLine],
    ) -> Optional[PhyloNode]:
        try:
            node2phyn = self._build_adj(
                internals=internals,
                unmatched_lvs=unmatched_lvs,
                tip_labels=tip_labels,
                label2leaf=label2leaf,
            )
            root = self._root_by_position(node2phyn=node2phyn)
        except CycleDetected:
            log.exception("cycle detected in tree build_tree_from_tips")
            self.root = None
            return None

        if self.tip_dir in (Direction.EAST, Direction.WEST):
            perp_coord_leaf_list = [
                (i.y, i.x, i.eertgif_id, i) for i in root.post_order() if i.is_tip
            ]
        else:
            perp_coord_leaf_list = [
                (i.x, i.y, i.eertgif_id, i) for i in root.post_order() if i.is_tip
            ]
        perp_coord_leaf_list.sort()
        if len(perp_coord_leaf_list) > 2:
            first_tup, last_tup = perp_coord_leaf_list[0], perp_coord_leaf_list[-1]
            tot_dist = last_tup[0] - first_tup[0]
            n_tips = len(perp_coord_leaf_list)

        for leaf in unmatched_lvs:
            phynd = node2phyn[leaf]
            if phynd is not root:
                self.add_penalty(Penalty.UNMATCHED_LABELS, 1)
        root.collapse_short_internals(MIN_BR_TOL)
        self.matched_phy_leaves = set([node2phyn[i] for i in matched_lvs])
        self.unused_inline_text = set(unmatched_labels)
        return root

    def _root_by_position(self, node2phyn: Dict[Node, PhyloNode]) -> PhyloNode:
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
        internals: List[Node],
        unmatched_lvs: Set[Node],
        tip_labels: List[SafeTextLine],
        label2leaf: Dict[SafeTextLine, Tuple[Node, float]],
    ) -> Dict[Node, PhyloNode]:
        node2phyn = {}
        leaves = set()
        phy_ctx = PhyloTreeData(tip_dir=self.tip_dir, attempt=self, id_gen=self.id_gen)
        self.phy_ctx = phy_ctx
        for tl in tip_labels:
            ml = label2leaf[tl][0]
            assert ml is not None
            phynd = PhyloNode(
                vnode=ml, label_obj=tl, phy_ctx=phy_ctx, id_gen=self.id_gen
            )
            node2phyn[ml] = phynd
            leaves.add(phynd)
        int_phylo = set()
        for ul in unmatched_lvs:
            assert ul not in node2phyn
            assert ul is not None
            phynd = PhyloNode(vnode=ul, phy_ctx=phy_ctx, id_gen=self.id_gen)
            node2phyn[ul] = phynd
            leaves.add(phynd)
        for i_nd in internals:
            assert i_nd not in node2phyn
            phynd = PhyloNode(vnode=i_nd, phy_ctx=phy_ctx, id_gen=self.id_gen)
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


class MatchingStats(object):
    def __init__(self, match_pairs: List[Tuple[Node, SafeTextLine]], pma):
        self.pma = pma
        x_off, y_off = [], []
        calc_x, calc_y = pma.calc_x, pma.calc_y
        for leaf, label in match_pairs:
            x_off.append(calc_x(label) - leaf.x)
            y_off.append(calc_y(label) - leaf.y)
        m, v = mean_var(x_off)
        if v is None:
            self.x_off_mean = m
            if m is None:
                self.x_off_sd = None
            else:
                self.x_off_sd = max(
                    abs(m), 10
                )  # TODO Arbitrarily setting sd to 10 or mean.
        else:
            try:
                sv = sqrt(v)
            except:
                sv = 0.0
            self.x_off_mean, self.x_off_sd = m, sqrt(v)
        m, v = mean_var(y_off)
        if v is None:
            self.y_off_mean = m
            if m is None:
                self.y_off_sd = None
            else:
                self.y_off_sd = max(
                    abs(m), 10
                )  # TODO Arbitrarily setting sd to 10 or mean.
        else:
            try:
                sv = sqrt(v)
            except:
                sv = 0.0
            self.y_off_mean, self.y_off_sd = m, 0.0

    def score(self, leaf, label):
        calc_x, calc_y = self.pma.calc_x, self.pma.calc_y
        x_off = calc_x(label) - leaf.x
        try:
            norm_x_off = ((x_off - self.x_off_mean) / self.x_off_sd) ** 2
        except ZeroDivisionError:
            norm_x_off = 0.0
        y_off = calc_y(label) - leaf.y
        try:
            norm_y_off = ((y_off - self.y_off_mean) / self.y_off_sd) ** 2
        except ZeroDivisionError:
            norm_y_off = 0.0
        return sum([norm_x_off, norm_y_off])
