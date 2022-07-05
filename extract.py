#!/usr/bin/env python3
from pdfminer.high_level import (extract_pages, LAParams, extract_text, )
from pdfminer.layout import (LTChar, LTFigure, )
from pdfminer.utils import fsplit
import sys

# Includes some code from pdfminer layout.py

VERBOSE = True
def debug(msg):
    if VERBOSE:
        sys.stderr.write("{msg}\n")


def analyze_figure(fig, params=None):
    if params is None:
        params = LAParams()
    (textobjs, otherobjs) = fsplit(lambda obj: isinstance(obj, LTChar), fig)
    textlines = list(fig.group_objects(params, textobjs))
    for line in textlines:
        print(line)
        # for char in line:
        #     print(char)
    for obj in otherobjs:
        print(obj)
def main(fp):
    params = LAParams()
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



if __name__ == '__main__':
    main(sys.argv[1])