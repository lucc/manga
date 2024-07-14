"""
A crawler/download script to download mangas and other comics from some websites.
"""

import argparse
import asyncio
from importlib.metadata import version, PackageNotFoundError
import logging
from pathlib import Path

from .download import resume, start
from .view import run_server


NAME = 'comic-dl'
try:
    VERSION = version(NAME)
except PackageNotFoundError:
    VERSION = "dev"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog=NAME, description="Download manga from some websites")
    parser.add_argument("--debug", default=logging.INFO, action="store_const",
                        const=logging.DEBUG)
    parser.add_argument('--version', action='version', version=VERSION)
    subparsers = parser.add_subparsers()

    dl = subparsers.add_parser("download")
    dl.set_defaults(func=lambda args:
        asyncio.run(start(args.url, args.directory, args.jobs)))
    dl.add_argument(
        "-d", "--directory", help="the output directory to save files",
        default=Path(), type=Path)
    dl.add_argument("--jobs", "-j", type=int, default=3,
                    help="number of concurrent downloads")
    dl.add_argument("url", help="the url to start downloading")

    r = subparsers.add_parser("resume")
    r.set_defaults(func=lambda args: asyncio.run(resume(args.target, args.jobs)))
    r.add_argument("--jobs", "-j", type=int, default=3,
                   help="number of concurrent downloads")
    r.add_argument("target", type=Path, nargs="+",
                        help="directories and state files to resume from")

    view = subparsers.add_parser("view")
    view.set_defaults(func=run_server)
    view.add_argument("folder", type=Path)
    view.add_argument("--port", default=8080, type=int)
    view.add_argument("--open", action="store_true")

    args = parser.parse_args()
    logging.basicConfig(level=args.debug, format="%(levelname)s:\t%(message)s")
    logging.debug("Command line arguments: %s", args)

    if "func" not in args:
        parser.error("No command given.")
    args.func(args)
