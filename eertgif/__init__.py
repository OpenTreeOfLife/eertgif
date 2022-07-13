#!/usr/bin/env python3
__all__ = ["extract", "point_map", "study_container", "to_svg", "views"]

from pyramid.config import Configurator
import os

import logging

log = logging.getLogger("eertgif")

# noinspection PyUnusedLocal
def main(global_config, **settings):

    log.debug("Starting eertgif...")
    """ This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings)
    config.include("pyramid_chameleon")
    abs_path_to_static = os.path.join(os.path.abspath(os.curdir), "static")
    log.debug(f"abs_path_to_static = {abs_path_to_static}")
    config.add_static_view(name="static", path=abs_path_to_static)
    # config.add_route('home', '/')
    log.debug("Read configuration...")

    config.add_route("eertgif:home", "/")
    config.add_route("eertgif:about", "/about")
    config.add_route("eertgif:upload", "/upload")
    config.add_route("eertgif:edit", "/edit/{tag}")
    config.add_route("eertgif:extract", "/extract/{tag}")
    config.add_route("eertgif:view", "/view/{tag}")
    config.add_route("eertgif:delete", "/delete/{tag}")
    config.add_route("eertgif:set_status", "/set_status/{tag}")

    config.scan(".views")
    log.debug("Added routes.")
    return config.make_wsgi_app()
