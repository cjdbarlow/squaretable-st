import json
from pathlib import Path
import re
import unittest
import warnings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KEYMAPS = [
    PROJECT_ROOT / 'Default (Linux).sublime-keymap',
    PROJECT_ROOT / 'Default (OSX).sublime-keymap',
    PROJECT_ROOT / 'Default (Windows).sublime-keymap',
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
        entries = load_json_with_comments(
            PROJECT_ROOT / 'Default.sublime-commands')
        commands = {entry['command'] for entry in entries}
        self.assertTrue(CELL_COMMANDS <= commands)

    def test_command_palette_uses_squaretable_caption_prefix(self):
        entries = load_json_with_comments(
            PROJECT_ROOT / 'Default.sublime-commands')

        self.assertTrue(entries)
        self.assertTrue(all(
            entry['caption'].startswith('SquareTable: ')
            for entry in entries))

    def test_command_palette_omits_demo_film(self):
        entries = load_json_with_comments(
            PROJECT_ROOT / 'Default.sublime-commands')

        self.assertNotIn(
            'table_editor_film',
            {entry['command'] for entry in entries})

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

    def test_grid_tab_navigation_requires_an_empty_selection(self):
        for path in KEYMAPS:
            bindings = load_json_with_comments(path)
            navigation = [binding for binding in bindings
                          if binding['command'] in (
                              'table_editor_next_field',
                              'table_editor_previous_field')]
            self.assertTrue(navigation)
            for binding in navigation:
                if context_value(
                        binding, 'table_editor_multiline_grid') is False:
                    continue
                self.assertIs(
                    True, context_value(binding, 'selection_empty'),
                    '{0}: {1}'.format(path, binding['command']))

    def test_grid_enter_navigation_requires_an_empty_selection(self):
        for path in KEYMAPS:
            bindings = load_json_with_comments(path)
            navigation = [binding for binding in bindings
                          if binding['command'] == 'table_editor_next_row']
            self.assertTrue(navigation)
            for binding in navigation:
                if context_value(
                        binding, 'table_editor_multiline_grid') is False:
                    continue
                self.assertIs(
                    True, context_value(binding, 'selection_empty'), path)

    def test_selected_legacy_navigation_remains_bound_outside_grid(self):
        commands = {
            'table_editor_next_field',
            'table_editor_previous_field',
            'table_editor_next_row',
        }
        for path in KEYMAPS:
            bindings = load_json_with_comments(path)
            for command in commands:
                matches = [
                    binding for binding in bindings
                    if binding['command'] == command and
                    context_value(binding, 'selection_empty') is False and
                    context_value(binding,
                                  'table_editor_multiline_grid') is False
                ]
                self.assertGreaterEqual(
                    len(matches), 2,
                    '{0}: selected {1}'.format(path, command))

    def test_plugin_compiles_without_syntax_warnings(self):
        path = PROJECT_ROOT / 'table_plugin.py'
        with open(path, encoding='utf-8') as stream:
            source = stream.read()
        with warnings.catch_warnings():
            warnings.simplefilter('error', SyntaxWarning)
            compile(source, str(path), 'exec')

    def test_preferences_menu_uses_squaretable_package_path(self):
        menu = load_json_with_comments(PROJECT_ROOT / 'Main.sublime-menu')

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
