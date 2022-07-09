from pyramid.response import Response
from pyramid.view import view_config
import os
import logging

log = logging.getLogger("eertgif")


class EeertgifView:
    def __init__(self, request):
        self.request = request
        settings = self.request.registry.settings
        self.uploads_dir = settings.get("uploads.dir", "pdfs")

    @view_config(route_name="eertgif:home", renderer="templates/home.pt")
    def eertgif_home_view(self):
        ud = self.uploads_dir
        ld = [i for i in os.listdir(ud) if os.path.isdir(os.path.join(ud, i))]
        return {"tags": ld}

    @view_config(route_name="eertgif:about", renderer="templates/about.pt")
    def eertgif_about_view(self):
        return {"name": "About View"}
