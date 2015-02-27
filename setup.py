#!/usr/bin/env python

from setuptools import setup
from manga_dl import constants

setup(
    name=constants.name,
    author='Lucas Hoffmann',
    version='.'.join(map(str, constants.version)),
    packages=['manga_dl'],
    entry_points={'console_scripts': ['manga-dl = manga_dl.cli:main']}
)
