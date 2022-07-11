#!/usr/bin/env python3
__all__ = ["extract", "to_svg", "views"]

from pyramid.config import Configurator

import logging

log = logging.getLogger("eertgif")

# noinspection PyUnusedLocal
def main(global_config, **settings):

    log.debug("Starting eertgif...")
    """ This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings)
    config.include("pyramid_chameleon")
    # config.add_route('home', '/')
    log.debug("Read configuration...")

    config.add_route("eertgif:home", "/")
    config.add_route("eertgif:about", "/about")
    config.add_route("eertgif:upload", "/upload")
    config.add_route("eertgif:edit", "/edit/{tag}")
    config.add_route("eertgif:delete", "/delete/{tag}")

    config.scan(".views")
    log.debug("Added routes.")
    return config.make_wsgi_app()
