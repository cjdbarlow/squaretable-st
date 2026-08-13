# table_pandoc_syntax.py - Pandoc table syntax

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
    return PandocTableSyntax(table_configuration)


class PandocTableSyntax(tbase.TableSyntax):

    def __init__(self, table_configuration):
        tbase.TableSyntax.__init__(self, "Pandoc", table_configuration)

        self.table_parser = tborder.BorderTableParser(self)
        self.table_driver = tborder.BorderTableDriver(self)

        self.hline_out_border = '+'
        self.hline_in_border = '+'
