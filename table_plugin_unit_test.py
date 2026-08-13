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
    sublime.status_message = lambda unused_message: None
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


class CellCommandIntegrationTest(unittest.TestCase):

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
