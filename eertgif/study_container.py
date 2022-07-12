#!/usr/bin/env python3
from pyramid.response import Response
from pyramid.httpexceptions import HTTPConflict, HTTPBadRequest, HTTPFound, HTTPNotFound
from typing import Optional
from pyramid.view import view_config
import os
import re
import logging
import json
import tempfile
import pickle
from threading import Lock
import shutil
from .extract import get_regions_unprocessed
from pdfminer.image import ImageWriter

log = logging.getLogger("eertgif.study_container")


class StudyContainer(object):
    """Caller of methods must obtain lock, first."""

    def __init__(self, info_blob, par_dir):
        self.blob = info_blob
        self.par_dir = par_dir
        self._page_ids = None
        self._image_ids = None
        self._page_status_list = None

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
            self._page_status_list = ["unknown"] * len(self._page_ids)
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

    def path_to_image(self, img_id) -> Optional[str]:
        suffix = f"{os.sep}img{os.sep}{img_id}"
        for i in self.all_file_paths:
            if i.endswith(suffix):
                return i
        return None
