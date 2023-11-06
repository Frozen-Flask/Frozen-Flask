from datetime import datetime
from pathlib import Path
from re import search

# -- General configuration ----------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'pallets_sphinx_themes',
]

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'flask': ('https://flask.palletsprojects.com/', None),
    'click': ('https://click.palletsprojects.com/', None),
}

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix of source filenames.
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# General information about the project.
project = 'Frozen-Flask'
copyright = f'2010-{datetime.now().year}, Simon Sapin'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The full version, including alpha/beta/rc tags.
_init = Path(__file__).parent.parent / 'flask_frozen' / '__init__.py'
release = search("VERSION = '([^']+)'", _init.read_text()).group(1)
# The short X.Y version.
version = release

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ['_build']

# Create table of contents entries for domain objects (e.g. functions, classes,
# attributes, etc.). Default is True.
toc_object_entries = False


# -- Options for HTML output --------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = 'flask'

# A list of CSS files. The entry must be a filename string or a tuple
# containing the filename string and the attributes dictionary. The filename
# must be relative to the html_static_path, or a full URI with scheme like
# https://example.org/style.css. The attributes is used for attributes of
# <link> tag.
html_css_files = ['style.css']

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Custom sidebar templates, maps document names to template names.
html_sidebars = {'**': ['sidebarintro.html', 'localtoc.html']}

# Output file base name for HTML help builder.
htmlhelp_basename = 'Frozen-Flask-doc'


# -- Options for manual page output -------------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ('index', 'frozen-flask', 'Frozen-Flask Documentation', ['Simon Sapin'], 1)
]
