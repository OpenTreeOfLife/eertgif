from pyramid.response import Response
from pyramid.view import view_config
import os
import logging
import json
import tempfile
from threading import Lock

log = logging.getLogger("eertgif")

# _uploads is a global of lists, each contained
#   list holds [tag str, blob dict, dir_for_this_upload]
# Use scan_for_uploads to refresh the _uploads
#   global.
_uploads = []
_upload_lock = Lock()
_up_dir = None

_info_fn = "info.json"


def scan_for_uploads(uploads_dir):
    global _uploads, _up_dir
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
            found_uploads.append([blob["tag"], blob, fp])

    with _upload_lock:
        _uploads[:] = found_uploads[:]  # replace contents
        _up_dir = uploads_dir
    return _uploads


class EeertgifView:
    def __init__(self, request):
        self.request = request
        settings = self.request.registry.settings
        self.uploads_dir = settings.get("uploads.dir", "pdfs")

    def _uploads(self):
        """Returns a list of a shallow copy of _uploads"""
        with _upload_lock:
            u = list(_uploads)
        if not u:
            u = list(scan_for_uploads(self.uploads_dir))
        return u

    @view_config(route_name="eertgif:home", renderer="templates/home.pt")
    def eertgif_home_view(self):
        u = self._uploads()
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
        filename = self.request.POST["pdf"].filename
        input_file = request.POST["pdf"].file
        dest_dir = tempfile.mkdtemp(dir=self.uploads_dir)
        file_path = os.path.join(dest_dir, "uploaded.pdf")
        # Use a temporary file to prevent incomplete files from being used.
        temp_file_path = file_path + "~"
        # Write the data to a temporary file
        input_file.seek(0)
        with open(temp_file_path, "wb") as output_file:
            shutil.copyfileobj(input_file, output_file)

        # Now that we know the file has been fully saved to disk move it into place.
        os.rename(temp_file_path, file_path)

        return Response("OK")
