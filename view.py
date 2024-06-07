#!/usr/bin/env python

import argparse
from http import HTTPStatus
import http.server
from itertools import chain, groupby
import json
import os
from pathlib import Path
import threading
from typing import Callable
import webbrowser


class RequestHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self) -> None:
        if handler := self.routes(self.path):
            handler()
        else:
            super().do_GET()

    def routes(self, path: str) -> Callable | None:
        return {
            "/": self.handle_root,
            "/data": self.handle_data,
        }.get(path)

    def handle_root(self) -> None:
        template = Path(__file__).parent / "view.html"
        with template.open("rb") as f:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(template.stat().st_size))
            self.end_headers()
            self.copyfile(f, self.wfile)

    def find_images(self) -> dict[str, list[str]]:
        p = Path()
        gen = chain(p.glob("**/*.JPEG"), p.glob("**/*.JPG"),
                    p.glob("**/*.jpeg"), p.glob("**/*.jpg"))
        groups = groupby(sorted(str(f) for f in gen), lambda f: f.split("/")[0])
        data = {}
        for section, images in groups:
            data[section] = list(images)
        return data


    def handle_data(self) -> None:
        s = json.dumps(self.find_images())
        b = bytes(s, "UTF-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    # change the current working directory as the http request handler uses it
    os.chdir(args.folder)

    if args.open:
        threading.Timer(1, webbrowser.open,
                        args=[f"http://localhost:{args.port}/"]).start()

    with http.server.ThreadingHTTPServer(("", args.port), RequestHandler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
