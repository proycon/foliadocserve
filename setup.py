#! /usr/bin/env python3
# -*- coding: utf8 -*-

from __future__ import print_function

import os
import sys
from setuptools import setup


try:
   os.chdir(os.path.dirname(sys.argv[0]))
except:
   pass


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "foliadocserve",
    version = "0.2",
    author = "Maarten van Gompel",
    author_email = "proycon@anaproy.nl",
    description = ("The FoLiA Document Server is a backend HTTP service to interact with documents in the FoLiA format, a rich XML-based format for linguistic annotation (http://proycon.github.io/folia). It provides an interface to efficiently edit FoLiA documents through the FoLiA Query Language (FQL). "),
    license = "GPL",
    keywords = "nlp computational_linguistics rest database document server",
    url = "https://github.com/proycon/foliadocserve",
    packages=['foliadocserve','foliadocserve.flat','foliadocserve.test'],
    long_description=read('README.md'),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Text Processing :: Linguistic",
        "Programming Language :: Python :: 3.2",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Operating System :: POSIX",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    ],
    entry_points = {
        'console_scripts': [
            'foliadocserve = foliadocserve.foliadocserve:main'
        ]
    },
    package_data = {'foliadocserve':[] },
    install_requires=['lxml >= 2.2','pynlpl >= 0.7.0']
)