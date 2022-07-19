#!/usr/bin/env python3
from __future__ import annotations

import logging
from collections import namedtuple
from typing import Union

log = logging.getLogger(__name__)
################################################################################
# Code for Pt and PointMap modified from code by Ned Batchelder
#   https://nedbatchelder.com/blog/201707/finding_fuzzy_floats.html
# "I don’t have a formal license for most of this code. I post it here in the
# spirit of sharing. Use it for what you will. " https://nedbatchelder.com/code
class Pt(namedtuple("Pt", "x")):
    # no need for special __eq__ or __hash__
    pass


_ROUND_DIGITS = 6


class PointMap:
    def __init__(self, round_digits=_ROUND_DIGITS):
        self._items = {}
        self._rounded = {}
        self.round_digits = round_digits
        self.jitters = [0, 0.5 * 10 ** -round_digits]

    def _round(self, pt, jitter):
        return Pt(round(pt.x + jitter, ndigits=self.round_digits))

    def _get_impl(self, pt, default=None):
        if not isinstance(pt, Pt):
            pt = Pt(float(pt))
        if pt in self._items:
            return self._items[pt], True
        for jitter in self.jitters:
            pt_rnd = self._round(pt, jitter)
            pt0 = self._rounded.get(pt_rnd)
            if pt0 is not None:
                return self._items[pt0], True
        return default, False

    def get(self, pt: Union[int, float, Pt], default=None):
        return self._get_impl(pt, default=default)[0]

    def setdefault(self, pt: Union[int, float, Pt], default=None):
        val, was_found = self._get_impl(pt, default=default)
        if not was_found:
            self.__setitem__(pt, val)
        return val

    def __getitem__(self, pt):
        val, was_found = self._get_impl(pt)
        if not was_found:
            raise KeyError(pt)
        return val

    def __delitem__(self, pt):
        if not isinstance(pt, Pt):
            pt = Pt(float(pt))
        if pt in self._items:
            del self._items[pt]
            return
        for jitter in self.jitters:
            pt_rnd = self._round(pt, jitter)
            if pt_rnd in self._items:
                del self._items[pt_rnd]
                return
        raise KeyError(str(pt))

    def __setitem__(self, pt, val):
        if not isinstance(pt, Pt):
            pt = Pt(float(pt))
        self._items[pt] = val
        for jitter in self.jitters:
            pt_rnd = self._round(pt, jitter)
            old = self._rounded.get(pt_rnd)
            store = True
            if old is not None:
                if old.x != pt.x:
                    del self._items[old]  # rounded key clash, replace old key in items
                else:
                    store = False  # Already stored
            if store:
                self._rounded[pt_rnd] = pt

    def __iter__(self):
        return iter(self._items)

    def items(self):
        return [(k.x, v) for k, v in self._items.items()]

    def keys(self):
        return [i.x for i in self._items.keys()]

    def values(self):
        return self._items.values()


################################################################################
