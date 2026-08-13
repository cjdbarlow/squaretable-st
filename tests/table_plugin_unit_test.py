"""Unit tests for the Sublime plugin integration layer."""

import importlib
import sys
import types
import unittest


class Region(object):

    def __init__(self, begin, end=None):
        self._begin = begin
        self._end = begin if end is None else end

    def begin(self):
        return self._begin

    def end(self):
        return self._end

    def empty(self):
        return self._begin == self._end


class TextCommand(object):

    def __init__(self, view):
        self.view = view


class FakeView(object):

    def __init__(self, text):
        self.text = text

    def text_point(self, row, col):
        lines = self.text.splitlines(True)
        return sum(len(line) for line in lines[:row]) + col

    def rowcol(self, point):
        before = self.text[:point]
        return before.count('\n'), len(before.rsplit('\n', 1)[-1])

    def size(self):
        return len(self.text)

    def line(self, point):
        start = self.text.rfind('\n', 0, point) + 1
        end = self.text.find('\n', point)
        if end == -1:
            end = len(self.text)
        return Region(start, end)

    def full_line(self, point):
        region = self.line(point)
        end = region.end()
        if end < len(self.text) and self.text[end] == '\n':
            end += 1
        return Region(region.begin(), end)

    def substr(self, region):
        return self.text[region.begin():region.end()]

    def replace(self, unused_edit, region, value):
        self.text = (self.text[:region.begin()] + value +
                     self.text[region.end():])

    def insert(self, unused_edit, point, value):
        self.text = self.text[:point] + value + self.text[point:]

    def erase(self, unused_edit, region):
        self.replace(None, region, '')


class RenderedTable(object):

    def __init__(self, lines):
        self.lines = lines

    def render_lines(self):
        return self.lines


class Context(object):
    pass


def load_plugin():
    sublime = types.ModuleType('sublime')
    sublime.Region = Region
    sublime.OP_NOT_EQUAL = 1
    sublime.status_messages = []
    sublime.status_message = sublime.status_messages.append
    sublime_plugin = types.ModuleType('sublime_plugin')
    sublime_plugin.TextCommand = TextCommand
    sublime_plugin.EventListener = object
    sublime_plugin.WindowCommand = object
    sys.modules['sublime'] = sublime
    sys.modules['sublime_plugin'] = sublime_plugin
    sys.modules.pop('table_plugin', None)
    return importlib.import_module('table_plugin')


class Settings(dict):

    def has(self, key):
        return key in self


class SyntaxView(object):

    def __init__(self, syntax):
        self._settings = Settings(syntax=syntax)

    def settings(self):
        return self._settings


class SyntaxDetectionTest(unittest.TestCase):

    def test_plugin_owns_film_command_entrypoint(self):
        plugin = load_plugin()

        self.assertTrue(hasattr(plugin, 'TableEditorFilmCommand'))

    def test_detects_st4_restructured_text_resource(self):
        plugin = load_plugin()
        view = SyntaxView(
            'Packages/RestructuredText/reStructuredText.sublime-syntax')

        self.assertEqual('reStructuredText',
                         plugin.auto_detect_syntax_name(view))

    def test_builds_settings_name_for_both_resource_formats(self):
        plugin = load_plugin()

        self.assertEqual(
            'Markdown.sublime-settings',
            plugin.syntax_settings_name(
                'Packages/Markdown/Markdown.sublime-syntax'))
        self.assertEqual(
            'Markdown.sublime-settings',
            plugin.syntax_settings_name(
                'Packages/Markdown/Markdown.tmLanguage'))


class MergeTest(unittest.TestCase):

    def test_removes_deleted_physical_line_including_newline(self):
        plugin = load_plugin()
        view = FakeView("before\n+---+\n| a |\n| b |\n+---+\nafter")
        command = plugin.AbstractTableCommand(view)
        ctx = Context()
        ctx.table = RenderedTable(["+---+", "| a |", "+---+"])
        ctx.first_table_row = 1
        ctx.last_table_row = 4

        command.merge(None, ctx)

        self.assertEqual("before\n+---+\n| a |\n+---+\nafter", view.text)

    def test_removes_multiple_deleted_lines_from_bottom_up(self):
        plugin = load_plugin()
        view = FakeView(
            "before\n+---+\n| a |\n| b |\n| c |\n+---+\nafter")
        command = plugin.AbstractTableCommand(view)
        ctx = Context()
        ctx.table = RenderedTable(["+---+", "| a |", "+---+"])
        ctx.first_table_row = 1
        ctx.last_table_row = 5

        command.merge(None, ctx)

        self.assertEqual("before\n+---+\n| a |\n+---+\nafter", view.text)


class GridContentTest(unittest.TestCase):

    def test_recognizes_cell_line_inside_bordered_grid(self):
        plugin = load_plugin()
        view = FakeView("+---+---+\n| A | B |\n+---+---+")

        self.assertTrue(plugin._is_grid_content(view, view.text.index('|')))

    def test_rejects_ordinary_pandoc_pipe_table(self):
        plugin = load_plugin()
        view = FakeView("| A | B |\n| C | D |")

        self.assertFalse(plugin._is_grid_content(view, 0))

    def test_rejects_isolated_pipe_line(self):
        plugin = load_plugin()
        view = FakeView("before\n| A |\nafter")

        self.assertFalse(plugin._is_grid_content(view, view.text.index('|')))

    def test_recognizes_separator_inside_complete_grid(self):
        plugin = load_plugin()
        view = FakeView("+---+\n| A |\n+---+")

        self.assertTrue(plugin._is_grid_content(view, 0))

    def test_rejects_incomplete_bordered_fragment(self):
        plugin = load_plugin()
        view = FakeView("+---+\n| A |")

        self.assertFalse(
            plugin._is_grid_content(view, view.text.index('|')))

    def test_rejects_complete_prefix_of_incomplete_bordered_fragment(self):
        plugin = load_plugin()
        view = FakeView("+---+\n| A |\n+---+\n| B |")

        self.assertFalse(plugin._is_grid_content(view, view.text.index('A')))
        self.assertFalse(plugin._is_grid_content(view, view.text.index('B')))

    def test_partial_rowspan_separator_stays_inside_complete_grid(self):
        plugin = load_plugin()
        view = FakeView("""\
+---+---+
| A | B |
|   +---+
| C | D |
+---+---+""")

        self.assertTrue(plugin._is_grid_content(view, view.text.index('A')))
        self.assertTrue(plugin._is_grid_content(
            view, view.text.index('+---+', view.text.index('A'))))
        self.assertTrue(plugin._is_grid_content(view, view.text.index('C')))

class SelectionList(list):

    def clear(self):
        del self[:]

    def add(self, selection):
        self.append(selection)


class CommandView(object):

    def __init__(self, selections):
        self.selections = SelectionList(selections)

    def sel(self):
        return self.selections


class EditingView(FakeView):

    def __init__(self, text, point):
        FakeView.__init__(self, text)
        self._settings = Settings(table_editor_syntax='Pandoc')
        self.selections = SelectionList([Region(point)])

    def settings(self):
        return self._settings

    def sel(self):
        return self.selections

    def show(self, unused_region, unused_animate):
        pass


class GridContextQueryTest(unittest.TestCase):

    def mixed_view(self):
        text = "+---+\n| A |\n+---+\nordinary"
        view = EditingView(text, text.index('A'))
        view.selections[:] = [Region(text.index('A')),
                              Region(text.index('ordinary'))]
        return view

    def test_match_all_requires_every_selection_to_match_true(self):
        plugin = load_plugin()
        listener = plugin.TableEditorContextListener()

        self.assertFalse(listener.on_query_context(
            self.mixed_view(), 'table_editor_multiline_grid', 0,
            True, True))

    def test_match_all_requires_every_selection_to_match_false(self):
        plugin = load_plugin()
        listener = plugin.TableEditorContextListener()

        self.assertFalse(listener.on_query_context(
            self.mixed_view(), 'table_editor_multiline_grid', 0,
            False, True))

    def test_match_any_accepts_one_selection_matching_operand(self):
        plugin = load_plugin()
        listener = plugin.TableEditorContextListener()
        view = self.mixed_view()

        self.assertTrue(listener.on_query_context(
            view, 'table_editor_multiline_grid', 0, True, False))
        self.assertTrue(listener.on_query_context(
            view, 'table_editor_multiline_grid', 0, False, False))


class CellCommandIntegrationTest(unittest.TestCase):

    def _manually_merged_readme_grid(self):
        plugin = load_plugin()
        text = ("+---+-----+\n"
                "| Title   |\n"
                "+===+=====+\n"
                "| A | B   |\n"
                "|   +-----+\n"
                "| C | D   |\n"
                "|   | sdf |\n"
                "+--------+\n"
                "|        |\n"
                "+--------+")
        return plugin, text

    def _typed_readme_span_grid(self):
        plugin = load_plugin()
        text = ("+---+---+\n"
                "| Title |\n"
                "+===+===+\n"
                "| A | B |\n"
                "|   +---+\n"
                "| C | D |\n"
                "+---+---+")
        view = EditingView(text, text.rindex('D') + 1)
        plugin.TableEditorNextRow(view).run(None)
        caret = view.sel()[0].begin()
        view.insert(None, caret, 'letters')
        view.selections[:] = [Region(caret + len('letters'))]
        return plugin, view

    def test_typed_cell_row_remains_in_multiline_grid_context(self):
        plugin, view = self._typed_readme_span_grid()

        self.assertTrue(
            plugin._is_grid_content(view, view.sel()[0].begin()))

    def test_enter_after_typing_resizes_and_preserves_spans(self):
        plugin, view = self._typed_readme_span_grid()
        dirty = view.text

        plugin.TableEditorNextRow(view).run(None)

        self.assertNotEqual(dirty, view.text)
        import table_grid_model
        grid = table_grid_model.GridDocument.from_text(view.text)
        cells = dict((cell.bounds(), cell.rows) for cell in grid.cells)
        self.assertEqual(['D', 'letters', ''], cells[(1, 2, 2, 3)])
        self.assertIn((0, 0, 2, 1), cells)
        self.assertIn((0, 1, 1, 3), cells)
        self.assertGreater(len(view.text.splitlines()[0]), len('+---+---+'))

    def test_tab_after_typing_resizes_and_preserves_spans(self):
        plugin, view = self._typed_readme_span_grid()
        dirty = view.text

        plugin.TableEditorNextField(view).run(None)

        self.assertNotEqual(dirty, view.text)
        import table_grid_model
        grid = table_grid_model.GridDocument.from_text(view.text)
        cells = dict((cell.bounds(), cell.rows) for cell in grid.cells)
        self.assertEqual(['D', 'letters'], cells[(1, 2, 2, 3)])
        self.assertIn((0, 0, 2, 1), cells)
        self.assertIn((0, 1, 1, 3), cells)
        self.assertGreater(len(view.text.splitlines()[0]), len('+---+---+'))

    def test_tab_after_growing_first_cell_moves_to_second_cell(self):
        plugin = load_plugin()
        text = ("+---+---+---+\n"
                "| A | B | C |\n"
                "+---+---+---+")
        view = EditingView(text, text.index('A') + 1)
        plugin.TableEditorNextRow(view).run(None)
        caret = view.sel()[0].begin()
        view.insert(None, caret, 'letters')
        view.selections[:] = [Region(caret + len('letters'))]

        plugin.TableEditorNextField(view).run(None)

        import table_grid_model
        grid = table_grid_model.GridDocument.from_text(view.text)
        self.assertEqual(1, len(grid.logical_row_ranges()))
        row, column = view.rowcol(view.sel()[0].begin())
        self.assertEqual(2, row)
        self.assertEqual(1, grid.field_at_column(row, column))

    def test_enter_after_growing_first_cell_continues_its_list(self):
        plugin = load_plugin()
        text = ("+---+---+---+\n"
                "| A | B | C |\n"
                "+---+---+---+")
        view = EditingView(text, text.index('A') + 1)
        plugin.TableEditorNextRow(view).run(None)
        caret = view.sel()[0].begin()
        view.insert(None, caret, '- one')
        view.selections[:] = [Region(caret + len('- one'))]

        plugin.TableEditorNextRow(view).run(None)

        import table_grid_model
        grid = table_grid_model.GridDocument.from_text(view.text)
        first = next(cell for cell in grid.cells if cell.x0 == 0)
        self.assertEqual(['A', '- one', '-'], first.rows)

    def test_manual_multiline_colspan_remains_in_grid_context(self):
        plugin, text = self._manually_merged_readme_grid()
        view = EditingView(text, text.index('sdf') + 3)

        self.assertTrue(plugin._is_grid_content(view, text.index('sdf')))
        self.assertTrue(plugin._is_grid_content(
            view, text.index('|        |') + 2))

    def test_enter_normalizes_manual_multiline_colspan(self):
        plugin, text = self._manually_merged_readme_grid()
        point = text.index('|        |') + 2
        view = EditingView(text, point)

        plugin.TableEditorNextRow(view).run(None)

        import table_grid_model
        grid = table_grid_model.GridDocument.from_text(view.text)
        cells = dict((cell.bounds(), cell.rows) for cell in grid.cells)
        self.assertEqual(['', ''], cells[(0, 3, 2, 4)])
        self.assertIn((0, 0, 2, 1), cells)
        self.assertIn((0, 1, 1, 3), cells)
        self.assertIn('+---------+', view.text)
        self.assertEqual(1, len(set(map(len, view.text.splitlines()))))

    def test_enter_after_typing_in_manual_multiline_colspan(self):
        plugin, text = self._manually_merged_readme_grid()
        point = text.index('|        |') + 2
        view = EditingView(text, point)
        view.insert(None, point, 'letters')
        view.selections[:] = [Region(point + len('letters'))]

        plugin.TableEditorNextRow(view).run(None)

        import table_grid_model
        grid = table_grid_model.GridDocument.from_text(view.text)
        cells = dict((cell.bounds(), cell.rows) for cell in grid.cells)
        self.assertEqual(['letters', ''], cells[(0, 3, 2, 4)])
        self.assertIn((0, 0, 2, 1), cells)
        self.assertIn((0, 1, 1, 3), cells)
        self.assertEqual(1, len(set(map(len, view.text.splitlines()))))

    def test_tab_normalizes_manual_colspan_from_preceding_cell(self):
        plugin, text = self._manually_merged_readme_grid()
        point = text.index('sdf') + 3
        view = EditingView(text, point)

        plugin.TableEditorNextField(view).run(None)

        import table_grid_model
        grid = table_grid_model.GridDocument.from_text(view.text)
        cells = dict((cell.bounds(), cell.rows) for cell in grid.cells)
        self.assertEqual([''], cells[(0, 3, 2, 4)])
        self.assertIn((0, 1, 1, 3), cells)
        self.assertEqual(1, len(set(map(len, view.text.splitlines()))))

    def test_tab_normalizes_manually_split_colspan(self):
        plugin = load_plugin()
        text = ("+---+-----+\n"
                "| A | B   |\n"
                "+---+-----+\n"
                "|   |      |\n"
                "+---+------+")
        point = text.index('|   |      |') + 5
        view = EditingView(text, point)

        plugin.TableEditorNextField(view).run(None)

        import table_grid_model
        grid = table_grid_model.GridDocument.from_text(view.text)
        cells = dict((cell.bounds(), cell.rows) for cell in grid.cells)
        self.assertEqual([''], cells[(0, 1, 1, 2)])
        self.assertEqual([''], cells[(1, 1, 2, 2)])
        self.assertIn('+---+-----+', view.text)
        self.assertEqual(1, len(set(map(len, view.text.splitlines()))))

    def test_insert_command_merges_once_and_moves_the_caret(self):
        plugin = load_plugin()
        text = "+---------+\n| - one   |\n+---------+"
        view = EditingView(text, text.index('one'))

        plugin.TableEditorInsertCellRow(view).run(None)

        import table_grid
        import table_lib
        table = table_lib.pandoc_syntax().table_parser.parse_text(view.text)
        self.assertEqual(["- one", "-"],
                         table_grid.GridTable(table).cell_rows(0, 0))
        self.assertEqual(2, view.rowcol(view.sel()[0].begin())[0])

    def test_insert_command_targets_cell_containing_literal_pipe(self):
        plugin = load_plugin()
        text = ("+----------+----------+\n"
                "| - x|y    | z        |\n"
                "+----------+----------+")
        view = EditingView(text, text.index('y'))

        plugin.TableEditorInsertCellRow(view).run(None)

        import table_grid
        import table_lib
        table = table_lib.pandoc_syntax().table_parser.parse_text(view.text)
        grid = table_grid.GridTable(table)
        self.assertEqual(['- x|y', '-'], grid.cell_rows(0, 0))
        self.assertEqual(['z', ''], grid.cell_rows(0, 1))

    def test_insert_command_targets_cell_containing_escaped_pipe(self):
        plugin = load_plugin()
        text = ("+----------+----------+\n"
                "| - x\\|y   | z        |\n"
                "+----------+----------+")
        view = EditingView(text, text.index('y'))

        plugin.TableEditorInsertCellRow(view).run(None)

        import table_grid
        import table_lib
        table = table_lib.pandoc_syntax().table_parser.parse_text(view.text)
        grid = table_grid.GridTable(table)
        self.assertEqual(['- x\\|y', '-'], grid.cell_rows(0, 0))
        self.assertEqual(['z', ''], grid.cell_rows(0, 1))

    def test_insert_command_targets_restructured_text_substitution_cell(self):
        plugin = load_plugin()
        text = "+----------+\n| |name|   |\n+----------+"
        view = EditingView(text, text.index('name'))
        view.settings()['table_editor_syntax'] = 'reStructuredText'

        plugin.TableEditorInsertCellRow(view).run(None)

        import table_grid
        import table_lib
        table = table_lib.re_structured_text_syntax().table_parser.parse_text(
            view.text)
        self.assertEqual(['|name|', ''],
                         table_grid.GridTable(table).cell_rows(0, 0))

    def test_indent_selection_stays_in_cell_containing_literal_pipe(self):
        plugin = load_plugin()
        text = ("+----------+---+\n"
                "| - x|y    | z |\n"
                "+----------+---+")
        start = text.index('- x')
        view = EditingView(text, start)
        view.selections[:] = [Region(start, text.index('y') + 1)]

        plugin.TableEditorIndentCellRows(view).run(None)

        import table_grid
        import table_lib
        table = table_lib.pandoc_syntax().table_parser.parse_text(view.text)
        self.assertEqual(['    - x|y'],
                         table_grid.GridTable(table).cell_rows(0, 0))

    def test_palette_cell_command_outside_table_reports_error(self):
        plugin = load_plugin()
        view = EditingView("ordinary text", 3)

        plugin.TableEditorInsertCellRow(view).run(None)

        self.assertEqual("ordinary text", view.text)
        self.assertTrue(plugin.sublime.status_messages)

    def test_palette_selection_command_outside_table_reports_error(self):
        plugin = load_plugin()
        view = EditingView("ordinary text", 0)
        view.selections[:] = [Region(0, 8)]

        plugin.TableEditorIndentCellRows(view).run(None)

        self.assertEqual("ordinary text", view.text)
        self.assertTrue(plugin.sublime.status_messages)

    def test_split_column_rejects_complete_grid_before_editing(self):
        plugin = load_plugin()
        text = "+---+---+\n| A | B |\n+---+---+"
        view = EditingView(text, text.index('A'))

        plugin.TableEditorSplitColumnDown(view).run(None)

        self.assertEqual(text, view.text)
        self.assertTrue(plugin.sublime.status_messages)

    def test_failed_command_on_border_retains_exact_caret(self):
        plugin = load_plugin()
        text = "+---+\n| A |\n+---+"
        point = text.index('-') + 1
        view = EditingView(text, point)

        plugin.TableEditorInsertSingleHline(view).run(None)

        self.assertEqual(text, view.text)
        self.assertEqual((point, point),
                         (view.sel()[0].begin(), view.sel()[0].end()))
        self.assertTrue(plugin.sublime.status_messages)

    def test_failed_command_retains_nonempty_selection(self):
        plugin = load_plugin()
        text = "+---+\n| A |\n+---+"
        start = text.index('A')
        view = EditingView(text, start)
        view.selections[:] = [Region(start, start + 1)]

        plugin.TableEditorInsertSingleHline(view).run(None)

        self.assertEqual(text, view.text)
        self.assertEqual((start, start + 1),
                         (view.sel()[0].begin(), view.sel()[0].end()))
        self.assertTrue(plugin.sublime.status_messages)


class LogicalRowCommandTest(unittest.TestCase):

    def test_rejects_multiple_carets_in_complete_grid(self):
        plugin = load_plugin()
        text = ("+---+---+\n"
                "| A | B |\n"
                "+---+---+\n"
                "| C | D |\n"
                "+---+---+")
        view = EditingView(text, text.index('A'))
        view.selections[:] = [Region(text.index('A')), Region(text.index('B'))]

        plugin.TableEditorMoveRowDown(view).run(None)

        self.assertEqual(text, view.text)
        self.assertEqual(2, len(view.sel()))
        self.assertTrue(plugin.sublime.status_messages)

    def test_rejects_multiple_carets_when_rowspan_has_partial_separator(self):
        plugin = load_plugin()
        text = ("+---+---+\n"
                "| A | B |\n"
                "|   +---+\n"
                "| C | D |\n"
                "+---+---+")
        view = EditingView(text, text.index('A'))
        view.selections[:] = [Region(text.index('A')), Region(text.index('B'))]

        plugin.TableEditorMoveRowDown(view).run(None)

        self.assertEqual(text, view.text)
        self.assertEqual(2, len(view.sel()))
        self.assertTrue(plugin.sublime.status_messages)


class ColumnCommandSafetyTest(unittest.TestCase):

    def assert_rejects_multiple_carets(self, command_name):
        plugin = load_plugin()
        text = ("+---+---+---+\n"
                "| A | B | C |\n"
                "+---+---+---+")
        selections = [Region(text.index('A')), Region(text.index('B'))]
        view = EditingView(text, selections[0].begin())
        view.selections[:] = selections

        getattr(plugin, command_name)(view).run(None)

        self.assertEqual(text, view.text)
        self.assertEqual(
            [(selection.begin(), selection.end()) for selection in selections],
            [(selection.begin(), selection.end()) for selection in view.sel()])
        self.assertTrue(plugin.sublime.status_messages)

    def test_move_left_rejects_multiple_grid_carets(self):
        self.assert_rejects_multiple_carets('TableEditorMoveColumnLeft')

    def test_move_right_rejects_multiple_grid_carets(self):
        self.assert_rejects_multiple_carets('TableEditorMoveColumnRight')

    def test_delete_rejects_multiple_grid_carets(self):
        self.assert_rejects_multiple_carets('TableEditorDeleteColumn')

    def test_insert_rejects_multiple_grid_carets(self):
        self.assert_rejects_multiple_carets('TableEditorInsertColumn')


class SingleCaretGridCommandTest(unittest.TestCase):

    def test_rejects_multiple_carets_before_running_operation(self):
        plugin = load_plugin()

        class ProbeCommand(plugin.SingleCaretGridCommand):
            def run_one_sel(self, unused_edit, unused_selection):
                raise AssertionError("operation must not run")

        view = CommandView([Region(0), Region(1)])

        ProbeCommand(view).run(None)

        self.assertEqual(2, len(view.sel()))

    def test_rejects_non_empty_selection_before_running_operation(self):
        plugin = load_plugin()

        class ProbeCommand(plugin.SingleCaretGridCommand):
            def run_one_sel(self, unused_edit, unused_selection):
                raise AssertionError("operation must not run")

        view = CommandView([Region(0, 1)])

        ProbeCommand(view).run(None)

        self.assertEqual(1, len(view.sel()))
