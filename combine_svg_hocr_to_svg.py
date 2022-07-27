#!/usr/bin/env python3
"""Implemented assuming potrace output."""

import sys
from html.parser import HTMLParser
from svg.path import parse_path, Move, Close, CubicBezier, Line
import logging

log = logging.getLogger("eertgif.combine")

loggers = [
    logging.getLogger(name)
    for name in logging.root.manager.loggerDict
    if name.startswith("eertgif")
]
h = logging.StreamHandler()
h.setLevel(logging.DEBUG)
for logger in loggers:
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(h)

SVG_HEADER = """<?xml version="1.0" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 20010904//EN"
 "http://www.w3.org/TR/2001/REC-SVG-20010904/DTD/svg10.dtd">
 """


def parse_dim(dim_str):
    assert dim_str.endswith("pt")
    return float(dim_str[:-2])


class HocrParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.lines = []
        self.line_bboxes = []
        self.current_line = []
        self.current_word = {}
        self.in_word = False

    def write_text(self, out_stream):
        for line in self.lines:
            for word in line:
                bbox = word["bbox"]
                x = bbox[0]
                y = (bbox[1] + bbox[3]) / 2
                length = bbox[2] - x
                height = int(bbox[3] - bbox[1] + 0.4)
                text = word.get("text", "")
                out_stream.write(
                    f'  <text x="{x}" y="{y}" textLength="{length}" textAdjust="spacingAndGlyphs" font-size="{height}px">{text}</text>\n'
                )

    def hides(self, path):
        x0, y0, x1, y1 = path.bbox
        for lbbox in self.line_bboxes:
            lx0, ly0, lx1, ly1 = lbbox
            pad = 1
            if x0 < lx0 - pad:
                continue
            if y0 < ly0 - pad:
                continue
            if x1 > lx1 + pad:
                continue
            if y1 > ly1 + pad:
                continue
            return True
        return False

    def _start_line(self):
        if self.current_line:
            self.lines.append(self.current_line)
            self.current_line = []

    def _add_word(self, att_dict):
        if self.current_word:
            self.current_line.append(self.current_word)
            self.current_word = {}
        if "bbox" in self.current_word:
            log.debug(f"c={self.current_word}  a={att_dict}")
            assert "title" not in self.current_word
        title_str = att_dict["title"]
        ts_sp = title_str.split(";")
        bbox_str = ts_sp[0]
        pref = "bbox "
        assert bbox_str.startswith(pref)
        nums = bbox_str[len(pref) :].strip()
        num_spl = nums.split(" ")
        assert len(num_spl) == 4
        self.current_word["bbox"] = [int(i) for i in num_spl]

    def handle_starttag(self, tag, attrs):
        self.in_word = False
        if tag == "span":
            adict = dict(attrs)
            sclass = adict.get("class", "")
            if sclass == "ocrx_word":
                self.in_word = True
                self._add_word(adict)
                return
            elif sclass == "ocr_line":
                self._start_line()
                return
        print(f"Skipping tag={tag} atts={attrs}")

    def handle_data(self, data):
        if self.in_word:
            self.current_word["text"] = self.current_word.get("text", "") + data

    def handle_endtag(self, tag):
        if tag == "span" and self.in_word:
            self.in_word = False
            self.current_line.append(self.current_word)
            self.current_word = {}

    def done(self):
        if self.current_word:
            self.current_line.append(self.current_word)
            self.current_word = {}
        if self.current_line:
            self.lines.append(self.current_line)
            self.current_line = []
        self.calc_line_bboxes()

    def calc_line_bboxes(self):
        self.line_bboxes = []
        for line in self.lines:
            bbox = line[0]["bbox"]
            for word in line[1:]:
                bbox = expand_bbox(bbox, word["bbox"])
            self.line_bboxes.append(bbox)

    def handle_entity_ref(self, name):
        raise ValueError(f"entity_ref={name}")


class SVGParser(HTMLParser):
    def __init__(self):
        self.width = None
        self.height = None
        self.translate_x = 0.0
        self.translate_y = 0.0
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.paths = []
        self.hidden = []
        self.svg_el_atts = None
        HTMLParser.__init__(self)

    def write_paths(self, out_stream):
        for path in self.paths:
            out_stream.write(f'  <path d="{path.d()}" />')

    def get_svg_atts_str(self):
        slist = [f'{i[0]}="{i[1]}"' for i in self.svg_el_atts]
        return " ".join(slist)

    def _parse_g_transform(self, tstr):
        tsp = tstr.split()
        assert len(tsp) == 2  # potrace  emits translate(...) scale()
        fpref = "translate("
        assert tsp[0].startswith(fpref)
        assert tsp[0].endswith(")")
        transl_pair_str = tsp[0][len(fpref) : -1]
        spref = "scale("
        assert tsp[1].startswith(spref)
        assert tsp[0].endswith(")")
        scale_pair_str = tsp[1][len(spref) : -1]
        transl_pair = transl_pair_str.split(",")
        self.translate_x = float(transl_pair[0])
        self.translate_y = float(transl_pair[1])
        scale_pair = scale_pair_str.split(",")
        self.scale_x = float(scale_pair[0])
        self.scale_y = float(scale_pair[1])

    def _transform_pt(self, pt):
        px, py = pt.real, pt.imag
        return complex(
            self.translate_x + self.scale_x * px, self.translate_y + self.scale_y * py
        )

    def _tranform_part(self, el):
        if isinstance(el, Move):
            el.start = el.end = self._transform_pt(el.start)
        elif isinstance(el, CubicBezier):
            el.start = self._transform_pt(el.start)
            el.control1 = self._transform_pt(el.control1)
            el.control2 = self._transform_pt(el.control2)
            el.end = self._transform_pt(el.end)
        elif isinstance(el, Close) or isinstance(el, Line):
            el.start = self._transform_pt(el.start)
            el.end = self._transform_pt(el.end)
        else:
            print(type(el))
            assert False

    def _tranform_path(self, path):
        for part in path:
            self._tranform_part(part)

    def transform_paths(self):
        for path in self.paths:
            self._tranform_path(path)
            # log.debug(f"path.__dict__ = {path.__dict__}")

    def _parse_path(self, d_str):
        p = parse_path(d_str)
        self.paths.append(p)

    def handle_starttag(self, tag, attrs):
        if tag == "svg":
            self.svg_el_atts = list(attrs)
            adict = dict(attrs)
            self.height = parse_dim(adict["height"])
            self.width = parse_dim(adict["width"])
            return
        if tag == "g":
            adict = dict(attrs)
            transform_str = adict.get("transform")
            if transform_str:
                self._parse_g_transform(transform_str)
            return
        if tag == "path":
            adict = dict(attrs)
            d_str = adict.get("d")
            assert d_str
            self._parse_path(d_str)
            return
        log.debug(f"Skipping tag: {tag}")


_start_bbox = (float("inf"), float("inf"), float("-inf"), float("-inf"))


def get_bb_for_el(el):
    if isinstance(el, Move):
        return [el.start.real, el.start.imag, el.start.real, el.start.imag]
    if isinstance(el, Close) or isinstance(el, Line):
        x1, x2 = el.start.real, el.end.real
        y1, y2 = el.start.imag, el.end.imag
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        return [x1, y1, x2, y2]
    if isinstance(el, CubicBezier):
        x1, x2 = el.start.real, el.end.real
        y1, y2 = el.start.imag, el.end.imag
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        for i in range(1, 50):
            pt = el.point(1 / 50.0)
            px, py = pt.real, pt.imag
            if px < x1:
                x1 = px
            elif px > x2:
                x2 = px
            if py < y1:
                y1 = py
            elif py > y2:
                y2 = py
        return [x1, y1, x2, y2]
    assert False


def expand_bbox(bb1, bb2):
    return [
        min(bb1[0], bb2[0]),
        min(bb1[1], bb2[1]),
        max(bb1[2], bb2[2]),
        max(bb1[3], bb2[3]),
    ]


def calc_bounding_box(path):
    bbox = None
    for part in path:
        nbb = get_bb_for_el(part)
        if bbox is None:
            bbox = nbb
        else:
            bbox = expand_bbox(bbox, nbb)
    path.bbox = bbox
    # print(bbox)


def main(svg_in_fp, hocr_in_fp, out_fp):
    svg_parser = SVGParser()
    with open(svg_in_fp, "r") as sinp:
        svg_parser.feed(sinp.read())
    svg_parser.transform_paths()
    for path in svg_parser.paths:
        calc_bounding_box(path)

    hocr_parser = HocrParser()
    with open(hocr_in_fp, "r") as sinp:
        hocr_parser.feed(sinp.read())
    hocr_parser.done()

    # log.debug(hocr_parser.lines)

    svg_p_copy = list(svg_parser.paths)
    idx_hidden = []
    for n, path in enumerate(svg_p_copy):
        if hocr_parser.hides(path):
            idx_hidden.append(n)
    idx_hidden.sort(reverse=True)
    for idx in idx_hidden:
        path = svg_parser.paths.pop(idx)
        svg_parser.hidden.insert(0, path)

    with open(out_fp, "w") as outp:
        outp.write(SVG_HEADER)
        atts_str = svg_parser.get_svg_atts_str()
        outp.write(f'<svg {atts_str}>\n<g fill="#000000" stroke="none">')
        svg_parser.write_paths(outp)
        outp.write("</g>\n")
        hocr_parser.write_text(outp)
        outp.write("</svg>\n")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
