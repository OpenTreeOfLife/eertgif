#!/usr/bin/env python3
from __future__ import annotations

import logging
import sys
from typing import List, Tuple
from threading import Lock
import pickle

from pdfminer.high_level import LAParams
from pdfminer.layout import LTChar, LTFigure, LTCurve, LTTextLine, LTTextBox, LTImage
from .to_svg import to_html
from .graph import GraphFromEdges
from .util import CurveShape, DisplayMode
from .safe_containers import UnprocessedRegion, SafeCurve

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
    def __init__(self, unproc_page):
        self.display_mode = DisplayMode.CURVES_AND_TEXT
        self.node_merge_tol = 0.01
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

    @staticmethod
    def unpickle(self, in_stream):
        o = pickle.load(pinp)
        assert isinstance(o, ExtractionManager)
        o.id_lock = Lock()
        o._update_by_id_map()

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

    def pickle(self, out_stream):
        d = self._by_id
        l = self.id_lock
        try:
            self._by_id = {}
            self.id_lock = None
            pickle.dump(ur, f_out, protocol=pickle.HIGHEST_PROTOCOL)
        finally:
            self._by_id = d
            self.id_lock = l

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

    def detect_components(self, node_merge_tol=None, suppress_update_map=False):
        node_merge_tol = (
            node_merge_tol if node_merge_tol is not None else self.node_merge_tol
        )
        new_graph = self.graph is None or self.graph.tol != node_merge_tol
        if new_graph:
            self.node_merge_tol = node_merge_tol
            self.graph = GraphFromEdges(self, node_merge_tol=self.node_merge_tol)
            for curve in self.nontext_objs:
                self.graph.add_curve(curve)
        new_forest = self.forest is None or new_graph
        if new_forest:
            self.forest = self.graph.build_forest()
        if (new_forest or new_graph) and not suppress_update_map:
            self._update_by_id_map()
        if self.display_mode == DisplayMode.CURVES_AND_TEXT:
            self.display_mode = DisplayMode.COMPONENTS

    def analyze(self, node_merge_tol=None):
        # build forest, but don't update map, as we'll do that after the trees are made
        self.detect_components(node_merge_tol=node_merge_tol, suppress_update_map=True)
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


def analyze_figure(fig, params=None):
    unproc_page = find_text_and_curves(fig, params=params)[0]
    extract_mgr = ExtractionManager(unproc_page)
    tree = extract_mgr.analyze()
    if tree:
        print(tree.root.get_newick(extract_mgr.edge_len_scaler))
    return tree


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


def main(fp):
    for page_tup in my_extract_pages(fp):
        page_layout = page_tup[0]
        figures = [el for el in page_layout if isinstance(el, LTFigure)]
        if figures:
            for fig in figures:
                analyze_figure(fig)
        else:
            analyze_figure(page_layout)


if __name__ == "__main__":
    main(sys.argv[1])
