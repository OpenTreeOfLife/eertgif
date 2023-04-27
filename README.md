# eertgif

This is an experimental-stage project. 

Yet another attempt to scrape phylogenetic
trees in an interoperable format from a pdf
with an image of a tree in it.

## Install

    python3 -mvenv env
    source env/bin/activate
    pip install 'svg-path>=6.2'
    python setup.py develop

## Running (in dangerous DEBUG mode for local install only!)

    pserve dev.ini --reload


#### Credits
  * Relies heavily on [pdfminer.six](https://github.com/pdfminer/pdfminer.six)
  * See attribution in `Pt` and `PointMap` classes to Ned Batchelder's 
    [blog post](https://nedbatchelder.com/blog/201707/finding_fuzzy_floats.html)
    about a dict implementation that maps close floats to the same key
  * jQuery see https://jquery.org/license/
  * svg-drag-select https://github.com/luncheon/svg-drag-select
