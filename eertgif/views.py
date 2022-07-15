#!/usr/bin/env python3
import json
import logging
import os
import pickle
import re
import shutil
import tempfile
from threading import Lock

from pyramid.httpexceptions import HTTPConflict, HTTPBadRequest, HTTPFound, HTTPNotFound
from pyramid.view import view_config

from pdfminer.image import ImageWriter
from .extract import get_regions_unprocessed, UnprocessedRegion, ExtractionManager
from .study_container import StudyContainer, RegionStatus

log = logging.getLogger("eertgif")

# _uploads is a global list of lists, each contained
#   list holds:
#       [tag str, shared_list]
#   where shared_list holds:
#       [blob dict, dir_for_this_upload, lock, top_container]
#   and shared_list is also stored in _uploads_by_tag
# Use scan_for_uploads to refresh the _uploads
#   global.
_uploads = []
_uploads_by_tag = {}
_upload_lock = Lock()
_up_dir = None

_info_fn = "info.json"
_tag_pat = re.compile(r"^[ a-zA-Z0-9]+$")


def _find_uploads(uploads_dir):
    found_uploads = []
    for i in os.listdir(uploads_dir):
        fp = os.path.join(uploads_dir, i)
        if not os.path.isdir(fp):
            log.debug(f"Skipping non-directory {i}")
            continue
        ifp = os.path.join(fp, _info_fn)
        try:
            with open(ifp, "r", encoding="utf-8") as inp:
                blob = json.load(inp)
            assert "tag" in blob
        except FileNotFoundError:
            log.debug(f"Skipping {fp} for lack of {_info_fn}")
        except:
            log.debug(f"Did not find a info blob with 'tag' at {ifp}")
        else:
            found_uploads.append([blob["tag"], [blob, fp, None, None]])
    return found_uploads


def _lock_held_udict_from_list():
    """Fills _uploads_by_tag from _uploads. Caller must hold _upload_lock !

    fills _uploads_by_tag """
    d = dict(_uploads_by_tag)
    _uploads_by_tag.clear()
    for u in _uploads:
        tag, shared_list = u
        prev = d.get(tag)
        if prev is None:
            lock = shared_list[2]
            if lock is None:
                lock = Lock()
                shared_list[2] = lock
            _uploads_by_tag[tag] = shared_list
        else:
            _uploads_by_tag[tag] = prev
    return _uploads, _uploads_by_tag


def force_add_upload_dir(tag, dest_dir):
    """Returns the study lock."""
    with _upload_lock:
        nl = Lock()
        shared_list = [{}, dest_dir, nl, None]
        _uploads.append([tag, shared_list])
        _lock_held_udict_from_list()
    return shared_list


def scan_for_uploads(uploads_dir):
    global _uploads, _up_dir
    found_uploads = _find_uploads(uploads_dir)
    with _upload_lock:
        _uploads[:] = found_uploads[:]  # replace contents
        _up_dir = uploads_dir
        _lock_held_udict_from_list()
        u, bt = _uploads, _uploads_by_tag
    return u, bt


class EertgifView:
    def __init__(self, request):
        log.debug(f"{request.url} called")
        self.request = request
        settings = self.request.registry.settings
        self.uploads_dir = settings.get("uploads.dir", "scratch")
        self.debug_mode = settings.get("debug_mode", False)

    def _uploads(self):
        """Returns a list of a shallow copy of _uploads, and _uploads_by_tag"""
        with _upload_lock:
            u = list(_uploads)
            bt = dict(_uploads_by_tag)
        if not u:
            tup = scan_for_uploads(self.uploads_dir)
            u = list(tup[0])
            bt = dict(tup[1])
        return u, bt

    def _get_shared_list_for_upload(self, tag):
        ubt = self._uploads()[1]
        r = ubt.get(tag)
        if r is None:  # Force scan
            tup = scan_for_uploads(self.uploads_dir)
            ubt = dict(tup[1])
            r = ubt.get(tag)
        if r is None:
            raise HTTPNotFound(f'unknown upload "{tag}"')
        return r

    def _get_lock_and_top(self, tag):
        shared_list = self._get_shared_list_for_upload(tag)
        info_blob, tmp_dir, study_lock, top_cont = shared_list
        if top_cont is None:
            with study_lock:
                top_cont = shared_list[-1]
                if top_cont is None:
                    top_cont = StudyContainer(info_blob, tmp_dir)
                    shared_list[-1] = top_cont
        return study_lock, top_cont

    @view_config(route_name="eertgif:home", renderer="templates/home.pt")
    def home_view(self):
        u = self._uploads()[0]
        tags = [i[0] for i in u]
        return {"tags": tags}

    @view_config(route_name="eertgif:about", renderer="templates/about.pt")
    def about_view(self):
        return {"name": "About View"}

    def _get_tag_and_mandatory_page_id(self):
        tag = self.request.matchdict["tag"]
        page_id = self.request.params.get("page")
        if page_id is None:
            return HTTPBadRequest('"page" query parameter required.')
        return tag, page_id

    @view_config(route_name="eertgif:set_status")
    def set_status_view(self):
        tag, page_id = self._get_tag_and_mandatory_page_id()
        status = self.request.params.get("status")
        if status is None:
            return HTTPBadRequest('"status" query parameter required.')
        validated_stat = RegionStatus.validate(status)
        if validated_stat is None:
            return HTTPBadRequest(f'"{status}" is not a valid value for status')
        study_lock, top_cont = self._get_lock_and_top(tag)
        with study_lock:
            idx = top_cont.index_for_page_id(page_id)
            if idx is None:
                return HTTPNotFound(f"Region/Page {page_id} in {tag} does not exist.")
            top_cont.page_status_list[idx] = validated_stat
        return HTTPFound(f"/view/{tag}?page={page_id}")

    @view_config(route_name="eertgif:extract", renderer="templates/extract.pt")
    def extract_view(self):
        tag, page_id = self._get_tag_and_mandatory_page_id()
        study_lock, top_cont = self._get_lock_and_top(tag)
        with study_lock:
            pages = list(top_cont.page_ids)
            idx = top_cont.index_for_page_id(page_id)
            page_status = list(top_cont.page_status_list)
        if idx is None:
            return HTTPNotFound(f"Region/Page {page_id} in {tag} does not exist.")
        page = pages[idx]
        status = page_status[idx]
        if status == RegionStatus.NO_TREES:
            return HTTPBadRequest(
                "Cannot call extract on a page/region that is marked as having no trees."
            )
        with study_lock:
            try:
                obj_for_region = top_cont.object_for_region(idx)
            except RuntimeError as x:
                log.exception("exception -> HTTPConflict")
                return HTTPConflict(
                    "Unknown error, please report this and the eertgif.log to developers"
                )
            if isinstance(obj_for_region, UnprocessedRegion):
                em = ExtractionManager(obj_for_region)
                top_cont.set_object_for_region(idx, em)
            else:
                assert isinstance(obj_for_region, ExtractionManager)
                em = obj_for_region
        svg = em.as_svg_str()
        d = {
            "tag": tag,
            "region_id": page_id,
            "svg": svg,
            "status": status,
            "node_merge_tol": em.node_merge_tol,
        }
        return d

    @view_config(route_name="eertgif:view", renderer="templates/view.pt")
    def edit_view(self):
        tag = self.request.matchdict["tag"]
        page_id = self.request.params.get("page")
        study_lock, top_cont = self._get_lock_and_top(tag)
        with study_lock:
            pages = list(top_cont.page_ids)
            images = list(top_cont.image_ids)
            page_status = list(top_cont.page_status_list)
        pages = [(i, page_status[n]) for n, i in enumerate(pages)]
        single_item = False
        next_region_id = None
        prev_region_id = None
        svg = None
        status = RegionStatus.UNKNOWN
        if page_id is not None:
            p = None
            idx = None
            for n, page_tup in enumerate(pages):
                if page_tup[0] == page_id:
                    p = page_tup
                    idx = n
                    break
            if p is None:
                return HTTPNotFound(f"Region/Page {page_id} in {tag} does not exist.")
            next_region_id = None if idx == (len(pages) - 1) else pages[idx + 1][0]
            prev_region_id = None if idx == 0 else pages[idx - 1][0]
            pages = [p]
            images = []
            status = page_status[idx]
            single_item = True
            if status != RegionStatus.NO_TREES:
                try:
                    with study_lock:
                        obj_for_region = top_cont.object_for_region(idx)
                    assert isinstance(obj_for_region, UnprocessedRegion) or isinstance(
                        obj_for_region, ExtractionManager
                    )
                except:
                    log.exception("exception -> HTTPConflict")
                    return HTTPConflict(
                        "Unknown error, please report this and the relevant parts of eertgif.log to developers"
                    )
                svg = obj_for_region.as_svg_str()
        else:
            if len(pages) > 1:
                next_region_id = pages[0][0]

        d = {
            "tag": tag,
            "pages": pages,
            "images": images,
            "single_item": single_item,
            "next_region_id": next_region_id,
            "prev_region_id": prev_region_id,
            "svg": svg,
            "status": status,
        }
        return d

    @view_config(route_name="eertgif:image")
    def image_view(self):
        tag = self.request.matchdict["tag"]
        img_id = self.request.params.get("image")
        if img_id is None:
            page_id = self.request.params.get("page")
            if page_id is None:
                return HTTPFound(location="/view/{tag}")
            return HTTPFound(location="/view/{tag}?page={page_id}")
        study_lock, top_cont = self._get_lock_and_top(tag)
        with study_lock:
            path_to_image = top_cont.path_to_image(img_id)
        if path_to_image is None:
            return HTTPNotFound(f"Image {img_id} in {tag} does not exist.")
        try:
            with open(path_to_image, "rb") as inp:
                image_blob = inp.read()
        except:
            return HTTPConflict(
                "Server-side mage {img_id} in {tag} does not is not parsable."
            )
        ext = img_id.split(".")[-1]
        resp = self.request.response
        resp.content_type = f"image/{ext}"
        resp.body = image_blob
        return resp

    @view_config(route_name="eertgif:delete", request_method="POST")
    def delete_view(self):
        tag = self.request.matchdict["tag"]
        shared_list = self._get_shared_list_for_upload(tag)
        info_blob, tmp_dir, study_lock, top_cont = shared_list
        log.debug(f"shared_list = {shared_list}")
        with study_lock:
            tc = info_blob.get("to_clean", [])
            if not clean_files_and_dir_no_raise(tc, tmp_dir):
                log.info(f"Failed to remove {tmp_dir}")
            force_remove_study_from_upload_globals(tag)
        return HTTPFound(location="/")

    @view_config(route_name="eertgif:upload", request_method="POST")
    def upload_pdf(self):
        """

        Adapted from https://docs.pylonsproject.org/projects/pyramid-cookbook/en/latest/forms/file_uploads.html
        """
        tag = self.request.POST["name"]
        if not _tag_pat.match(tag):
            return HTTPBadRequest(
                f'"{tag}" is not a valid name. Labels must have only ASCII letters, numbers or spaces'
            )
        by_tag = self._uploads()[1]
        if tag in by_tag:
            return HTTPBadRequest(
                f'"{tag}" is already in use. Choose a new name, or delete the existing study with that name'
            )
        dest_dir = tempfile.mkdtemp(dir=self.uploads_dir)
        shared_list = force_add_upload_dir(tag, dest_dir)
        blob, tmp_dir, study_lock, top_cont = shared_list
        with study_lock:
            assert top_cont is None
            assert tmp_dir == dest_dir
            to_clean = []
            blob["tag"] = tag
            blob["to_clean"] = to_clean
            to_clean.append(_serialize_info_blob_unlocked(blob, dest_dir))

            filename = self.request.POST["pdf"].filename
            input_file = self.request.POST["pdf"].file
            file_path = os.path.join(dest_dir, "uploaded.pdf")
            # Use a temporary file to prevent incomplete files from being used.
            temp_file_path = file_path + "~"
            # Write the data to a temporary file
            input_file.seek(0)
            with open(temp_file_path, "wb") as output_file:
                shutil.copyfileobj(input_file, output_file)

            # Now that we know the file has been fully saved to disk move it into place.
            os.rename(temp_file_path, file_path)
            to_clean.append(file_path)

            img_dir = os.path.join(dest_dir, "img")
            iw = ImageWriter(os.path.join(img_dir))
            to_clean.append(img_dir)

            try:
                unproc_regions, image_paths = get_regions_unprocessed(
                    file_path, image_writer=iw
                )
                to_clean.extend([os.path.join(img_dir, i) for i in image_paths])
            except:
                log.exception(f"pdf parse failure")
                clean_files_and_dir_no_raise(to_clean, dest_dir)
                force_remove_study_from_upload_globals(tag)
                return HTTPBadRequest(
                    f'Uploaded "{filename}" could not be processed as a pdf file'
                )
            try:
                pickled = []
                nfs = set()
                for ur in unproc_regions:
                    pf = f"{ur.tag}.pickle"
                    assert pf not in nfs
                    nfs.add(pf)
                    pfp = os.path.join(dest_dir, pf)
                    to_clean.append(pfp)
                    with open(pfp, "wb") as f_out:
                        pickle.dump(ur, f_out, protocol=pickle.HIGHEST_PROTOCOL)
                    pickled.append(pf)
            except TypeError:
                log.exception(f"Pickle failure")
                clean_files_and_dir_no_raise(to_clean, dest_dir)
                force_remove_study_from_upload_globals(tag)
                return HTTPBadRequest(
                    f"Unexpected error in storing segments of uploaded file."
                )
            blob["unprocessed"] = pickled
            _serialize_info_blob_unlocked(blob, dest_dir)
        return HTTPFound(location=f"/view/{tag}")


def force_remove_study_from_upload_globals(tag):
    log.debug(f'force removing "{tag}"')
    with _upload_lock:
        if tag in _uploads_by_tag:
            log.debug(f'force removing "{tag}" from _uploads_by_tag')
            del _uploads_by_tag[tag]
        to_pop = None
        for n, u in enumerate(_uploads):
            if u[0] == tag:
                to_pop = n
                break
        if to_pop is not None:
            log.debug(f'force removing "{tag}" from pos {to_pop} of _uploads')
            _uploads.pop(to_pop)


def _serialize_info_blob_unlocked(blob, dest_dir):
    """Assumes caller holds lock for the study"""
    info_fp = os.path.join(dest_dir, _info_fn)
    with open(info_fp, "w", encoding="utf-8") as jout:
        json.dump(blob, jout, sort_keys=True, indent=2)
    return info_fp


def clean_files_and_dir_no_raise(to_clean, dest_dir):
    dirs_to_rm = []
    for fp in to_clean:
        try:
            if os.path.isdir(fp):
                dirs_to_rm.append(fp)
            else:
                os.remove(fp)

        except:
            log.exception(f'Temp file "{fp}" could not be deleted.')
            pass
    # longest first to delete in postorder
    dtr = [(len(i), i) for i in dirs_to_rm]
    dtr.sort(reverse=True)
    dtr.append((100000000, dest_dir))
    success = True
    for d in [i[1] for i in dtr]:
        try:
            os.rmdir(d)
        except:
            log.error(f'Temp dir "{d}" could not be deleted.')
            success = False
    return success
