#!/usr/bin/env python3
import logging
import os
import pickle
from typing import Optional

log = logging.getLogger("eertgif.study_container")


class RegionStatus:
    UNKNOWN = "unknown"
    NO_TREES = "no trees"
    all_values = (UNKNOWN, NO_TREES)

    @staticmethod
    def validate(s):
        sl = s.lower()
        for v in RegionStatus.all_values:
            if v == sl:
                return v
        return None


class StudyContainer(object):
    """Caller of methods must obtain lock, first."""

    def __init__(self, info_blob, par_dir):
        self.blob = info_blob
        self.par_dir = par_dir
        self._page_ids = None
        self._image_ids = None
        self._page_status_list = []
        self._page_status_list = self.blob.setdefault(
            "page_status_list", self.page_status_list
        )
        self._obj_for_regions = None

    @property
    def pickles_names(self):
        return self.blob.get("unprocessed", [])

    @property
    def all_file_paths(self):
        return self.blob.get("to_clean", [])

    @property
    def page_ids(self):
        if self._page_ids is None:
            lensuf = len(".pickle")
            self._page_ids = [i[:-lensuf] for i in self.pickles_names]
            # TODO page status diagnosis?
            npi = len(self._page_ids)
            if not self._page_status_list:
                x = [RegionStatus.UNKNOWN] * npi
                self._page_status_list[:] = x
            self._obj_for_regions = [None] * npi
        return self._page_ids

    @property
    def image_ids(self):
        if self._image_ids is None:
            ipath = f"{os.sep}img{os.sep}"
            self._image_ids = [
                os.path.split(i)[-1] for i in self.all_file_paths if ipath in i
            ]
        return self._image_ids

    @property
    def page_status_list(self):
        if self._page_status_list is None:
            x = self.page_ids  # side effect of filling page_ids
        return self._page_status_list

    def object_for_region(self, idx):
        pg_id = self.page_ids[idx]  # side effect of filling page_ids
        o = self._obj_for_regions[idx]
        if o is None:
            pickle_path = self.path_to_pickle(pg_id)
            if not pickle_path:
                msg = f"Could not find storage for page/region {pg_id}"
                log.exception(msg)
                raise RuntimeError(msg)
            try:
                with open(pickle_path, "rb") as pinp:
                    o = pickle.load(pinp)
            except:
                msg = f"Error unpacking storage for page/region {pg_id}"
                log.exception(msg)
                raise RuntimeError(msg)
            self._obj_for_regions[idx] = o
        return o

    def path_to_image(self, img_id) -> Optional[str]:
        suffix = f"{os.sep}img{os.sep}{img_id}"
        for i in self.all_file_paths:
            if i.endswith(suffix):
                return i
        return None

    def path_to_pickle(self, pg_id) -> Optional[str]:
        suffix = f"{os.sep}{pg_id}.pickle"
        for i in self.all_file_paths:
            if i.endswith(suffix):
                return i
        return None

    def index_for_page_id(self, page_id):
        try:
            return self.page_ids.index(page_id)
        except:
            return None
