from pathlib import Path
from re import search

# -- General configuration ----------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.intersphinx']

intersphinx_mapping = {
    'flask': ('https://flask.palletsprojects.com/', None),
    'python': ('https://docs.python.org/3/', None),
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
copyright = '2010-2023, Simon Sapin'

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

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
html_theme_options = {
    'index_logo': 'artwork/frozen-flask.png',
    'index_logo_height': '156px',
}

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
