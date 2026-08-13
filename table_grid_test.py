import unittest

import table_base as tbase
import table_grid
import table_lib


class GridTableTest(unittest.TestCase):

    def setUp(self):
        self.syntax = table_lib.pandoc_syntax()

    def parse(self, text):
        return self.syntax.table_parser.parse_text(text)

    def test_groups_physical_lines_into_logical_rows(self):
        table = self.parse("""\
+-------+---------+
| Alice | - One   |
| note  | - Two   |
+-------+---------+
| Bob   | - Three |
+-------+---------+""")

        grid = table_grid.GridTable(table)

        self.assertEqual(2, len(grid.logical_rows))
        self.assertEqual(2, len(grid.logical_rows[0].data_rows))
        self.assertEqual(1, len(grid.logical_rows[1].data_rows))

    def test_maps_between_physical_and_grid_positions(self):
        table = self.parse("""\
+-------+---------+
| Alice | - One   |
| note  | - Two   |
+-------+---------+
| Bob   | - Three |
+-------+---------+""")
        grid = table_grid.GridTable(table)
        grid_pos = table_grid.GridPosition(0, 1, 1)

        self.assertEqual(grid_pos, grid.position(tbase.TablePos(2, 1)))
        self.assertEqual(tbase.TablePos(2, 1),
                         grid.table_position(grid_pos))

    def test_rejects_missing_top_border(self):
        table = self.parse("""\
| value |
+-------+""")
        with self.assertRaises(tbase.TableException):
            table_grid.GridTable(table)

    def test_rejects_consecutive_borders(self):
        table = self.parse("""\
+-------+
+-------+""")
        with self.assertRaises(tbase.TableException):
            table_grid.GridTable(table)

    def test_rejects_missing_bottom_border(self):
        table = self.parse("""\
+-------+
| value |""")
        with self.assertRaises(tbase.TableException):
            table_grid.GridTable(table)

    def test_separator_text_inside_a_grid_cell_remains_content(self):
        table = self.parse("""\
+-----+
| --- |
+-----+""")

        grid = table_grid.GridTable(table)

        self.assertEqual(["---"], grid.cell_rows(0, 0))

    def test_preserves_nested_list_indentation(self):
        table = self.parse("""\
+--------------+
| Header       |
+==============+
| - root       |
|     - nested |
+--------------+""")
        grid = table_grid.GridTable(table)

        self.assertEqual(["- root", "    - nested"],
                         grid.cell_rows(1, 0))
        grid.commit()
        self.assertIn("|     - nested |", table.render())

    def test_shared_model_round_trips_both_grid_syntaxes(self):
        text = """\
+---------+
| - root  |
|   - sub |
+---------+"""
        factories = (table_lib.pandoc_syntax,
                     table_lib.re_structured_text_syntax)

        for factory in factories:
            with self.subTest(syntax=factory().__class__.__name__):
                syntax = factory()
                table = syntax.table_parser.parse_text(text)
                syntax.table_driver.editor_insert_cell_row(
                    table, tbase.TablePos(1, 0))
                reparsed = table_grid.GridTable(
                    syntax.table_parser.parse_text(table.render()))
                self.assertEqual(["- root", "-", "  - sub"],
                                 reparsed.cell_rows(0, 0))

    def test_grid_alignment_is_idempotent(self):
        text = """\
+--------+
| - root |
|   - sub|
+--------+"""

        for factory in (table_lib.pandoc_syntax,
                        table_lib.re_structured_text_syntax):
            syntax = factory()
            first = syntax.table_parser.parse_text(text).render()
            second = syntax.table_parser.parse_text(first).render()
            self.assertEqual(first, second)


class GridOperationTest(unittest.TestCase):

    def parse_grid(self, text):
        syntax = table_lib.pandoc_syntax()
        table = syntax.table_parser.parse_text(text)
        return table_grid.GridTable(table)


class GridCellInsertTest(GridOperationTest):

    def test_inserts_list_row_without_moving_other_cells(self):
        grid = self.parse_grid("""\
+-------+-------+
| Alice | - One |
| note  | - Two |
+-------+-------+""")

        result = grid.insert_cell_row(table_grid.GridPosition(0, 0, 1))

        self.assertEqual(table_grid.GridPosition(0, 1, 1), result)
        self.assertEqual(["- One", "-", "- Two"],
                         grid.cell_rows(0, 1))
        self.assertEqual(["Alice", "note", ""], grid.cell_rows(0, 0))

    def test_inserts_empty_row_after_ordinary_text(self):
        grid = self.parse_grid("""\
+-------+-------+
| Alice | First |
| note  | Next  |
+-------+-------+""")

        grid.insert_cell_row(table_grid.GridPosition(0, 0, 1))

        self.assertEqual(["First", "", "Next"], grid.cell_rows(0, 1))
        self.assertEqual(["Alice", "note", ""], grid.cell_rows(0, 0))

    def test_inserts_unchecked_task(self):
        grid = self.parse_grid("""\
+-------------+
| - [x] done  |
+-------------+""")

        grid.insert_cell_row(table_grid.GridPosition(0, 0, 0))

        self.assertEqual(["- [x] done", "- [ ]"], grid.cell_rows(0, 0))

    def test_inserts_and_renumbers_ordered_item(self):
        grid = self.parse_grid("""\
+----------+
| 4. four  |
| 9. five  |
+----------+""")

        grid.insert_cell_row(table_grid.GridPosition(0, 0, 0))

        self.assertEqual(["4. four", "5.", "6. five"],
                         grid.cell_rows(0, 0))


class GridCellDeleteTest(GridOperationTest):

    def test_closes_gap_without_moving_other_cell_content(self):
        grid = self.parse_grid("""\
+-------+---------+
| Alice | - One   |
| note  | - Two   |
|       | - Three |
+-------+---------+""")

        result = grid.delete_cell_row(table_grid.GridPosition(0, 1, 1))

        self.assertEqual(table_grid.GridPosition(0, 1, 1), result)
        self.assertEqual(["- One", "- Three"], grid.cell_rows(0, 1))
        self.assertEqual(["Alice", "note"], grid.cell_rows(0, 0))

    def test_keeps_height_when_another_cell_uses_trailing_row(self):
        grid = self.parse_grid("""\
+-------+---------+
| Alice | - One   |
| note  | - Two   |
| tail  | - Three |
+-------+---------+""")

        grid.delete_cell_row(table_grid.GridPosition(0, 1, 1))

        self.assertEqual(["- One", "- Three", ""],
                         grid.cell_rows(0, 1))
        self.assertEqual(["Alice", "note", "tail"],
                         grid.cell_rows(0, 0))

    def test_deleting_only_row_leaves_empty_cell(self):
        grid = self.parse_grid("""\
+-------+-------+
| Alice | Only  |
+-------+-------+""")

        grid.delete_cell_row(table_grid.GridPosition(0, 0, 1))

        self.assertEqual(["Alice"], grid.cell_rows(0, 0))
        self.assertEqual([""], grid.cell_rows(0, 1))

    def test_deleting_first_ordered_item_preserves_list_start(self):
        grid = self.parse_grid("""\
+---------+
| 4. four |
| 5. five |
| 6. six  |
+---------+""")

        grid.delete_cell_row(table_grid.GridPosition(0, 0, 0))

        self.assertEqual(["4. five", "5. six"], grid.cell_rows(0, 0))


class GridCellMoveTest(GridOperationTest):

    def test_moves_up_without_moving_other_cell_content(self):
        grid = self.parse_grid("""\
+-------+---------+
| Alice | - One   |
| note  | - Two   |
|       | - Three |
+-------+---------+""")

        result = grid.move_cell_row(table_grid.GridPosition(0, 1, 1), -1)

        self.assertEqual(table_grid.GridPosition(0, 0, 1), result)
        self.assertEqual(["- Two", "- One", "- Three"],
                         grid.cell_rows(0, 1))
        self.assertEqual(["Alice", "note", ""], grid.cell_rows(0, 0))

    def test_moves_down(self):
        grid = self.parse_grid("""\
+---------+
| - One   |
| - Two   |
+---------+""")

        result = grid.move_cell_row(table_grid.GridPosition(0, 0, 0), 1)

        self.assertEqual(table_grid.GridPosition(0, 1, 0), result)
        self.assertEqual(["- Two", "- One"], grid.cell_rows(0, 0))

    def test_move_renumbers_from_original_list_start(self):
        grid = self.parse_grid("""\
+---------+
| 4. four |
| 5. five |
| 6. six  |
+---------+""")

        grid.move_cell_row(table_grid.GridPosition(0, 1, 0), -1)

        self.assertEqual(["4. five", "5. four", "6. six"],
                         grid.cell_rows(0, 0))

    def test_rejects_move_above_cell_boundary_without_mutation(self):
        grid = self.parse_grid("""\
+-------+
| first |
| next  |
+-------+""")
        before = grid.cell_rows(0, 0)

        with self.assertRaises(tbase.TableException):
            grid.move_cell_row(table_grid.GridPosition(0, 0, 0), -1)

        self.assertEqual(before, grid.cell_rows(0, 0))

    def test_rejects_move_below_cell_boundary_without_mutation(self):
        grid = self.parse_grid("""\
+-------+
| first |
| next  |
+-------+""")
        before = grid.cell_rows(0, 0)

        with self.assertRaises(tbase.TableException):
            grid.move_cell_row(table_grid.GridPosition(0, 1, 0), 1)

        self.assertEqual(before, grid.cell_rows(0, 0))


class GridCellIndentTest(GridOperationTest):

    def test_indents_selected_rows_in_one_cell(self):
        grid = self.parse_grid("""\
+-------+---------+
| Alice | - One   |
| note  | - Two   |
| tail  | - Three |
+-------+---------+""")

        result = grid.indent_cell_rows(
            table_grid.GridPosition(0, 1, 1),
            table_grid.GridPosition(0, 2, 1),
            "    ")

        self.assertEqual(table_grid.GridPosition(0, 1, 1), result)
        self.assertEqual(["- One", "    - Two", "    - Three"],
                         grid.cell_rows(0, 1))
        self.assertEqual(["Alice", "note", "tail"],
                         grid.cell_rows(0, 0))

    def test_outdents_and_renumbers_selected_ordered_rows(self):
        grid = self.parse_grid("""\
+----------------+
| 1. root        |
|     7. nested  |
|     9. nested  |
| 2. next        |
+----------------+""")

        grid.outdent_cell_rows(
            table_grid.GridPosition(0, 1, 0),
            table_grid.GridPosition(0, 2, 0),
            4)

        self.assertEqual(
            ["1. root", "2. nested", "3. nested", "4. next"],
            grid.cell_rows(0, 0))

    def test_outdent_at_root_is_no_op(self):
        grid = self.parse_grid("""\
+-------+
| - one |
+-------+""")

        grid.outdent_cell_rows(
            table_grid.GridPosition(0, 0, 0),
            table_grid.GridPosition(0, 0, 0),
            4)

        self.assertEqual(["- one"], grid.cell_rows(0, 0))

    def test_rejects_selection_crossing_cells_before_mutation(self):
        grid = self.parse_grid("""\
+-------+-------+
| - one | - two |
+-------+-------+""")
        before = [grid.cell_rows(0, 0), grid.cell_rows(0, 1)]

        with self.assertRaises(tbase.TableException):
            grid.indent_cell_rows(
                table_grid.GridPosition(0, 0, 0),
                table_grid.GridPosition(0, 0, 1),
                "    ")

        self.assertEqual(before,
                         [grid.cell_rows(0, 0), grid.cell_rows(0, 1)])

    def test_rejects_selection_crossing_logical_rows_before_mutation(self):
        grid = self.parse_grid("""\
+-------+
| - one |
+-------+
| - two |
+-------+""")
        before = [grid.cell_rows(0, 0), grid.cell_rows(1, 0)]

        with self.assertRaises(tbase.TableException):
            grid.indent_cell_rows(
                table_grid.GridPosition(0, 0, 0),
                table_grid.GridPosition(1, 0, 0),
                "    ")

        self.assertEqual(before,
                         [grid.cell_rows(0, 0), grid.cell_rows(1, 0)])


class GridLogicalRowDriverTest(GridOperationTest):

    def setUp(self):
        self.syntax = table_lib.pandoc_syntax()
        self.driver = table_grid.GridTableDriver(self.syntax)

    def parse_table(self, text):
        return self.syntax.table_parser.parse_text(text)

    def test_moves_complete_multiline_logical_row_down(self):
        table = self.parse_table("""\
+------+------+
| A    | a1   |
| A2   | a2   |
+------+------+
| B    | b1   |
+------+------+""")

        unused_message, position = self.driver.editor_move_row_down(
            table, tbase.TablePos(1, 0))

        grid = table_grid.GridTable(table)
        self.assertEqual(["B"], grid.cell_rows(0, 0))
        self.assertEqual(["A", "A2"], grid.cell_rows(1, 0))
        self.assertEqual(tbase.TablePos(3, 0), position)

    def test_move_carries_the_logical_rows_bottom_separator(self):
        table = self.parse_table("""\
+---+
| A |
+---+
| H |
+===+
| B |
+---+""")

        self.driver.editor_move_row_up(table, tbase.TablePos(3, 0))

        grid = table_grid.GridTable(table)
        self.assertEqual(["H"], grid.cell_rows(0, 0))
        self.assertEqual('=', grid.logical_rows[0].bottom_separator.separator)
        self.assertEqual(["A"], grid.cell_rows(1, 0))
        self.assertEqual('-', grid.logical_rows[1].bottom_separator.separator)

    def test_move_cannot_cross_header_border(self):
        table = self.parse_table("""\
+--------+
| Header |
+========+
| value  |
+--------+""")
        before = table.render()

        with self.assertRaises(tbase.TableException):
            self.driver.editor_move_row_down(table, tbase.TablePos(1, 0))

        self.assertEqual(before, table.render())

    def test_inserts_blank_logical_row_before_current_row(self):
        table = self.parse_table("""\
+-------+
| value |
+-------+""")

        unused_message, position = self.driver.editor_insert_row(
            table, tbase.TablePos(1, 0))

        grid = table_grid.GridTable(table)
        self.assertEqual(2, len(grid.logical_rows))
        self.assertEqual([""], grid.cell_rows(0, 0))
        self.assertEqual(["value"], grid.cell_rows(1, 0))
        self.assertEqual(tbase.TablePos(1, 0), position)

    def test_deletes_complete_logical_row(self):
        table = self.parse_table("""\
+-------+
| first |
| line  |
+-------+
| next  |
+-------+""")

        unused_message, position = self.driver.editor_kill_row(
            table, tbase.TablePos(1, 0))

        grid = table_grid.GridTable(table)
        self.assertEqual(1, len(grid.logical_rows))
        self.assertEqual(["next"], grid.cell_rows(0, 0))
        self.assertEqual(tbase.TablePos(1, 0), position)

    def test_delete_removes_the_logical_rows_header_separator(self):
        table = self.parse_table("""\
+--------+
| Header |
+========+
| body   |
+--------+""")
        self.driver.editor_insert_row(table, tbase.TablePos(1, 0))
        table.rows[1][0].data = '     - nested'
        table.pack()

        self.driver.editor_kill_row(table, tbase.TablePos(3, 0))

        grid = table_grid.GridTable(table)
        self.assertEqual(["    - nested", "body"],
                         [grid.cell_rows(row, 0)[0] for row in range(2)])
        self.assertEqual(['-', '-'],
                         [row.bottom_separator.separator
                          for row in grid.logical_rows])
        self.assertFalse(any(
            column.header
            for row in grid.logical_rows
            for data_row in row.data_rows
            for column in data_row.columns))
        self.assertEqual(1, len(set(map(len, table.render_lines()))))

    def test_deleting_only_logical_row_leaves_blank_row(self):
        table = self.parse_table("""\
+-------+
| value |
+-------+""")

        self.driver.editor_kill_row(table, tbase.TablePos(1, 0))

        grid = table_grid.GridTable(table)
        self.assertEqual(1, len(grid.logical_rows))
        self.assertEqual([""], grid.cell_rows(0, 0))

    def test_next_row_delegates_to_cell_insertion(self):
        table = self.parse_table("""\
+-------+
| - one |
+-------+""")

        unused_message, position = self.driver.editor_next_row(
            table, tbase.TablePos(1, 0))

        grid = table_grid.GridTable(table)
        self.assertEqual(["- one", "-"], grid.cell_rows(0, 0))
        self.assertEqual(tbase.TablePos(2, 0), position)

    def test_only_enhanced_syntaxes_select_grid_driver(self):
        self.assertIsInstance(table_lib.pandoc_syntax().table_driver,
                              table_grid.GridTableDriver)
        self.assertIsInstance(table_lib.re_structured_text_syntax().table_driver,
                              table_grid.GridTableDriver)
        self.assertNotIsInstance(table_lib.simple_syntax().table_driver,
                                 table_grid.GridTableDriver)

    def test_next_field_appends_logical_row_inside_outer_border(self):
        table = self.parse_table("""\
+-------+-------+
| first | last  |
+-------+-------+""")

        unused_message, position = self.driver.editor_next_field(
            table, tbase.TablePos(1, 1))

        grid = table_grid.GridTable(table)
        self.assertEqual(2, len(grid.logical_rows))
        self.assertEqual(["", ""],
                         [grid.cell_rows(1, field)[0]
                          for field in range(2)])
        self.assertEqual(tbase.TablePos(3, 0), position)

    def test_next_field_keeps_header_separator_above_appended_row(self):
        table = self.parse_table("""\
+--------+
| Header |
+========+""")

        self.driver.editor_next_field(table, tbase.TablePos(1, 0))

        grid = table_grid.GridTable(table)
        self.assertEqual('=', grid.logical_rows[0].bottom_separator.separator)
        self.assertEqual('-', grid.logical_rows[1].bottom_separator.separator)

    def test_field_navigation_moves_between_existing_cell_rows(self):
        table = self.parse_table("""\
+-------+-------+
| one   | two   |
| three | four  |
+-------+-------+""")

        unused_message, next_position = self.driver.editor_next_field(
            table, tbase.TablePos(1, 1))
        unused_message, previous_position = self.driver.editor_previous_field(
            table, next_position)

        self.assertEqual(tbase.TablePos(2, 0), next_position)
        self.assertEqual(tbase.TablePos(1, 1), previous_position)

    def test_previous_field_at_start_stays_in_first_cell(self):
        table = self.parse_table("""\
+-------+
| value |
+-------+""")

        unused_message, position = self.driver.editor_previous_field(
            table, tbase.TablePos(1, 0))

        self.assertEqual(tbase.TablePos(1, 0), position)


class PandocPipeCompatibilityTest(unittest.TestCase):

    def setUp(self):
        self.syntax = table_lib.pandoc_syntax()
        self.driver = self.syntax.table_driver

    def parse_table(self):
        return self.syntax.table_parser.parse_text("""\
| A | B |
| C | D |""")

    def test_field_navigation_uses_existing_pipe_table_behavior(self):
        table = self.parse_table()

        unused_message, position = self.driver.editor_next_field(
            table, tbase.TablePos(0, 1))

        self.assertEqual(tbase.TablePos(1, 0), position)

    def test_enter_uses_existing_pipe_table_behavior(self):
        table = self.parse_table()

        unused_message, position = self.driver.editor_next_row(
            table, tbase.TablePos(1, 0))

        self.assertEqual(3, len(table.rows))
        self.assertEqual(tbase.TablePos(2, 0), position)

    def test_row_commands_use_existing_pipe_table_behavior(self):
        table = self.parse_table()

        unused_message, position = self.driver.editor_move_row_down(
            table, tbase.TablePos(0, 0))

        self.assertEqual("C", table.rows[0][0].data.strip())
        self.assertEqual(tbase.TablePos(1, 0), position)
