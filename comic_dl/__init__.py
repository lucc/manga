#!python

"""
A crawler/download script to download mangas and other comics from some websites.
"""

import argparse
import asyncio
from importlib.metadata import version
import logging
from pathlib import Path

# needed for the unpickeling?
from .download import start, FileDownload, PageDownload
from .view import run_server


NAME = 'comic-dl'
VERSION = version(NAME)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog=NAME, description="Download manga from some websites")
    parser.add_argument("--debug", default=logging.INFO, action="store_const",
                        const=logging.DEBUG)
    parser.add_argument('--version', action='version', version=VERSION)
    subparsers = parser.add_subparsers()

    dl = subparsers.add_parser("download")
    dl.set_defaults(func=lambda args: asyncio.run(start(args)))
    dl.add_argument(
        "-d", "--directory", help="the output directory to save files",
        default=Path(), type=Path)
    dl.add_argument("--jobs", "-j", type=int, default=3,
                        help="number of concurent downloads")
    target = dl.add_mutually_exclusive_group(required=True)
    target.add_argument("--resume", action="store_true",
                        help="resume downloading from a state file")
    target.add_argument("url", nargs="?", help="the url to start downloading")

    view = subparsers.add_parser("view")
    view.set_defaults(func=run_server)
    view.add_argument("folder", type=Path)
    view.add_argument("--port", default=8080, type=int)
    view.add_argument("--open", action="store_true")

    args = parser.parse_args()
    logging.basicConfig(level=args.debug)
    logging.debug("Command line arguments: %s", args)

    args.func(args)


if __name__ == "__main__":
    main()
