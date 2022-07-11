from pyramid.response import Response
from pyramid.httpexceptions import HTTPBadRequest
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

log = logging.getLogger("eertgif")

# _uploads is a global of lists, each contained
#   list holds:
#   [tag str, blob dict, dir_for_this_upload, lock]
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
            found_uploads.append([blob["tag"], blob, fp, None])
    return found_uploads


def _lock_held_udict_from_list():
    """Fills _uploads_by_tag from _uploads. Caller must hold _upload_lock !

    Creates"""
    d = dict(_uploads_by_tag)
    _uploads_by_tag.clear()
    for u in _uploads:
        tag = u[0]
        prev = d.get(tag)
        if prev is None:
            lock = u[3]
            if lock is None:
                lock = Lock()
                u[3] = lock
            _uploads_by_tag[tag] = [u[1], u[2], lock]
        else:
            _uploads_by_tag[tag] = prev


def force_add_upload_dir(tag, dest_dir):
    """Returns the study lock."""
    with _upload_lock:
        nl = Lock()
        _uploads.append([tag, {}, dest_dir, nl])
        _lock_held_udict_from_list()
    return nl


def scan_for_uploads(uploads_dir):
    global _uploads, _up_dir
    found_uploads = _find_uploads(uploads_dir)
    with _upload_lock:
        _uploads[:] = found_uploads[:]  # replace contents
        _up_dir = uploads_dir
        _lock_held_udict_from_list()
    return _uploads


class EeertgifView:
    def __init__(self, request):
        self.request = request
        settings = self.request.registry.settings
        self.uploads_dir = settings.get("uploads.dir", "pdfs")
        self.debug_mode = settings.get("debug_mode", False)
        log.debug(f"self.debug_mode = {repr(self.debug_mode)}")

    def _uploads(self):
        """Returns a list of a shallow copy of _uploads, and _uploads_by_tag"""
        with _upload_lock:
            u = list(_uploads)
        if not u:
            u = list(scan_for_uploads(self.uploads_dir))
        return u, dict(_uploads_by_tag)

    @view_config(route_name="eertgif:home", renderer="templates/home.pt")
    def eertgif_home_view(self):
        u = self._uploads()[0]
        tags = [i[0] for i in u]
        return {"tags": tags}

    @view_config(route_name="eertgif:about", renderer="templates/about.pt")
    def eertgif_about_view(self):
        return {"name": "About View"}

    @view_config(
        route_name="eertgif:upload",
        renderer="templates/upload.pt",
        request_method="POST",
    )
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
        study_lock = force_add_upload_dir(tag, dest_dir)
        with study_lock:
            to_clean = []
            blob = {"tag": tag, "to_clean": to_clean}
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

            try:
                unproc_regions = get_regions_unprocessed(file_path)
            except:
                log.exception(f"pdf parse failure")
                clean_files_and_dir_no_raise(to_clean, dest_dir)
                force_remove_study(tag)
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
            except:
                log.exception(f"Pickle failure")
                clean_files_and_dir_no_raise(to_clean, dest_dir)
                force_remove_study(tag)
                return HTTPBadRequest(
                    f"Unexpected error in storing segments of uploaded file."
                )
            blob["unprocessed"] = pickled
            _serialize_info_blob_unlocked(blob, dest_dir)
        with _upload_lock:
            b = _uploads_by_tag.get(tag)
            if b is not None:
                b[1] = blob
        return Response("OK")


def force_remove_study(tag):
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
    for fp in to_clean:
        try:
            os.remove(fp)
        except:
            log.exception(f'Temp file "{fp}" could not be deleted.')
            pass
    try:
        os.rmdir(dest_dir)
    except:
        log.error(f'Temp dir "{dest_dir}" could not be deleted.')
        return False
    return True
