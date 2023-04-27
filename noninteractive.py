#!/usr/bin/env python3
import sys
from eertgif.extract import main

import logging

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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[-1], "images"))
