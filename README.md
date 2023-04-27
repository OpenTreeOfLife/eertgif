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

### Developer notes

#### home page
  * Uploading a pdf will create a tmp directory in the server's scratch directory. You can clear the contents of the scratch directory and restart the server to throw away old downloads.
  * an `info.json` file in the temp directory holds the "state" of the project. (see below)

#### `info.json`
A JSON serialization object with properties:

  * `page_status_list` list for each region of either {"no trees" | "unknown" }
  * `tag` holds the "nickname" that will be shown to the user and in URLs
  * `to_clean` list of filepaths (relative to the top of the repo) to be removed if the use removes the project.
  * `unprocessed` a list of pickled object for each region found in the pdf. See `object_for_region` method for the `StudyContainer`


#### Credits
  * Relies heavily on [pdfminer.six](https://github.com/pdfminer/pdfminer.six)
  * See attribution in `Pt` and `PointMap` classes to Ned Batchelder's 
    [blog post](https://nedbatchelder.com/blog/201707/finding_fuzzy_floats.html)
    about a dict implementation that maps close floats to the same key
  * jQuery see https://jquery.org/license/
  * svg-drag-select https://github.com/luncheon/svg-drag-select
