#!/usr/bin/env python

import os
import sys

import requests_futures

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    sys.exit()

packages = [
    'requests_futures',
]

requires = [
    'requests>=1.2.0'
]

if sys.version_info < (3, 2):
    requires.append('futures>=2.1.3')

setup(
    name='requests-futures',
    version=requests_futures.__version__,
    description='Asynchronous Python HTTP for Humans.',
    long_description=open('README.rst').read(),
    author='Ross McFarland',
    author_email='rwmcfa1@neces.com',
    packages=packages,
    package_dir={'requests_futures': 'requests_futures'},
    package_data={'requests_futures': ['LICENSE', 'README.rst']},
    include_package_data=True,
    install_requires=requires,
    license='Apache License v2',
    url='https://github.com/ross/requests-futures',
    zip_safe=False,
    classifiers=(
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ),
)
