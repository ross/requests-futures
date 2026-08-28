import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from requests_futures import __version__

### sphinx config ###

project = 'requests-futures'
copyright = '2013-present'  # noqa
author = 'Ross McFarland'
release = __version__
version = __version__

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx.ext.viewcode',
    'sphinx_copybutton',
    'sphinx_rtd_theme',
]

### autodoc ###

autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'special-members': '__init__',
    'show-inheritance': True,
}
autodoc_member_order = 'bysource'

### napoleon ###
# Docstrings here are plain reST (Sphinx field lists), not Google/NumPy
# style, but napoleon is still useful for tidying up the rendered output.

napoleon_google_docstring = False
napoleon_numpy_docstring = False

### intersphinx ###
# Lets `:class:`/`:meth:` references to Session, Future, HTTPAdapter, and
# Retry resolve to their upstream docs instead of rendering as plain text.

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'requests': ('https://requests.readthedocs.io/en/latest/', None),
    'urllib3': ('https://urllib3.readthedocs.io/en/stable/', None),
}

### content ###

master_doc = 'index'

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

### theme ###

html_theme = 'sphinx_rtd_theme'
