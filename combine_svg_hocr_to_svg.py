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


def parse_dim(dim_str):
    assert dim_str.endswith("pt")
    return float(dim_str[:-2])


class HocrParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)

    def handle_starttag(self, tag, attrs):
        if tag == "span":
            adict = dict(attrs)
            sclass = adict.get("class", "")
            if sclass == "ocr_line":
                self._start_line()
            elif sclass == "ocr_word":
                self._add_word(tag)

        print(f"Skipping tag={tag}")


class SVGParser(HTMLParser):
    def __init__(self):
        self.width = None
        self.height = None
        self.translate_x = 0.0
        self.translate_y = 0.0
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.paths = []
        HTMLParser.__init__(self)

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


def main(svg_in_fp, hocr_in_fp, out_fp):
    svg_parser = SVGParser()
    with open(svg_in_fp, "r") as sinp:
        svg_parser.feed(sinp.read())
    svg_parser.transform_paths()

    hocr_parser = HocrParser()
    with open(hocr_in_fp, "r") as sinp:
        hocr_parser.feed(sinp.read())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
