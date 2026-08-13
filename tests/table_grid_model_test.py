import unittest

try:
    from .. import table_base as tbase
    from .. import table_grid_model as model
    from ..widechar_support import wlen
except (ImportError, ValueError):
    import table_base as tbase
    import table_grid_model as model
    from widechar_support import wlen


ROWSPAN_FIXTURE = r"""+--------------------------+---------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------+
| Factor                   | Effect                                                                                                                                      | Detail                                                                                                       |
+==========================+=============================================================================================================================================+==============================================================================================================+
| **Age**                  | BMR ↓ as age ↑                                                                                                                              | Neonates have a BMR twice that of an adult\                                                                  |
|                          |                                                                                                                                             +--------------------------------------------------------------------------------------------------------------+
|                          |                                                                                                                                             | Children have an ↑ BMR relative to that of an adult\                                                         |
|                          |                                                                                                                                             +--------------------------------------------------------------------------------------------------------------+
|                          |                                                                                                                                             | BMR ↓ by 2% for each decade of life                                                                          |
+--------------------------+---------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------+
| **Body Composition**     | Lean muscle has a greater energy requirement than fat                                                                                       | Higher body fat percentage results in a lower BMR\                                                           |
|                          |                                                                                                                                             +--------------------------------------------------------------------------------------------------------------+
|                          |                                                                                                                                             | Females have a lower BMR for this reason alone                                                               |
+--------------------------+---------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------+
| **Diet**                 | The **specific dynamic action** of food describes the ↑ metabolic rate in metabolic rate due to the energy required to assimilate nutrients | Generally ~10% ↑ in BMR\                                                                                     |
|                          |                                                                                                                                             +--------------------------------------------------------------------------------------------------------------+
|                          |                                                                                                                                             | Protein > carbohydrate > fat\                                                                                |
|                          |                                                                                                                                             +--------------------------------------------------------------------------------------------------------------+
|                          |                                                                                                                                             | Specific Dynamic Action for each macromolecule is not related to the respiratory quotient for that food type |
+--------------------------+---------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------+
| **Exercise**             | Skeletal muscle is the largest and most variable source of energy consumption                                                               |                                                                                                              |
+--------------------------+---------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------+
| **Environment**          | Cooler environments ↑ BMR\                                                                                                                  |                                                                                                              |
|                          +---------------------------------------------------------------------------------------------------------------------------------------------+                                                                                                              |
|                          | Temperate environments ↓ BMR up to 10%                                                                                                      |                                                                                                              |
+--------------------------+---------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------+
| **Physiological state**s | Pregnancy ↑ BMR up to 20% in 2nd and 3rd trimester\                                                                                         |                                                                                                              |
|                          +---------------------------------------------------------------------------------------------------------------------------------------------+                                                                                                              |
|                          | Lactation ↑ BMR\                                                                                                                            |                                                                                                              |
|                          +---------------------------------------------------------------------------------------------------------------------------------------------+                                                                                                              |
|                          | Catecholamines ↑ metabolic rate                                                                                                             |                                                                                                              |
|                          +---------------------------------------------------------------------------------------------------------------------------------------------+                                                                                                              |
|                          | Corticosteroids ↑ metabolic rate                                                                                                             |                                                                                                              |
+--------------------------+---------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------+
| **Disease states**       | Malignancy ↑ metabolic rate\                                                                                                                |                                                                                                              |
|                          +---------------------------------------------------------------------------------------------------------------------------------------------+                                                                                                              |
|                          | Sepsis ↑ metabolic rate\                                                                                                                    |                                                                                                              |
|                          +---------------------------------------------------------------------------------------------------------------------------------------------+                                                                                                              |
|                          | Hyperthyroidism ↑ metabolic rate                                                                                                             |                                                                                                              |
+--------------------------+---------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------+"""
ROWSPAN_FIXTURE = ROWSPAN_FIXTURE.replace(
    ' Corticosteroids ↑ metabolic rate' + ' ' * 109 + '|',
    ' Corticosteroids ↑ metabolic rate' + ' ' * 108 + '|').replace(
        ' Hyperthyroidism ↑ metabolic rate' + ' ' * 109 + '|',
        ' Hyperthyroidism ↑ metabolic rate' + ' ' * 108 + '|')

PANDOC_SPAN_FIXTURE = """\
+---------------------+----------+
| Property            | Earth    |
+=============+=======+==========+
|             | min   | -89.2 °C |
| Temperature +-------+----------+
| 1961-1990   | mean  | 14 °C    |
|             +-------+----------+
|             | max   | 56.7 °C  |
+-------------+-------+----------+"""


class GridGeometryParseTest(unittest.TestCase):

    def test_infers_four_ordinary_cells(self):
        grid = model.GridDocument.from_text("""\
+---+---+
| A | B |
+---+---+
| C | D |
+---+---+""")

        self.assertEqual(
            [(0, 0, 1, 1), (1, 0, 2, 1),
             (0, 1, 1, 2), (1, 1, 2, 2)],
            [cell.bounds() for cell in grid.cells])

    def test_missing_vertical_edge_declares_colspan(self):
        grid = model.GridDocument.from_text("""\
+----+----+
| merged  |
+----+----+""")

        self.assertEqual([(0, 0, 2, 1)],
                         [cell.bounds() for cell in grid.cells])
        self.assertEqual(["merged"], grid.cells[0].rows)

    def test_missing_horizontal_segment_declares_rowspan(self):
        grid = model.GridDocument.from_text("""\
+---+---+
| A | B |
|   +---+
|   | D |
+---+---+""")

        self.assertIn((0, 0, 1, 2),
                      [cell.bounds() for cell in grid.cells])

    def test_combines_rowspan_and_colspan(self):
        grid = model.GridDocument.from_text("""\
+---+---+---+
| A     | B |
|       +---+
|       | C |
+---+---+---+""")

        self.assertIn((0, 0, 2, 2),
                      [cell.bounds() for cell in grid.cells])

    def test_rejects_non_rectangular_connected_component(self):
        with self.assertRaises(tbase.TableException):
            model.GridDocument.from_text("""\
+---+---+
| A     |
|   +---+
|   | B |
+---+---+""")

    def test_try_from_text_returns_none_for_pipe_and_incomplete_tables(self):
        self.assertIsNone(model.GridDocument.try_from_text('| A | B |'))
        self.assertIsNone(model.GridDocument.try_from_text('+---+\n| A |'))

    def test_try_from_text_keeps_malformed_complete_grid_as_error(self):
        with self.assertRaises(tbase.TableException):
            model.GridDocument.try_from_text("""\
+---+---+
| A     |
|   +---+
|   | B |
+---+---+""")

    def test_discovers_atomic_boundaries_below_spanning_top_cell(self):
        grid = model.GridDocument.from_text(PANDOC_SPAN_FIXTURE)

        self.assertEqual(3, len(grid.column_widths))
        self.assertIn((0, 0, 2, 1),
                      [cell.bounds() for cell in grid.cells])
        temperature = next(
            cell for cell in grid.cells
            if cell.bounds() == (0, 1, 1, 4))
        self.assertIn('Temperature', temperature.rows)

    def test_shifted_structural_boundary_is_rejected_not_guessed(self):
        with self.assertRaises(tbase.TableException):
            model.GridDocument.from_text("""\
+---+---+
| long value | B |
+---+---+""")

    def test_missing_edge_anchor_is_rejected(self):
        with self.assertRaises(tbase.TableException):
            model.GridDocument.from_text("""\
+---+---+
| A | B |
|   |---+
| C | D |
+---+---+""")


class GridEditingRecoveryTest(unittest.TestCase):

    def test_recovers_boundary_deletion_from_edited_top_border(self):
        edited = """\
+------+
| A  B |
+---+---+
| C | D |
+---+---+"""

        grid, unused_field = model.GridDocument.editing_document_at(
            edited, 1, 3)

        self.assertIn((0, 0, 2, 1),
                      [cell.bounds() for cell in grid.cells])
        model.GridDocument.from_text(grid.render())

    def test_recovers_boundary_insertion_from_edited_top_border(self):
        edited = """\
+---+----+
| A |    |
+---+---+
| C | D |
+---+---+"""

        grid, unused_field = model.GridDocument.editing_document_at(
            edited, 1, 2)

        cells = [cell.bounds() for cell in grid.cells]
        self.assertIn((0, 0, 1, 1), cells)
        self.assertIn((1, 0, 2, 1), cells)
        model.GridDocument.from_text(grid.render())

    def test_recovers_boundary_deletion_at_each_internal_coordinate(self):
        canonical = [
            '+---+---+---+',
            '| A | B | C |',
            '+---+---+---+',
            '| D | E | F |',
            '+---+---+---+',
        ]

        for boundary, expected_span in (
                (4, (0, 1, 2, 2)),
                (8, (1, 1, 3, 2))):
            with self.subTest(boundary=boundary):
                edited = list(canonical)
                for row in (2, 3, 4):
                    edited[row] = (edited[row][:boundary] +
                                   edited[row][boundary + 1:])

                with self.assertRaises(tbase.TableException):
                    model.GridDocument.from_text('\n'.join(edited))
                grid, unused_field = model.GridDocument.editing_document_at(
                    '\n'.join(edited), 3, boundary)

                reparsed = model.GridDocument.from_text(grid.render())
                self.assertIn(expected_span,
                              [cell.bounds() for cell in reparsed.cells])
                self.assertEqual(
                    1, len(set(wlen(line)
                               for line in grid.render_lines())))

    def test_recovers_typed_content_after_each_boundary_deletion(self):
        canonical = [
            '+---+---+---+',
            '| A | B | C |',
            '+---+---+---+',
            '| D | E | F |',
            '+---+---+---+',
        ]

        for boundary, label, expected_span in (
                (4, 'D', (0, 1, 2, 2)),
                (8, 'E', (1, 1, 3, 2))):
            with self.subTest(boundary=boundary):
                edited = list(canonical)
                for row in (2, 3, 4):
                    edited[row] = (edited[row][:boundary] +
                                   edited[row][boundary + 1:])
                insertion = edited[3].index(label) + 1
                edited[3] = (edited[3][:insertion] + 'letters' +
                             edited[3][insertion:])

                grid, unused_field = model.GridDocument.editing_document_at(
                    '\n'.join(edited), 3, insertion + len('letters'))

                merged = next(cell for cell in grid.cells
                              if cell.bounds() == expected_span)
                self.assertIn(label + 'letters', merged.rows[0])
                model.GridDocument.from_text(grid.render())

    def test_recovers_boundary_insertion_to_split_colspan(self):
        edited = """\
+---+-----+
| A | B   |
+---+-----+
|   |      |
+---+------+"""

        grid, unused_field = model.GridDocument.editing_document_at(
            edited, 3, 2)

        cells = dict((cell.bounds(), cell.rows) for cell in grid.cells)
        self.assertEqual([''], cells[(0, 1, 1, 2)])
        self.assertEqual([''], cells[(1, 1, 2, 2)])
        model.GridDocument.from_text(grid.render())

    def test_single_line_growth_recovers_every_field_and_content_kind(self):
        canonical = [
            '+---+---+---+',
            '| A | B | C |',
            '+---+---+---+',
        ]
        addition = r'long|\|漢字'

        for field, label in enumerate('ABC'):
            with self.subTest(field=field):
                edited = list(canonical)
                index = edited[1].index(label) + 1
                edited[1] = (edited[1][:index] + addition +
                             edited[1][index:])
                column = index + len(addition)

                grid, recovered_field = (
                    model.GridDocument.editing_document_at(
                        '\n'.join(edited), 1, column))

                self.assertEqual(field, recovered_field)
                self.assertEqual(
                    label + addition, grid.cells[field].rows[0])
                self.assertEqual(
                    1, len(set(wlen(line)
                               for line in grid.render_lines())))

    def test_preserves_literal_and_escaped_pipes_in_recovered_colspan(self):
        canonical = [
            '+----------+----------+',
            '| A        | B        |',
            '+----------+----------+',
            r'| x|y      | z\|w     |',
            '+----------+----------+',
        ]
        boundary = 11
        edited = list(canonical)
        for row in (2, 3, 4):
            edited[row] = (edited[row][:boundary] +
                           edited[row][boundary + 1:])

        grid, unused_field = model.GridDocument.editing_document_at(
            '\n'.join(edited), 1, 2)

        merged = next(cell for cell in grid.cells
                      if cell.bounds() == (0, 1, 2, 2))
        self.assertIn('x|y', merged.rows[0])
        self.assertIn(r'z\|w', merged.rows[0])

    def test_rejects_inconsistent_multiline_boundary_edits(self):
        edited = """\
+---+---+
| A | B |
+------+
| C  D |
+---+----+"""

        with self.assertRaises(tbase.TableException):
            model.GridDocument.from_editing_text(edited, 3, 3)

    def test_rejects_border_deletions_without_content_boundary_edit(self):
        edited = """\
+---+---+
| A | B |
+------+
| C | D |
+------+"""

        with self.assertRaises(tbase.TableException):
            model.GridDocument.from_editing_text(edited, 3, 3)

    def test_rejects_content_deletion_beside_boundary(self):
        edited = """\
+---+---+
| A | B |
+------+
| C| D |
+------+"""

        with self.assertRaises(tbase.TableException):
            model.GridDocument.from_editing_text(edited, 3, 3)


class GridGeometryRenderTest(unittest.TestCase):

    def assert_round_trip(self, text):
        self.assertEqual(text, model.GridDocument.from_text(text).render())

    def test_round_trips_simple_colspan(self):
        self.assert_round_trip("""\
+----+----+
| merged  |
+----+----+""")

    def test_round_trips_supplied_multi_rowspan_table(self):
        self.assert_round_trip(ROWSPAN_FIXTURE)

    def test_round_trips_pandoc_canonical_spanning_header_table(self):
        self.assert_round_trip(PANDOC_SPAN_FIXTURE)

    def test_preserves_raw_pipe_inside_cell_content(self):
        self.assert_round_trip("""\
+----------+----------+
| x|y      | z        |
+----------+----------+""")

    def test_preserves_escaped_pipe_inside_cell_content(self):
        self.assert_round_trip(r"""+----------+----------+
| x\|y     | z        |
+----------+----------+""")

    def test_preserves_restructured_text_substitution_reference(self):
        self.assert_round_trip("""\
+----------+
| |name|   |
+----------+""")

    def test_preserves_plus_dash_sequence_inside_cell_content(self):
        self.assert_round_trip("""\
+-----------------+
| foo +---+ bar   |
+-----------------+""")

    def test_pipe_wrapped_dashes_remain_cell_content(self):
        grid = model.GridDocument.from_text("""\
+---+
|---|
+---+""")

        self.assertEqual(['---'], grid.cells[0].rows)
        self.assertEqual("+-----+\n| --- |\n+-----+", grid.render())

    def test_unrelated_plus_does_not_turn_dashes_into_an_edge(self):
        grid = model.GridDocument.from_text("""\
+---+---+
|---|a+ |
+---+---+""")

        self.assertEqual([['---'], ['a+']],
                         [cell.rows for cell in grid.cells])
        self.assertEqual("+-----+----+\n| --- | a+ |\n+-----+----+",
                         grid.render())

    def test_manual_vertical_edge_removal_and_restore_changes_colspan(self):
        merged = """\
+---+---+
| A     |
+---+---+
| C | D |
+---+---+"""
        restored = """\
+---+---+
| A |   |
+---+---+
| C | D |
+---+---+"""

        merged_cells = model.GridDocument.from_text(merged).cells
        restored_cells = model.GridDocument.from_text(restored).cells

        self.assertIn((0, 0, 2, 1),
                      [cell.bounds() for cell in merged_cells])
        self.assertNotIn((0, 0, 2, 1),
                         [cell.bounds() for cell in restored_cells])

    def test_manual_horizontal_edge_removal_and_restore_changes_rowspan(self):
        merged = """\
+---+---+
| A | B |
|   +---+
| C | D |
+---+---+"""
        restored = """\
+---+---+
| A | B |
+---+---+
| C | D |
+---+---+"""

        merged_cells = model.GridDocument.from_text(merged).cells
        restored_cells = model.GridDocument.from_text(restored).cells

        self.assertIn((0, 0, 1, 2),
                      [cell.bounds() for cell in merged_cells])
        self.assertNotIn((0, 0, 1, 2),
                         [cell.bounds() for cell in restored_cells])

    def test_expands_rightmost_covered_column_for_wide_content(self):
        grid = model.GridDocument.from_text("""\
+----+----+
| 漢字    |
+----+----+""")
        grid.cells[0].rows[0] = '漢字漢字漢字'

        widths = [wlen(line) for line in grid.render_lines()]

        self.assertEqual(1, len(set(widths)))
        self.assertGreater(widths[0], 11)

class GridPositionTest(unittest.TestCase):

    def test_rows_separated_only_in_another_cell_share_one_rowspan(self):
        grid = model.GridDocument.from_text("""\
+---+---+
| A | B |
|   +---+
| C | D |
+---+---+""")

        first = grid.position(tbase.TablePos(1, 0))
        second = grid.position(tbase.TablePos(3, 0))

        self.assertEqual(first.cell_id, second.cell_id)
        self.assertEqual((0, 1), (first.slot_index, second.slot_index))


class GridCellOperationTest(unittest.TestCase):

    def parse_rowspan(self):
        return model.GridDocument.from_text("""\
+---+---+
| A | B |
|   +---+
| C | D |
+---+---+""")

    def test_insert_inside_rowspan_preserves_partial_separator(self):
        grid = self.parse_rowspan()
        position = grid.position(tbase.TablePos(1, 0))

        result = grid.insert_cell_row(position)

        self.assertEqual(['A', '', 'C'],
                         grid.cells[position.cell_id].rows)
        self.assertEqual(tbase.TablePos(2, 0), grid.table_position(result))
        self.assertEqual('|   +---+', grid.render_lines()[3])
        self.assertEqual(['B', ''],
                         next(cell.rows for cell in grid.cells
                              if cell.bounds() == (1, 0, 2, 1)))

    def test_move_inside_rowspan_crosses_other_cells_separator(self):
        grid = self.parse_rowspan()
        position = grid.position(tbase.TablePos(3, 0))

        result = grid.move_cell_row(position, -1)

        self.assertEqual(['C', 'A'], grid.cells[position.cell_id].rows)
        self.assertEqual(tbase.TablePos(1, 0), grid.table_position(result))
        self.assertEqual('|   +---+', grid.render_lines()[2])

    def test_delete_shifts_only_active_cell_when_other_cell_uses_height(self):
        grid = model.GridDocument.from_text("""\
+---+---+
| A | 1 |
| B | 2 |
| C | 3 |
+---+---+""")
        position = grid.position(tbase.TablePos(2, 0))

        result = grid.delete_cell_row(position)

        self.assertEqual(['A', 'C', ''],
                         grid.cells[position.cell_id].rows)
        self.assertEqual(['1', '2', '3'],
                         next(cell.rows for cell in grid.cells
                              if cell.bounds() == (1, 0, 2, 1)))
        self.assertEqual(tbase.TablePos(2, 0), grid.table_position(result))

    def test_delete_contracts_blank_trailing_line_across_band(self):
        grid = model.GridDocument.from_text("""\
+---+---+
| A | 1 |
| B | 2 |
| C |   |
+---+---+""")
        position = grid.position(tbase.TablePos(2, 0))

        grid.delete_cell_row(position)

        self.assertEqual(2, grid.bands[0].height)
        self.assertEqual(['A', 'C'], grid.cells[position.cell_id].rows)
        self.assertEqual(['1', '2'],
                         next(cell.rows for cell in grid.cells
                              if cell.bounds() == (1, 0, 2, 1)))

    def test_delete_does_not_contract_another_band_in_rowspan(self):
        grid = model.GridDocument.from_text("""\
+---+---+
| A | 1 |
|   |   |
|   +---+
| C | 2 |
| D | 3 |
+---+---+""")
        position = grid.position(tbase.TablePos(4, 0))

        grid.delete_cell_row(position)

        self.assertEqual([2, 2], [band.height for band in grid.bands])
        self.assertEqual(['A', '', 'D', ''],
                         grid.cells[position.cell_id].rows)

    def test_deleting_only_cell_row_leaves_empty_cell(self):
        grid = model.GridDocument.from_text("""\
+---+
| A |
+---+""")
        position = grid.position(tbase.TablePos(1, 0))

        grid.delete_cell_row(position)

        self.assertEqual([''], grid.cells[0].rows)
        self.assertEqual(1, grid.bands[0].height)

    def test_indents_list_rows_across_partial_separator_in_same_rowspan(self):
        grid = model.GridDocument.from_text("""\
+---------+---+
| - one   | B |
|         +---+
| - two   | D |
+---------+---+""")
        start = grid.position(tbase.TablePos(1, 0))
        end = grid.position(tbase.TablePos(3, 0))

        grid.indent_cell_rows(start, end, '    ')

        self.assertEqual(['    - one', '    - two'],
                         grid.cells[start.cell_id].rows)

    def test_rejects_selection_across_different_cells(self):
        grid = self.parse_rowspan()
        start = grid.position(tbase.TablePos(1, 0))
        end = grid.position(tbase.TablePos(1, 1))

        with self.assertRaises(tbase.TableException):
            grid.indent_cell_rows(start, end, '    ')


class GridNavigationTest(unittest.TestCase):

    def test_navigation_uses_physical_reading_order_through_rowspan(self):
        grid = model.GridDocument.from_text("""\
+---+---+
| A | B |
|   +---+
| C | D |
+---+---+""")
        position = grid.position(tbase.TablePos(1, 0))

        visited = []
        for unused_index in range(3):
            position = grid.next_field(position)
            visited.append(grid.table_position(position))

        self.assertEqual(
            [tbase.TablePos(1, 1), tbase.TablePos(3, 0),
             tbase.TablePos(3, 1)],
            visited)
        for expected in reversed([
                tbase.TablePos(1, 0), tbase.TablePos(1, 1),
                tbase.TablePos(3, 0)]):
            position = grid.previous_field(position)
            self.assertEqual(expected, grid.table_position(position))
