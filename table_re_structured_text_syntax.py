# re_structured_text_syntax.py - Support reStructuredText table syntax

# Copyright (C) 2012  Free Software Foundation, Inc.
# SPDX-License-Identifier: Apache-2.0

# Author: Valery Kocubinsky
# Package: SublimeTableEditor
# Homepage: https://github.com/vkocubinsky/SublimeTableEditor

from __future__ import print_function
from __future__ import division

try:
    from . import table_base as tbase
    from . import table_border_syntax as tborder
except ValueError:
    import table_base as tbase
    import table_border_syntax as tborder


def create_syntax(table_configuration=None):
    return ReStructuredTextTableSyntax(table_configuration)


class ReStructuredTextTableSyntax(tbase.TableSyntax):

    def __init__(self, table_configuration):
        tbase.TableSyntax.__init__(self, "reStructuredText", table_configuration)

        self.table_parser = tborder.BorderTableParser(self)
        self.table_driver = tborder.BorderTableDriver(self)

        self.hline_out_border = '+'
        self.hline_in_border = '+'
