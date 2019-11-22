#!/usr/bin/env python

from setuptools import setup

setup(
    name='comic-dl',
    author='Lucas Hoffmann',
    scripts=['comic_dl.py'],
    version='0.6-dev',
    install_requires=['beautifulsoup4', 'lxml', 'requests'],
)
