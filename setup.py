#!/usr/bin/env python

from setuptools import setup
import manga_dl

setup(
    name=manga_dl.name,
    author='Lucas Hoffmann',
    version='.'.join(map(str, manga_dl.__version__)),
    packages=['manga_dl'],
    entry_points={'console_scripts': ['manga-dl = manga_dl.cli:main']}
)
