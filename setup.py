#!/usr/bin/env python3

import os
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, 'README.md')) as f:
    README = f.read()

if __name__ == "__main__":
    setup(
        name = 'django-settings-object',
        setup_requires = ['setuptools_scm'],
        use_scm_version = True,
        description = 'Django utilities for building settings objects.',
        long_description = README,
        classifiers = [
            "Programming Language :: Python",
            "Framework :: Django",
        ],
        author = 'Matt Pryor',
        author_email = 'matt.pryor@stfc.ac.uk',
        url = 'https://github.com/cedadev/django-settings-object',
        keywords = 'web django settings',
        packages = find_packages(),
        include_package_data = True,
        zip_safe = False,
        extras_require = {
            'django': ['django'],
        }
    )
