#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import logging
import pickle
import sys
from threading import Lock
from typing import List, Tuple


from pdfminer.high_level import LAParams
from pdfminer.layout import LTChar, LTFigure, LTTextLine, LTTextBox, LTImage
from .graph import GraphFromEdges
from .safe_containers import UnprocessedRegion
from .util import CurveShape, DisplayMode, ExtractionConfig, Direction, AxisDir

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
    for el in fig:
        if isinstance(el, LTChar):
            char_objs.append(el)
        elif isinstance(el, LTTextBox):
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
    return (
        UnprocessedRegion(text_lines, otherobjs, fig, pdf_interpret=pdf_interpret),
        image_paths,
    )


_def_filter_shapes = {CurveShape.COMPLICATED, CurveShape.DOT}


class ExtractionManager(object):
    def __init__(self, unproc_page, extract_cfg=None):
        self._cfg = ExtractionConfig(extract_cfg)
        self.page_num = unproc_page.page_num
        self.subpage_num = unproc_page.subpage_num
        self.font_dict = dict(unproc_page.font_dict)
        self._raw_text_lines = list(unproc_page.text_lines)
        self._raw_nontext_objs = list(unproc_page.nontext_objs)
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
        self._filter()
        self._update_by_id_map()

    def set_extract_config(self, extract_cfg):
        extract_cfg = ExtractionConfig(extract_cfg, self._cfg)
        for k in ExtractionConfig.non_vs_keys:
            if k in extract_cfg:
                self._cfg[k] = copy.deepcopy(extract_cfg[k])

    @property
    def cfg(self):
        return self._cfg

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

    def as_svg_str(self):
        from .to_svg import get_svg_str

        if self.forest is None:
            return get_svg_str(obj_container=self)
        if self.best_tree is None:
            return get_svg_str(obj_container=self)

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

    def _filter(self):
        for line in self._raw_text_lines:
            self.text_lines.append(line)
        for obj in self._raw_nontext_objs:
            if obj.shape in _def_filter_shapes:
                self.trashed_nontext_objs.append(obj)
            else:
                self.nontext_objs.append(obj)

    def _new_graph(self):
        """
        Caller must update_map."""
        nm_tol = self.node_merge_tol
        self.graph = GraphFromEdges(self, node_merge_tol=nm_tol)
        first, deferred = [], []

        rect_shape = self._cfg.is_rect_shape
        target_shapes, ext_point_dir = None, None
        if rect_shape:
            orientation = self._cfg.orientation
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

            for curve in self.nontext_objs:
                dest = first if curve.shape in target_shapes else deferred
                dest.append(curve)
        else:
            first = self.nontext_objs

        fedges, dedges = [], []
        for curve in first:
            fedges.append(self.graph.add_curve(curve))
        for curve in deferred:
            dedges.append(self.graph.add_curve(curve))
        all_edges = fedges + dedges
        if not rect_shape:
            return

        for e1 in fedges:
            most_extreme = e1.most_extreme_vis_point(ext_point_dir)
            for e2 in fedges:
                if e2 is e1:
                    continue
                contains, coord = e2.axis_contains(base_axis, most_extreme, nm_tol)
                if contains:
                    self.graph.force_merge(e1, most_extreme, e2, coord)

    def detect_components(self, node_merge_tol=None, suppress_update_map=False):
        node_merge_tol = (
            node_merge_tol if node_merge_tol is not None else self.node_merge_tol
        )
        new_graph = self.graph is None or self.graph.tol != node_merge_tol
        if new_graph:
            self.node_merge_tol = node_merge_tol
            self._new_graph()
        new_forest = self.forest is None or new_graph
        if new_forest:
            self.forest = self.graph.build_forest()
        if (new_forest or new_graph) and not suppress_update_map:
            self._update_by_id_map()
        if self.display_mode == DisplayMode.CURVES_AND_TEXT:
            self.display_mode = DisplayMode.COMPONENTS

    def analyze(self):
        # build forest, but don't update map, as we'll do that after the trees are made
        self.detect_components(suppress_update_map=True)
        extra_lines = set(self.text_lines)
        best_tree, best_score = None, float("inf")
        for n, c in enumerate(self.forest.components):
            if len(c) > 4:
                tree = self.forest.interpret_as_tree(n, self.text_lines)
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
        if tree:
            print(tree.root.get_newick(self.edge_len_scaler))
        return tree


def analyze_figure(fig, params=None, extract_cfg=None):
    unproc_page = find_text_and_curves(fig, params=params)[0]
    extract_mgr = ExtractionManager(unproc_page, extract_cfg=extract_cfg)
    extract_mgr.analyze_print_and_return_tree()


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


def get_regions_unprocessed(filepath, params=None, image_writer=None):
    ur = []
    image_paths = []
    for n, pag_tup in enumerate(my_extract_pages(filepath)):
        page_layout = pag_tup[0]
        pdf_interpret = pag_tup[1]
        figures = [el for el in page_layout if isinstance(el, LTFigure)]
        if figures:
            for fn, fig in enumerate(figures):
                unproc_page, imgs = find_text_and_curves(
                    fig,
                    params=params,
                    image_writer=image_writer,
                    pdf_interpret=pdf_interpret,
                )
                image_paths.extend(imgs)
                if unproc_page.has_content:
                    unproc_page.page_num = n
                    unproc_page.subpage_num = fn
                    ur.append(unproc_page)
        else:
            # try whole page as figure container
            unproc_page, imgs = find_text_and_curves(
                page_layout,
                params=params,
                image_writer=image_writer,
                pdf_interpret=pdf_interpret,
            )
            image_paths.extend(imgs)
            if unproc_page.has_content:
                unproc_page.page_num = n
                ur.append(unproc_page)
    return ur, image_paths


def main(fp, config_fp):
    if fp == config_fp:
        ec = ExtractionConfig()
    else:
        with open(config_fp, "r") as cinp:
            obj = json.load(cinp)
        ec = ExtractionConfig(obj)
    return do_extraction(fp, extract_cfg=ec)


def do_extraction(fp, extract_cfg):
    if fp.endswith(".pdf"):
        for page_tup in my_extract_pages(fp):
            page_layout = page_tup[0]
            figures = [el for el in page_layout if isinstance(el, LTFigure)]
            if figures:
                for fig in figures:
                    analyze_figure(fig, extract_cfg=extract_cfg)
            else:
                analyze_figure(page_layout, extract_cfg=extract_cfg)
    elif fp.endswith(".pickle"):
        with open(fp, "rb") as pin:
            obj = pickle.load(pin)
        if isinstance(obj, UnprocessedRegion):
            em = ExtractionManager(obj)
        else:
            assert isinstance(obj, ExtractionManager)
            em = obj
        em.set_extract_config(extract_cfg)
        em.analyze_print_and_return_tree()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[-1])
