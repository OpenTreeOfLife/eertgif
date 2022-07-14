#!/usr/bin/env python3
from __future__ import annotations

import logging
import sys
from typing import List, Tuple

from pdfminer.high_level import LAParams
from pdfminer.layout import LTChar, LTFigure, LTCurve, LTTextLine, LTTextBox, LTImage
from .to_svg import to_html
from .graph import GraphFromEdges
from .safe_containers import UnprocessedRegion, SafeCurve

log = logging.getLogger("eertgif.extract")
# Includes some code from pdfminer layout.py


def _analyze_text_and_curves(text_lines, curves):
    graph = GraphFromEdges()
    for curve in curves:
        graph.add_curve(curve)
    forest = graph.build_forest()
    extra_lines = set(text_lines)
    best_tree, best_score = None, float("inf")
    for n, c in enumerate(forest.components):
        if len(c) > 4:
            tree = forest.interpret_as_tree(n, text_lines)
            score = tree.score
            if score < best_score:
                best_score = score
                best_tree = tree
            extra_lines = extra_lines.difference(tree.used_text)
    if not best_tree:
        return
    pma = best_tree.attempt
    best_legend, best_leg_score = None, float("inf")
    for n, c in enumerate(forest.components):
        if len(c) <= 4:
            legend = forest.interpret_as_legend(n, pma.unused_text)
            if (legend is not None) and (legend.score < best_leg_score):
                best_leg_score = legend.score
                best_legend = legend
    edge_len_scaler = None
    if best_legend:
        edge_len_scaler = best_legend.edge_len_scaler
    best_tree.clean_for_export()
    print(best_tree.root.get_newick(edge_len_scaler))


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


def filter_text_and_curves(text_lines, otherobjs):
    ftl, fc = [], []
    for line in text_lines:
        ftl.append(line)
    for obj in otherobjs:
        if isinstance(obj, SafeCurve):
            if len(obj.pts) > 5:
                log.debug(f"ignoring curve with too many points: {obj}, {obj.__dict__}")
                continue
            elif len(obj.pts) < 2:
                log.debug(f"ignoring curve with too few points: {obj}, {obj.__dict__}")
                continue
            fc.append(obj)
            # print(f"curve from {obj.pts[0]} to {obj.pts[-1]}")
        else:
            print("Unknown", obj, obj.__dict__)
    return ftl, fc


def analyze_figure(fig, params=None):
    unproc_page = find_text_and_curves(fig, params=params)[0]
    ftl, fc = filter_text_and_curves(unproc_page.text_lines, unproc_page.nontext_objs)
    return _analyze_text_and_curves(ftl, fc)


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
    # params = LAParams()
    for page_tup in my_extract_pages(fp):
        page_layout = page_tup[0]
        figures = [el for el in page_layout if isinstance(el, LTFigure)]
        if figures:
            for fig in figures:
                analyze_figure(fig)
        else:
            # try whole page as figure container
            analyze_figure(page_layout)
        # for element in page_layout:
        #     if isinstance(element, LTFigure):
        #         analyze_figure(element)
        #     else:
        #         debug(f"Skipping non-figure {element}")
        # for sub in element:
        #
        #     try:
        #         for subsub in sub:
        #             print(f"    subsub = {subsub}")
        #     except TypeError:
        #         pass


if __name__ == "__main__":
    main(sys.argv[1])
