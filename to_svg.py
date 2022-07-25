#!/usr/bin/env python3
import sys
import pickle
from eertgif.safe_containers import UnprocessedRegion
from eertgif.extract import ExtractionManager
import logging
loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict if name.startswith('eertgif')]
h = logging.StreamHandler()
h.setLevel(logging.DEBUG)
for logger in loggers:
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(h)


if __name__ == "__main__":
    fp = sys.argv[1]
    if fp.endswith(".pickle"):
        with open(fp, "rb") as pin:
            obj = pickle.load(pin)
        assert isinstance(obj, UnprocessedRegion) or isinstance(obj, ExtractionManager)
        print(obj.as_svg_str(None))
    else:
        sys.exit("Expecting the only argument to be the path to a pickle file")
