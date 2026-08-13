# table_lib.py - pretty print text table.

# Copyright (C) 2012  Free Software Foundation, Inc.
# SPDX-License-Identifier: Apache-2.0

# Author: Valery Kocubinsky
# Package: SublimeTableEditor
# Homepage: https://github.com/vkocubinsky/SublimeTableEditor

from __future__ import print_function
from __future__ import division

import csv

try:
    from . import table_base as tbase
    from . import table_simple_syntax as simple
    from . import table_emacs_org_mode_syntax as emacs
    from . import table_pandoc_syntax as pandoc
    from . import table_multi_markdown_syntax as markdown
    from . import table_re_structured_text_syntax as re_structured_text
    from . import table_textile_syntax as textile
except ValueError:
    import table_base as tbase
    import table_simple_syntax as simple
    import table_emacs_org_mode_syntax as emacs
    import table_pandoc_syntax as pandoc
    import table_multi_markdown_syntax as markdown
    import table_re_structured_text_syntax as re_structured_text
    import table_textile_syntax as textile


def simple_syntax(table_configuration=None):
    return create_syntax("Simple", table_configuration)


def emacs_org_mode_syntax(table_configuration=None):
    return create_syntax("EmacsOrgMode", table_configuration)


def pandoc_syntax(table_configuration=None):
    return create_syntax("Pandoc", table_configuration)


def re_structured_text_syntax(table_configuration=None):
    return create_syntax("reStructuredText", table_configuration)


def multi_markdown_syntax(table_configuration=None):
    return create_syntax("MultiMarkdown", table_configuration=table_configuration)


def textile_syntax(table_configuration=None):
    return create_syntax("Textile", table_configuration=table_configuration)


def create_syntax(syntax_name, table_configuration=None):
    modules = {
        "Simple": simple,
        "EmacsOrgMode": emacs,
        "Pandoc": pandoc,
        "MultiMarkdown": markdown,
        "reStructuredText": re_structured_text,
        "Textile": textile
    }

    if syntax_name in modules:
        module = modules[syntax_name]
    else:
        raise ValueError("Syntax {syntax_name} doesn't supported"
                         .format(syntax_name=syntax_name))

    syntax = module.create_syntax(table_configuration)
    return syntax
