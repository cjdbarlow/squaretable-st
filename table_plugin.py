# table_plugin.py - sublime plugins for pretty print text table

# Copyright (C) 2012  Free Software Foundation, Inc.
# SPDX-License-Identifier: Apache-2.0

# Author: Valery Kocubinsky
# Package: SublimeTableEditor
# Homepage: https://github.com/vkocubinsky/SublimeTableEditor

import sublime
import sublime_plugin
import re

try:
    from . import table_lib as tlib
    from . import table_base as tbase
    from . import table_grid_model as tmodel
except (ImportError, ValueError):
    import table_lib as tlib
    import table_base as tbase
    import table_grid_model as tmodel


GRID_SYNTAX_NAMES = ('Pandoc', 'reStructuredText')
GRID_ROW_RE = re.compile(r'^\s*[|+].*[|+]\s*$')


def auto_detect_syntax_name(view):
    view_syntax = view.settings().get('syntax') or ''
    resource_name = view_syntax.rsplit('/', 1)[-1].split('.', 1)[0]
    if resource_name in ('MultiMarkdown', 'Markdown'):
        return "MultiMarkdown"
    elif resource_name == 'Textile':
        return "Textile"
    elif resource_name == 'reStructuredText':
        return "reStructuredText"
    return "Simple"


def configured_syntax_name(view):
    if view.settings().has("table_editor_syntax"):
        return view.settings().get("table_editor_syntax")
    return auto_detect_syntax_name(view)


def syntax_settings_name(syntax):
    match = re.search(
        r'([^/]+?)(?:\.tmLanguage|\.sublime-syntax)$', syntax or '')
    return match.group(1) + '.sublime-settings' if match else None


def _is_grid_content(view, point):
    return _grid_document_at(view, point) is not None


def _grid_document_at(view, point):
    row, column = view.rowcol(point)
    if not _is_grid_row(view, row):
        return None

    first_row = row
    while first_row > 0 and _is_grid_row(view, first_row - 1):
        first_row -= 1
    last_row = row
    final_row = view.rowcol(view.size())[0]
    while last_row < final_row and _is_grid_row(view, last_row + 1):
        last_row += 1

    text = '\n'.join(_row_text(view, candidate)
                     for candidate in range(first_row, last_row + 1))
    try:
        return tmodel.GridDocument.try_from_text(text)
    except tbase.TableException:
        try:
            return tmodel.GridDocument.from_editing_text(
                text, row - first_row, column)
        except tbase.TableException:
            return None


def _is_grid_row(view, row):
    return GRID_ROW_RE.match(_row_text(view, row)) is not None


def _row_text(view, row):
    return view.substr(view.line(view.text_point(row, 0)))


class TableEditorContextListener(sublime_plugin.EventListener):

    def on_query_context(self, view, key, operator, operand, match_all):
        if key != 'table_editor_multiline_grid':
            return None

        syntax_enabled = configured_syntax_name(view) in GRID_SYNTAX_NAMES
        values = []
        for selection in view.sel():
            end = max(selection.begin(), selection.end() - 1)
            values.append(
                syntax_enabled and
                _is_grid_content(view, selection.begin()) and
                _is_grid_content(view, end))

        if operator == sublime.OP_NOT_EQUAL:
            matches = [value != operand for value in values]
        else:
            matches = [value == operand for value in values]
        return all(matches) if match_all else any(matches)


class TableContext:

    def __init__(self, view, sel, syntax):
        self.view = view
        (sel_row, sel_col) = self.view.rowcol(sel.begin())
        self.syntax = syntax

        self.first_table_row = self._get_first_table_row(sel_row, sel_col)
        self.last_table_row = self._get_last_table_row(sel_row, sel_col)
        self.table_text = self._get_table_text(self.first_table_row, self.last_table_row)
        self.row_num = sel_row - self.first_table_row
        self.table = self.syntax.table_parser.parse_text(self.table_text)
        self.table_driver = self.syntax.table_driver
        tbase.check_condition(
            (not self.table.empty() and
             0 <= self.row_num < len(self.table) and
             len(self.table[self.row_num]) > 0),
            "Expected a table at the cursor")
        self.visual_field_num = self.visual_field_num_at(sel_row, sel_col)
        self.table_pos = tbase.TablePos(self.row_num, self.visual_field_num)
        self.field_num = self.table_driver.visual_to_internal_index(self.table, self.table_pos).field_num

    def _get_table_text(self, first_table_row, last_table_row):
        begin_point = self.view.line(self.view.text_point(first_table_row, 0)
                                     ).begin()
        end_point = self.view.line(self.view.text_point(last_table_row, 0)
                                   ).end()
        return self.view.substr(sublime.Region(begin_point, end_point))

    def _get_last_table_row(self, sel_row, sel_col):
        row = sel_row
        last_table_row = sel_row
        last_line = self.view.rowcol(self.view.size())[0]
        while (row <= last_line and self._is_table_row(row)):
            last_table_row = row
            row = row + 1
        return last_table_row

    def _get_first_table_row(self, sel_row, sel_col):
        row = sel_row
        first_table_row = sel_row
        while (row >= 0 and self._is_table_row(row)):
            first_table_row = row
            row = row - 1
        return first_table_row

    def _is_table_row(self, row):
        text = self._get_text(row)
        return self.syntax.table_parser.is_table_row(text)

    def visual_field_num_at(self, sel_row, sel_col):
        line_text = self._get_text(sel_row)
        return self.table_driver.visual_field_at_column(
            self.table, sel_row - self.first_table_row,
            line_text, sel_col)

    def _get_text(self, row):
        point = self.view.text_point(row, 0)
        region = self.view.line(point)
        text = self.view.substr(region)
        return text


class AbstractTableCommand(sublime_plugin.TextCommand):

    def detect_syntax(self):
        syntax_name = configured_syntax_name(self.view)

        table_configuration = tbase.TableConfiguration()

        border_style = (self.view.settings().get("table_editor_border_style", None)
                        or self.view.settings().get("table_editor_style", None))
        if border_style == "emacs":
            table_configuration.hline_out_border = '|'
            table_configuration.hline_in_border = '+'
        elif border_style == "grid":
            table_configuration.hline_out_border = '+'
            table_configuration.hline_in_border = '+'
        elif border_style == "simple":
            table_configuration.hline_out_border = '|'
            table_configuration.hline_in_border = '|'

        if self.view.settings().has("table_editor_custom_column_alignment"):
            table_configuration.custom_column_alignment = self.view.settings().get("table_editor_custom_column_alignment")

        if self.view.settings().has("table_editor_keep_space_left"):
            table_configuration.keep_space_left = self.view.settings().get("table_editor_keep_space_left")

        if self.view.settings().has("table_editor_align_number_right"):
            table_configuration.align_number_right = self.view.settings().get("table_editor_align_number_right")

        if self.view.settings().has("table_editor_detect_header"):
            table_configuration.detect_header = self.view.settings().get("table_editor_detect_header")

        if self.view.settings().has("table_editor_intelligent_formatting"):
            table_configuration.intelligent_formatting = self.view.settings().get("table_editor_intelligent_formatting")

        syntax = tlib.create_syntax(syntax_name, table_configuration)
        return syntax

    def auto_detect_syntax_name(self):
        return auto_detect_syntax_name(self.view)

    def merge(self, edit, ctx):
        table = ctx.table
        new_lines = table.render_lines()
        first_table_row = ctx.first_table_row
        last_table_row = ctx.last_table_row
        rows = range(first_table_row, last_table_row + 1)
        for row, new_text in zip(rows, new_lines):
            region = self.view.line(self.view.text_point(row, 0))
            old_text = self.view.substr(region)
            if old_text != new_text:
                self.view.replace(edit, region, new_text)

        #case 1: some lines inserted
        if len(rows) < len(new_lines):
            row = last_table_row
            for new_text in new_lines[len(rows):]:
                end_point = self.view.line(self.view.text_point(row, 0)).end()
                self.view.insert(edit, end_point, "\n" + new_text)
                row = row + 1
        #case 2: some lines deleted
        elif len(rows) > len(new_lines):
            for row in reversed(rows[len(new_lines):]):
                region = self.view.full_line(self.view.text_point(row, 0))
                self.view.erase(edit, region)

    def create_context(self, sel):
        return TableContext(self.view, sel, self.detect_syntax())

    def run(self, edit):
        new_sels = []
        for sel in self.view.sel():
            new_sel = self.run_one_sel(edit, sel)
            new_sels.append(new_sel)
        self.view.sel().clear()
        for sel in new_sels:
            self.view.sel().add(sel)
            self.view.show(sel, False)

    def run_one_sel(self, edit, sel):
        ctx = None
        try:
            ctx = self.create_context(sel)
            msg, table_pos = self.run_operation(ctx)
            self.merge(edit, ctx)
            sublime.status_message("Table Editor: {0}".format(msg))
            return self.table_pos_sel(ctx, table_pos)
        except tbase.TableException as err:
            sublime.status_message("Table Editor: {0}".format(err))
            return sel

    def visual_field_sel(self, ctx, row_num, visual_field_num):
        if ctx.table.empty():
            pt = self.view.text_point(ctx.first_table_row, 0)
        else:
            pos = tbase.TablePos(row_num, visual_field_num)
            col = ctx.table_driver.get_cursor(ctx.table, pos)
            pt = self.view.text_point(ctx.first_table_row + row_num, col)
        return sublime.Region(pt, pt)

    def table_pos_sel(self, ctx, table_pos):
        return self.visual_field_sel(ctx, table_pos.row_num,
                                     table_pos.field_num)

    def field_sel(self, ctx, row_num, field_num):
        if ctx.table.empty():
            visual_field_num = 0
        else:
            pos = tbase.TablePos(row_num, field_num)
            visual_field_num = ctx.table_driver.internal_to_visual_index(ctx.table, pos).field_num
        return self.visual_field_sel(ctx, row_num, visual_field_num)


class TableEditorAlignCommand(AbstractTableCommand):
    """
    Key: ctrl+shift+a
    Re-align the table without change the current table field.
    Move cursor to begin of the current table field.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_align(ctx.table, ctx.table_pos)


class TableEditorNextField(AbstractTableCommand):
    """
    Key: tab
    Re-align the table, move to the next field.
    Creates a new row if necessary.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_next_field(ctx.table, ctx.table_pos)


class TableEditorPreviousField(AbstractTableCommand):
    """
    Key: shift+tab
    Re-align, move to previous field.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_previous_field(ctx.table, ctx.table_pos)


def reject_unsafe_grid_selections(view):
    selections = list(view.sel())
    uses_grid = (configured_syntax_name(view) in GRID_SYNTAX_NAMES and
                 any(_is_grid_content(view, selection.begin())
                     for selection in selections))
    if (uses_grid and
            (len(selections) != 1 or not selections[0].empty())):
        sublime.status_message(
            "Table Editor: Bordered grid editing requires one caret")
        return True
    return False


class SingleCaretLogicalGridCommand(AbstractTableCommand):

    def run(self, edit):
        if reject_unsafe_grid_selections(self.view):
            return
        AbstractTableCommand.run(self, edit)


class TableEditorNextRow(SingleCaretLogicalGridCommand):
    """
    Key: enter
    Re-align the table and move down to next row.
    Creates a new row if necessary.
    At the beginning or end of a line, enter still does new line.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_next_row(ctx.table, ctx.table_pos)


class TableEditorMoveColumnLeft(SingleCaretLogicalGridCommand):
    """
    Key: alt+left
    Move the current column left.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_move_column_left(ctx.table,
                                                        ctx.table_pos)


class TableEditorMoveColumnRight(SingleCaretLogicalGridCommand):
    """
    Key: alt+right
    Move the current column right.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_move_column_right(ctx.table,
                                                         ctx.table_pos)


class TableEditorDeleteColumn(SingleCaretLogicalGridCommand):
    """
    Key: alt+shift+left
    Kill the current column.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_delete_column(ctx.table,
                                                     ctx.table_pos)


class TableEditorInsertColumn(SingleCaretLogicalGridCommand):
    """
    Keys: alt+shift+right
    Insert a new column to the left of the cursor position.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_insert_column(ctx.table,
                                                     ctx.table_pos)


class TableEditorKillRow(SingleCaretLogicalGridCommand):
    """
    Key : alt+shift+up
    Kill the current row.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_kill_row(ctx.table, ctx.table_pos)


class TableEditorInsertRow(SingleCaretLogicalGridCommand):
    """
    Key: alt+shift+down
    Insert a new row above the current row.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_insert_row(ctx.table, ctx.table_pos)


class TableEditorMoveRowUp(SingleCaretLogicalGridCommand):
    """
    Key: alt+up
    Move the current row up.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_move_row_up(ctx.table, ctx.table_pos)


class TableEditorMoveRowDown(SingleCaretLogicalGridCommand):
    """
    Key: alt+down
    Move the current row down.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_move_row_down(ctx.table,
                                                     ctx.table_pos)


def multiline_grid_driver(ctx):
    if not getattr(ctx.table_driver, 'supports_multiline_grid', False):
        raise tbase.TableException(
            "Multiline cell editing requires a bordered grid table")
    return ctx.table_driver


class SingleCaretGridCommand(AbstractTableCommand):

    def run(self, edit):
        selections = list(self.view.sel())
        if len(selections) != 1 or not selections[0].empty():
            sublime.status_message(
                "Table Editor: Multiline grid editing requires one caret")
            return
        AbstractTableCommand.run(self, edit)


class TableEditorInsertCellRow(SingleCaretGridCommand):

    def run_operation(self, ctx):
        return multiline_grid_driver(ctx).editor_insert_cell_row(
            ctx.table, ctx.table_pos)


class TableEditorDeleteCellRow(SingleCaretGridCommand):

    def run_operation(self, ctx):
        return multiline_grid_driver(ctx).editor_delete_cell_row(
            ctx.table, ctx.table_pos)


class TableEditorMoveCellRowUp(SingleCaretGridCommand):

    def run_operation(self, ctx):
        return multiline_grid_driver(ctx).editor_move_cell_row_up(
            ctx.table, ctx.table_pos)


class TableEditorMoveCellRowDown(SingleCaretGridCommand):

    def run_operation(self, ctx):
        return multiline_grid_driver(ctx).editor_move_cell_row_down(
            ctx.table, ctx.table_pos)


class CellRowsSelectionCommand(object):

    outdent = False

    def run(self, edit):
        selections = list(self.view.sel())
        if len(selections) != 1 or selections[0].empty():
            sublime.status_message(
                "Table Editor: Select rows in one grid-table cell")
            return

        selection = selections[0]
        try:
            ctx = self.create_context(sublime.Region(selection.begin(),
                                                     selection.begin()))
            driver = multiline_grid_driver(ctx)
            start = self._table_pos(ctx, selection.begin())
            end = self._table_pos(ctx, selection.end() - 1)
            tab_size = int(self.view.settings().get('tab_size', 4))
            if self.outdent:
                msg, table_pos = driver.editor_outdent_cell_rows(
                    ctx.table, start, end, tab_size)
            else:
                use_spaces = self.view.settings().get(
                    'translate_tabs_to_spaces', True)
                indent = ' ' * tab_size if use_spaces else '\t'
                msg, table_pos = driver.editor_indent_cell_rows(
                    ctx.table, start, end, indent)
            self.merge(edit, ctx)
            new_selection = self.table_pos_sel(ctx, table_pos)
            self.view.sel().clear()
            self.view.sel().add(new_selection)
            self.view.show(new_selection, False)
            sublime.status_message("Table Editor: {0}".format(msg))
        except tbase.TableException as err:
            sublime.status_message("Table Editor: {0}".format(err))

    def _table_pos(self, ctx, point):
        row, col = self.view.rowcol(point)
        tbase.check_condition(
            ctx.first_table_row <= row <= ctx.last_table_row,
            "Selection must stay within one table")
        return tbase.TablePos(
            row - ctx.first_table_row,
            ctx.visual_field_num_at(row, col))


class TableEditorIndentCellRows(CellRowsSelectionCommand,
                                AbstractTableCommand):
    pass


class TableEditorOutdentCellRows(CellRowsSelectionCommand,
                                 AbstractTableCommand):
    outdent = True


class TableEditorInsertSingleHline(AbstractTableCommand):
    """
    Key: ctrl+k,-
    Insert single horizontal line below current row.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_insert_single_hline(ctx.table,
                                                           ctx.table_pos)


class TableEditorInsertDoubleHline(AbstractTableCommand):
    """
    Key: ctrl+k,=
    Insert double horizontal line below current row.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_insert_double_hline(ctx.table,
                                                           ctx.table_pos)


class TableEditorHlineAndMove(AbstractTableCommand):
    """
    Key: ctrl+k, enter
    Insert a horizontal line below current row,
    and move the cursor into the row below that line.
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_insert_hline_and_move(ctx.table,
                                                             ctx.table_pos)


class TableEditorSplitColumnDown(AbstractTableCommand):
    """
    Key: alt+enter
    Split rest of cell down from current cursor position,
    insert new line bellow if current row is last row in the table
    or if next line is hline
    """
    def remove_rest_line(self, edit, sel):
        end_region = self.view.find(r"\|",
                                    sel.begin())
        rest_region = sublime.Region(sel.begin(), end_region.begin())
        rest_data = self.view.substr(rest_region)
        self.view.replace(edit, rest_region, "")
        return rest_data.strip()

    def run_one_sel(self, edit, sel):
        try:
            ctx = self.create_context(sel)
        except tbase.TableException as err:
            sublime.status_message("Table Editor: {0}".format(err))
            return sel
        if (hasattr(ctx.table_driver, 'is_complete_grid') and
                ctx.table_driver.is_complete_grid(ctx.table)):
            sublime.status_message(
                "Table Editor: Split column down is not available for "
                "bordered grid tables")
            return sel
        field_num = ctx.field_num
        row_num = ctx.row_num
        if (ctx.table[row_num].is_separator() or
                ctx.table[row_num].is_header_separator()):
            sublime.status_message("Table Editor: Split column is not "
                                   "permitted for separator or header "
                                   "separator line")
            return sel
        if row_num + 1 < len(ctx.table):
            if len(ctx.table[row_num + 1]) - 1 < field_num:
                sublime.status_message("Table Editor: Split column is not "
                                       "permitted for short line")
                return sel
            elif ctx.table[row_num + 1][field_num].pseudo():
                sublime.status_message("Table Editor: Split column is not "
                                       "permitted to colspan column")
                return sel

        (sel_row, sel_col) = self.view.rowcol(sel.begin())
        rest_data = self.remove_rest_line(edit, sel)

        ctx = self.create_context(sel)

        field_num = ctx.field_num
        row_num = ctx.row_num

        if row_num + 1 == len(ctx.table) or ctx.table[row_num + 1].is_separator():
            ctx.table.insert_empty_row(row_num + 1)

        row_num = row_num + 1
        ctx.table[row_num][field_num].data = rest_data + " " + ctx.table[row_num][field_num].data.strip()
        ctx.table.pack()
        self.merge(edit, ctx)
        sublime.status_message("Table Editor: Column splitted down")
        return self.field_sel(ctx, row_num, field_num)


class TableEditorJoinLines(AbstractTableCommand):
    """
    Key: ctrl+j
    Join current row and next row into one if next row is not hline
    """
    def run_operation(self, ctx):
        return ctx.table_driver.editor_join_lines(ctx.table, ctx.table_pos)


class TableEditorCsvToTable(AbstractTableCommand):
    """
    Command: table_csv_to_table
    Key: ctrl+k, |
    Convert selected CSV region into table
    """

    def run_one_sel(self, edit, sel):
        if sel.empty():
            return sel
        else:
            syntax = self.detect_syntax()
            text = self.view.substr(sel)
            table = syntax.table_driver.parse_csv(text)
            self.view.replace(edit, sel, table.render())

            first_row = self.view.rowcol(sel.begin())[0]

            pt = self.view.text_point(first_row, syntax.table_driver.get_cursor(table, tbase.TablePos(0, 0)))
            sublime.status_message("Table Editor: Table created from CSV")
            return sublime.Region(pt, pt)


class TableEditorDisableForCurrentView(sublime_plugin.TextCommand):

    def run(self, args, prop):
        self.view.settings().set(prop, False)


class TableEditorEnableForCurrentView(sublime_plugin.TextCommand):

    def run(self, args, prop):
        self.view.settings().set(prop, True)


class TableEditorDisableForCurrentSyntax(sublime_plugin.TextCommand):

    def run(self, edit):
        base_name = syntax_settings_name(
            self.view.settings().get('syntax'))
        if base_name:
            settings = sublime.load_settings(base_name)
            settings.erase("enable_table_editor")
            sublime.save_settings(base_name)


class TableEditorEnableForCurrentSyntax(sublime_plugin.TextCommand):

    def run(self, edit):
        base_name = syntax_settings_name(
            self.view.settings().get('syntax'))
        if base_name:
            settings = sublime.load_settings(base_name)
            settings.set("enable_table_editor", True)
            sublime.save_settings(base_name)


class TableEditorSetSyntax(sublime_plugin.TextCommand):

    def run(self, edit, syntax):
        self.view.settings().set("enable_table_editor", True)
        self.view.settings().set("table_editor_syntax", syntax)
        sublime.status_message("Table Editor: set syntax to '{0}'"
                               .format(syntax))


class TableEditorFilmCommand(sublime_plugin.WindowCommand):

    def run(self):
        try:
            from .tests.table_plugin_test import TableEditorTestSuite
        except (ImportError, ValueError):
            from tests.table_plugin_test import TableEditorTestSuite

        view = self.window.new_file()
        view.set_scratch(True)
        view.set_name("Sublime Table Editor Film")
        view.settings().set("table_editor_border_style", "simple")
        view.run_command(
            "table_editor_enable_for_current_view",
            {"prop": "enable_table_editor"})
        TableEditorTestSuite(view).run()
