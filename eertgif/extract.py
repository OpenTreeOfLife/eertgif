#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import logging
import pickle
import sys
import os
from threading import Lock
from typing import List, Tuple


from pdfminer.high_level import LAParams
from pdfminer.image import ImageWriter
from pdfminer.layout import (
    LTChar,
    LTFigure,
    LTTextLine,
    LTTextBox,
    LTImage,
    LTRect,
    LTCurve,
)
from .graph import GraphFromEdges, Node, Edge
from .safe_containers import UnprocessedRegion, SafeTextLine, SafeCurve
from .util import (
    CurveShape,
    DisplayMode,
    ExtractionConfig,
    Direction,
    AxisDir,
    orientation_to_direction,
)

log = logging.getLogger("eertgif.extract")
# Includes some code from pdfminer layout.py


_skip_types = {LTImage}


def find_text_and_curves(
    fig, params=None, image_writer=None, pdf_interpret=None
) -> Tuple[UnprocessedRegion, List[str]]:
    if params is None:
        params = LAParams()
    char_objs = []
    text_lines = []
    otherobjs = []
    image_paths = []
    figures = []
    for el in fig:
        # log.debug(f"el= {el}")
        if isinstance(el, LTChar):
            char_objs.append(el)
        elif isinstance(el, LTTextBox):
            for sel in el:
                if isinstance(sel, LTTextLine):

                    text_lines.append(sel)
                else:
                    log.debug(f"skipping element of type {type(el)} in textbox {el}")
        elif isinstance(el, LTTextLine):
            # log.debug(f"lttextline {el.bbox}")
            text_lines.append(el)
        elif isinstance(el, LTFigure):
            figures.append(el)
        elif type(el) not in _skip_types:
            if isinstance(el, LTRect):
                pass  # log.debug(f"LTRect with __dict__={el.__dict__}")
            elif not isinstance(el, LTCurve):
                pass  # log.debug(f"obj of type {type(el)} with bbox={el.bbox}")
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
    return (
        UnprocessedRegion(text_lines, otherobjs, fig, pdf_interpret=pdf_interpret),
        image_paths,
        figures,
    )


_def_filter_shapes = {CurveShape.COMPLICATED, CurveShape.DOT}


class ExtractionManager(object):
    def __init__(self, unproc_page, extract_cfg=None):
        self._cfg = ExtractionConfig(extract_cfg)
        self.force_trashed_ids = set()
        self.auto_trashed_ids = set()
        self.page_num = unproc_page.page_num
        self.subpage_num = unproc_page.subpage_num
        self.font_dict = dict(unproc_page.font_dict)
        self._raw_text_lines = list(unproc_page.text_lines)
        self._raw_nontext_objs = list(unproc_page.nontext_objs)
        if self._cfg.force_trashed_ids:
            all_lines = self._raw_text_lines + self._raw_nontext_objs
            all_ids = set([i.eertgif_id for i in all_lines])
            for tid in self._cfg.force_trashed_ids:
                if tid not in all_ids:
                    raise RuntimeError(
                        f"Unknown object id ({tid}) in force_trashed_ids"
                    )
                self.force_trashed_ids.add(tid)
        self.eertgif_id = 1 + unproc_page.eertgif_id
        self._next_e_id = 1 + self.eertgif_id
        self.id_lock = Lock()
        self.container_bbox = unproc_page.container_bbox
        self.text_lines = []
        self.nontext_objs = []
        self.trashed_text = []
        self.trashed_nontext_objs = []
        assert isinstance(self.container_bbox, tuple)
        assert len(self.container_bbox) == 4
        for el in self.container_bbox:
            assert isinstance(el, float) or isinstance(el, int)
        self.graph = None
        self.forest = None
        self.best_tree = None
        self.best_legend = None
        self._by_id = {}
        self.filter()
        self._update_by_id_map()

    def set_extract_config(self, extract_cfg):
        trashed_ids = extract_cfg.get("force_trashed_ids", [])
        log.debug(f"force_trashed_ids = {trashed_ids}")
        new_force_trashed = set()
        all_trashed = set()
        if trashed_ids:
            self._update_by_id_map()
            for tid in trashed_ids:
                try:
                    tid = int(tid)
                except:
                    pass
                obj = self._by_id.get(tid)
                if obj is None:
                    raise RuntimeError(f"Unknown id to be trashed: {tid}")
                log.debug(f"obj for {tid} = {obj}")
                if isinstance(obj, Node):
                    continue  # nodes are side effects of edge addition, so deleting a node
                    #  won't change the next detect components
                if isinstance(obj, Edge):
                    obj = obj.curve
                if isinstance(obj, SafeCurve):
                    if obj in self.nontext_objs:
                        self.nontext_objs.remove(obj)
                        if obj not in self.trashed_nontext_objs:
                            self.trashed_nontext_objs.append(obj)
                            new_force_trashed.add(obj.eertgif_id)
                    else:
                        assert obj in self.trashed_nontext_objs
                    all_trashed.add(obj.eertgif_id)
                elif isinstance(obj, SafeTextLine):
                    if obj in self.text_lines:
                        self.text_lines.remove(obj)
                        if obj not in self.trashed_text:
                            self.trashed_text.append(obj)
                            new_force_trashed.add(obj.eertgif_id)
                    else:
                        assert obj in self.trashed_text
                    all_trashed.add(obj.eertgif_id)
                else:
                    raise RuntimeError(
                        f"Unexpected attempt to trash element of type {type(obj)}"
                    )
        for auto_id in self.auto_trashed_ids:
            if auto_id in all_trashed:
                all_trashed.remove(auto_id)
        self.force_trashed_ids = all_trashed
        extract_cfg = ExtractionConfig(extract_cfg, self._cfg)
        for k in ExtractionConfig.all_keys:
            if k in extract_cfg:
                self._cfg[k] = copy.deepcopy(extract_cfg[k])
        self._cfg.force_trashed_ids = list(self.force_trashed_ids)

    @property
    def cfg(self):
        return self._cfg

    @property
    def orientation(self):
        return self._cfg.orientation

    @property
    def orientation_as_direction(self):
        return orientation_to_direction[self.orientation]

    @property
    def display_mode(self):
        return self._cfg.display_mode

    @display_mode.setter
    def display_mode(self, new_dm):
        if not isinstance(new_dm, DisplayMode):
            new_dm = DisplayMode(new_dm)
        self._cfg.display_mode = new_dm

    @property
    def node_merge_tol(self):
        return self._cfg.node_merge_tol

    @property
    def is_rect_shape(self):
        return self._cfg.is_rect_shape

    @property
    def rect_base_intercept_tol(self):
        return self._cfg.rect_base_intercept_tol

    @node_merge_tol.setter
    def node_merge_tol(self, new_node_merge_tol):
        if (
            not (
                isinstance(new_node_merge_tol, float)
                or isinstance(new_node_merge_tol, int)
            )
            or new_node_merge_tol < 0
        ):
            raise ValueError("node_merge_tol must be positive")
        self._cfg.node_merge_tol = new_node_merge_tol

    def iter_nodes(self):
        g = self.graph
        if g is None:
            return iter([])
        return g.iter_nodes()

    def create_pairings(self):
        if self.best_tree is None:
            return {}
        pairing_obj = {}
        for leaf_nd in self.best_tree.matched_phy_leaves:
            text_id = str(leaf_nd.label_obj.eertgif_id)
            node_id = str(leaf_nd.vnode.eertgif_id)
            if leaf_nd.orig_vedge_to_par is not None:
                edge = leaf_nd.orig_vedge_to_par
                edge_id = str(edge.eertgif_id)
                curve_id = str(edge.curve.eertgif_id)
                pairing_obj[text_id] = [node_id, edge_id, curve_id]
                pairing_obj[node_id] = [text_id, edge_id]
                pairing_obj[edge_id] = [text_id, node_id]
                log.debug(
                    f"pairing text={text_id}, node={node_id}, edge={edge_id}, curve={curve_id}"
                )
            else:
                pairing_obj[text_id] = [node_id]
                pairing_obj[node_id] = [text_id]
        return pairing_obj

    def as_svg_str(self, pairings=None):
        from .to_svg import get_svg_str

        if pairings is None:
            pairings = self.create_pairings()
        return get_svg_str(obj_container=self, pairings=pairings)

    def _update_by_id_map(self):
        m = {}
        for top_list in [
            self._raw_text_lines,
            self._raw_nontext_objs,
            [self.graph, self.forest],
        ]:
            for el in top_list:
                if el is not None:
                    m[el.eertgif_id] = el
        if self.graph is not None:
            m[self.graph.nodes.eertgif_id] = self.graph.nodes
        if self.forest is not None:
            f = self.forest
            for c in f.components:
                # record all the nodes and edges
                for nd in c:
                    m[nd.eertgif_id] = nd
                    for e in nd.edges:
                        m[e.eertgif_id] = e
                # record all the PhyloTrees
                for t in f.trees:
                    if t is None:
                        continue
                    m[t.eertgif_id] = t
                    pma = t.pma
                    if pma:
                        m[pma.eertgif_id] = pma
                        if pma.phy_ctx:
                            m[pma.phy_ctx.eertgif_id] = pma.phy_ctx
                    for phynd in t.post_order():
                        m[phynd.eertgif_id] = phynd
                for leg in f.legends:
                    if leg is not None:
                        m[leg.eertgif_id] = leg
        self._by_id = m

    @staticmethod
    def unpickle(in_stream):
        o = pickle.load(in_stream)
        assert isinstance(o, ExtractionManager)
        o.post_unpickle()
        return o

    def post_unpickle(self):
        self.id_lock = Lock()
        self._update_by_id_map()

    def pickle(self, out_stream):
        d = self._by_id
        lock = self.id_lock
        try:
            self._by_id = {}
            self.id_lock = None
            pickle.dump(self, out_stream, protocol=pickle.HIGHEST_PROTOCOL)
        finally:
            self._by_id = d
            self.id_lock = lock

    def get_new_id(self):
        with self.id_lock:
            i = self._next_e_id
            self._next_e_id += 1
        return i

    def filter(self):
        auto_trashed_ids = set()
        tl = []
        ttl = []
        for line in self._raw_text_lines:
            if line.eertgif_id in self.force_trashed_ids:
                ttl.append(line)
            else:
                tl.append(line)
        tn, no = [], []
        for obj in self._raw_nontext_objs:
            trash = obj.shape in _def_filter_shapes
            if trash:
                # log.debug(f"filtering out {obj.__dict__}")
                # if obj.eertgif_id == 329:
                #    obj._diagnose_shape()
                auto_trashed_ids.add(obj.eertgif_id)
                tn.append(obj)
            elif obj.eertgif_id in self.force_trashed_ids:
                tn.append(obj)
            else:
                no.append(obj)
        changed = False
        if tl != self.text_lines:
            self.text_lines[:] = tl
            changed = True
        if ttl != self.trashed_text:
            self.trashed_text[:] = ttl
            changed = True
        if no != self.nontext_objs:
            changed = True
            self.nontext_objs[:] = no
        if tn != self.trashed_nontext_objs:
            changed = True
            self.trashed_nontext_objs[:] = tn
        if auto_trashed_ids != self.auto_trashed_ids:
            self.auto_trashed_ids.clear()
            self.auto_trashed_ids.update(auto_trashed_ids)
            changed = True
        return changed

    def _new_graph(self):
        """
        Caller must update_map."""
        self.graph = GraphFromEdges(self, node_merge_tol=self.node_merge_tol)
        for curve in self.nontext_objs:
            self.graph.add_curve(curve)
        log.debug(
            f"graph with {len(self.graph.nodes._all_nodes)} nodes and {len(self.graph.edges)} edges created."
        )

    def merge_component_using_rect_shape_joins(self):
        mergeable = self._find_mergeable_components_rect()
        for tup in mergeable:
            e1, most_extreme, e2, coord = tup[2:]
            if e1.component_idx == e2.component_idx:
                continue
            c1_idx = e1.component_idx
            c2_idx = e2.component_idx
            self.graph.force_merge(e1, most_extreme, e2, coord)
            self.forest._post_merge_hook(c1_idx, c2_idx)

    def _find_mergeable_components_rect(self):
        target_shapes, ext_point_dir = None, None
        nm_tol = self.rect_base_intercept_tol
        orientation = self.orientation
        if orientation == "right":
            target_shapes = {CurveShape.CORNER_LL, CurveShape.CORNER_UL}
            ext_point_dir = Direction.EAST
            base_axis = AxisDir.VERTICAL
        elif orientation == "left":
            target_shapes = {CurveShape.CORNER_LR, CurveShape.CORNER_UR}
            ext_point_dir = Direction.WEST
            base_axis = AxisDir.VERTICAL
        elif orientation == "down":
            target_shapes = {CurveShape.CORNER_UL, CurveShape.CORNER_UR}
            ext_point_dir = Direction.SOUTH
            base_axis = AxisDir.HORIZONTAL
        else:
            assert orientation == "up"
            target_shapes = {CurveShape.CORNER_LL, CurveShape.CORNER_LR}
            ext_point_dir = Direction.NORTH
            base_axis = AxisDir.HORIZONTAL

        edges = self.graph.edges
        mergeable = []
        for e1 in edges:
            comp_idx = e1.component_idx
            most_extreme = e1.most_extreme_vis_point(ext_point_dir)
            for e2 in edges:
                if e2 is e1:
                    continue
                if e2.component_idx == comp_idx:
                    continue

                contains, coord, dist = e2.axis_contains(
                    base_axis, most_extreme, nm_tol
                )

                if contains:
                    log.debug(
                        f"  mergeable {(dist, e1.eertgif_id, e1, most_extreme, e2, coord)}"
                    )
                    mergeable.append((dist, e1.eertgif_id, e1, most_extreme, e2, coord))
                else:
                    log.debug(f"  unmergeable {e1} and {e2}")

        mergeable.sort()
        return mergeable

    def clear_trees(self):
        self.best_tree, self.best_legend = None, None
        self.display_mode = DisplayMode.COMPONENTS
        if self.forest:
            self.forest.clear_trees()

    def detect_components(
        self, node_merge_tol=None, suppress_update_map=False, suppress_filter=False
    ):
        self.clear_trees()
        if not suppress_filter:
            filter_changed = self.filter()
        else:
            filter_changed = False
        # id_list = [i.eertgif_id for i in self.text_lines]
        # assert 136 not in id_list
        # assert 126 not in id_list
        # assert 123 not in id_list

        node_merge_tol = (
            node_merge_tol if node_merge_tol is not None else self.node_merge_tol
        )
        new_graph = (
            True
            or (self.graph is None)
            or (self.graph.tol != node_merge_tol)
            or filter_changed
        )
        if new_graph:
            self._new_graph()
        new_forest = True
        self.forest = self.graph.build_forest()
        log.debug(f"{len(self.forest.components)} components detected")
        if self.is_rect_shape:
            rbit = self._cfg["rect_base_intercept_tol"]
            if (
                self.forest.rect_base_intercept_tol is None
                or self.forest.rect_base_intercept_tol != rbit
            ):
                self.merge_component_using_rect_shape_joins()

        if (new_forest or new_graph) and not suppress_update_map:
            self._update_by_id_map()
        if self.display_mode == DisplayMode.CURVES_AND_TEXT:
            self.display_mode = DisplayMode.COMPONENTS

    def extract_trees(self):
        return self.analyze()

    def analyze(self):
        # build forest, but don't update map, as we'll do that after the trees are made
        self.detect_components(suppress_update_map=True)
        extra_lines = set(self.text_lines)
        best_tree, best_score = None, float("inf")

        # id_list = [i.eertgif_id for i in self.text_lines]
        # assert 136 not in id_list
        # assert 126 not in id_list
        # assert 123 not in id_list

        for n, c in enumerate(self.forest.components):
            if len(c) > 4:
                tree = self.forest.interpret_as_tree(
                    n, self.text_lines, self.orientation_as_direction
                )
                score = tree.score
                if score < best_score:
                    best_score = score
                    best_tree = tree
                extra_lines = extra_lines.difference(tree.used_text)

        self.best_tree = best_tree
        self.best_legend = None
        if not best_tree:
            self._update_by_id_map()
            return None
        self.display_mode = DisplayMode.PHYLO
        pma = best_tree.attempt
        best_legend, best_leg_score = None, float("inf")
        for n, c in enumerate(self.forest.components):
            if len(c) <= 4:
                legend = self.forest.interpret_as_legend(n, pma.unused_text)
                if (legend is not None) and (legend.score < best_leg_score):
                    best_leg_score = legend.score
                    best_legend = legend
        self.best_legend = best_legend
        best_tree.clean_for_export()
        self._update_by_id_map()
        return self.best_tree

    @property
    def edge_len_scaler(self):
        if self.best_legend is not None:
            return self.best_legend.edge_len_scaler
        return None

    def analyze_print_and_return_tree(self):
        tree = self.analyze()
        if tree is None:
            log.debug("tree from analyze is None")
        else:
            print(tree.root.get_newick(self.edge_len_scaler))
        return tree


def print_and_return_tree(extract_cfg, unproc_page):
    extract_mgr = ExtractionManager(unproc_page, extract_cfg=extract_cfg)
    return extract_mgr.analyze_print_and_return_tree()


def my_extract_pages(pdf_file, page_numbers=None):
    """Extract and yield (LTPage, interpreter, device, resource_mgr) tuples

    Tweak of pdfminer.six version to the PDFResourceManagerToo
    """
    laparams = LAParams()
    maxpages = 0
    password = ""
    caching = True
    from pdfminer.high_level import (
        open_filename,
        cast,
        BinaryIO,
        PDFResourceManager,
        PDFPageAggregator,
        PDFPageInterpreter,
        PDFPage,
    )

    with open_filename(pdf_file, "rb") as fp:
        fp = cast(BinaryIO, fp)  # we opened in binary mode
        resource_manager = PDFResourceManager(caching=caching)
        device = PDFPageAggregator(resource_manager, laparams=laparams)
        interpreter = PDFPageInterpreter(resource_manager, device)
        for page in PDFPage.get_pages(
            fp, page_numbers, maxpages=maxpages, password=password, caching=caching
        ):
            interpreter.process_page(page)
            layout = device.get_result()
            yield layout, interpreter, device, resource_manager


def _process_figures(
    ur, image_paths, figures, params, image_writer, pdf_interpret, n, prev_fn
):
    subfigures = []
    subpage_n = prev_fn
    for fn, fig in enumerate(figures):
        unproc_page, imgs, subfig_list = find_text_and_curves(
            fig, params=params, image_writer=image_writer, pdf_interpret=pdf_interpret
        )
        image_paths.extend(imgs)
        subpage_n += 1
        if unproc_page.has_content:
            unproc_page.page_num = n
            unproc_page.subpage_num = fn + subpage_n
            ur.append(unproc_page)
            log.debug(
                f"Added UnprocessedRegion {unproc_page.tag} n={n} subpage_n={subpage_n} fn={fn} prev_fn={prev_fn}"
            )
        subfigures.extend(subfig_list)

    return subfigures, subpage_n


def get_regions_unprocessed(filepath, params=None, image_writer=None):
    ur, image_paths = [], []
    for n, pag_tup in enumerate(my_extract_pages(filepath)):
        page_layout = pag_tup[0]
        pdf_interpret = pag_tup[1]
        figures = [page_layout]
        prev_fn = -1  # pre-increment will cause first to be 0
        subfigures = []
        while figures:
            subfigures, prev_fn = _process_figures(
                ur,
                image_paths,
                figures,
                params,
                image_writer,
                pdf_interpret,
                n,
                prev_fn,
            )
            figures = subfigures
    return ur, image_paths


def do_extraction(fp, extract_cfg, image_writer=None):
    rc = 1
    if fp.endswith(".pdf"):
        ur, images = get_regions_unprocessed(fp, image_writer=image_writer)
        for region in ur:
            tree = print_and_return_tree(extract_cfg, region)
            if tree:
                rc = 0
    elif fp.endswith(".pickle"):
        with open(fp, "rb") as pin:
            obj = pickle.load(pin)
        if isinstance(obj, UnprocessedRegion):
            em = ExtractionManager(obj)
        else:
            assert isinstance(obj, ExtractionManager)
            with open(fp, "rb") as pin:
                em = ExtractionManager.unpickle(pin)
        em.set_extract_config(extract_cfg)
        if em.analyze_print_and_return_tree() is not None:
            rc = 0
    return rc


def main(fp, config_fp, image_dir=None):
    if image_dir:
        if not os.path.isdir(image_dir):
            os.makedirs(image_dir)
        iw = ImageWriter(image_dir)
    else:
        iw = None
    if fp == config_fp:
        ec = ExtractionConfig()
    else:
        with open(config_fp, "r") as cinp:
            obj = json.load(cinp)
        ec = ExtractionConfig(obj)
    return do_extraction(fp, extract_cfg=ec, image_writer=iw)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[-1])
