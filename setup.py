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

packages = ['requests_futures']

requires = ['requests>=1.2.0']

tests_require = ('pytest>=6.2.5', 'pytest-cov>=3.0.0', 'pytest-network>=0.0.1')

setup(
    name='requests-futures',
    version=requests_futures.__version__,
    description='Asynchronous Python HTTP for Humans.',
    extras_require={
        'dev': tests_require
        + (
            'black>=22.3.0',
            'build>=0.7.0',
            'isort>=5.11.4',
            'pyflakes>=2.2.0',
            'readme_renderer[rst]>=26.0',
            'twine>=3.4.2',
        )
    },
    long_description=open('README.rst').read(),
    long_description_content_type='text/x-rst',
    author='Ross McFarland',
    author_email='rwmcfa1@rwmcfa1.com',
    packages=packages,
    package_dir={'requests_futures': 'requests_futures'},
    package_data={'requests_futures': ['LICENSE', 'README.rst']},
    include_package_data=True,
    install_requires=requires,
    setup_requires=['setuptools>=38.6.1'],
    license='Apache License v2',
    tests_require=tests_require,
    url='https://github.com/ross/requests-futures',
    zip_safe=False,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    options={'bdist_wheel': {'universal': True}},
)
