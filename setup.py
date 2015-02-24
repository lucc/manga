#!/usr/bin/env python

from setuptools import setup
from manga_dl import constants

setup(
    name=constants.name,
    author='Lucas Hoffmann',
    version='.'.join(map(str, constants.version)),
    scripts=['scripts/manga-dl'],
    packages=['manga_dl'],
)
