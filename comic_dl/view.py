#!/usr/bin/env python

import argparse
import functools
from itertools import chain, groupby
from pathlib import Path
import threading
import webbrowser

from flask import Flask, Response, render_template, send_from_directory
from jinja2 import Template


@functools.cache
def get_template() -> Template:
    with (Path(__file__).parent / "view.html").open() as f:
        return Template(f.read())


def run_server(args: argparse.Namespace) -> None:
    folder: Path = args.folder
    # find all state files below the given directory, these are the root
    # directories of mangas/comics to view
    dirs = sorted(d.parent.relative_to(folder)
                  for d in folder.glob("**/state.pickle*"))

    def comic(dir: str = "") -> str:
        return render_template(get_template(), comic=dir)

    def data(dir: str = "") -> dict[str, list[str]]:
        p = folder / dir
        gen = chain(p.glob("**/*.JPEG"), p.glob("**/*.JPG"),
                    p.glob("**/*.jpeg"), p.glob("**/*.jpg"))
        groups = groupby(sorted(str(f.relative_to(folder)) for f in gen),
                         lambda f: f.split("/")[1])
        data = {}
        for section, images in groups:
            data[section] = list(images)
        return data

    def images(path: str) -> Response:
        return send_from_directory(folder, path)

    app = Flask("comic-viewer")

    if len(dirs) == 1 and dirs[0] == Path("."):
        app.route("/")(comic)
        app.route("/data")(data)
    else:
        @app.route("/")
        def root() -> str:
            return "".join(f"<p><a href='/view/{dir}'>{dir}</a></p>"
                           for dir in dirs)
        app.route("/view/<dir>")(comic)
        app.route("/data/<dir>")(data)
    app.route("/view/<path:path>")(images)

    if args.open:
        threading.Timer(1, webbrowser.open,
                        args=[f"http://localhost:{args.port}/"]).start()
    app.run(port=args.port)
