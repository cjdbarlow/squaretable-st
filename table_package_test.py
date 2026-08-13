import json
import re
import subprocess
import sys
import unittest


KEYMAPS = [
    'Default (Linux).sublime-keymap',
    'Default (OSX).sublime-keymap',
    'Default (Windows).sublime-keymap',
]

CELL_COMMANDS = {
    'table_editor_insert_cell_row',
    'table_editor_delete_cell_row',
    'table_editor_move_cell_row_up',
    'table_editor_move_cell_row_down',
    'table_editor_indent_cell_rows',
    'table_editor_outdent_cell_rows',
}


def load_json_with_comments(path):
    with open(path, encoding='utf-8') as stream:
        text = re.sub(r'^\s*//.*$', '', stream.read(), flags=re.MULTILINE)
    return json.loads(text)


def context_value(binding, key):
    for context in binding.get('context', []):
        if context.get('key') == key:
            return context.get('operand')
    return None


class PackageMetadataTest(unittest.TestCase):

    def test_command_palette_exposes_all_cell_commands(self):
        entries = load_json_with_comments('Default.sublime-commands')
        commands = {entry['command'] for entry in entries}
        self.assertTrue(CELL_COMMANDS <= commands)

    def test_each_platform_binds_cell_commands(self):
        expected = {
            ('ctrl+alt+shift+down',): 'table_editor_insert_cell_row',
            ('ctrl+alt+shift+up',): 'table_editor_delete_cell_row',
            ('ctrl+alt+up',): 'table_editor_move_cell_row_up',
            ('ctrl+alt+down',): 'table_editor_move_cell_row_down',
            ('tab',): 'table_editor_indent_cell_rows',
            ('shift+tab',): 'table_editor_outdent_cell_rows',
        }
        for path in KEYMAPS:
            bindings = load_json_with_comments(path)
            for keys, command in expected.items():
                matches = [binding for binding in bindings
                           if tuple(binding['keys']) == keys and
                           binding['command'] == command]
                self.assertTrue(matches, '{0}: {1}'.format(path, command))
                self.assertTrue(any(
                    context_value(binding, 'table_editor_multiline_grid') is True
                    for binding in matches))

    def test_tab_navigation_requires_an_empty_selection(self):
        for path in KEYMAPS:
            bindings = load_json_with_comments(path)
            navigation = [binding for binding in bindings
                          if binding['command'] in (
                              'table_editor_next_field',
                              'table_editor_previous_field')]
            self.assertTrue(navigation)
            for binding in navigation:
                self.assertIs(
                    True, context_value(binding, 'selection_empty'),
                    '{0}: {1}'.format(path, binding['command']))

    def test_enter_navigation_requires_an_empty_selection(self):
        for path in KEYMAPS:
            bindings = load_json_with_comments(path)
            navigation = [binding for binding in bindings
                          if binding['command'] == 'table_editor_next_row']
            self.assertTrue(navigation)
            for binding in navigation:
                self.assertIs(
                    True, context_value(binding, 'selection_empty'), path)

    def test_plugin_compiles_without_syntax_warnings(self):
        result = subprocess.run(
            [sys.executable, '-W', 'error::SyntaxWarning', '-m', 'py_compile',
             'table_plugin.py'],
            capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_preferences_menu_uses_squaretable_package_path(self):
        menu = load_json_with_comments('Main.sublime-menu')

        def walk(items):
            for item in items:
                yield item
                for child in walk(item.get('children', [])):
                    yield child

        paths = [item.get('args', {}).get('file') for item in walk(menu)
                 if item.get('args', {}).get('file')]
        self.assertTrue(paths)
        self.assertTrue(all(path.startswith('${packages}/SquareTable/')
                            for path in paths))
