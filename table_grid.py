try:
    from . import table_base as tbase
    from . import table_border_syntax as tborder
    from . import table_grid_model as tmodel
except (ImportError, ValueError):
    import table_base as tbase
    import table_border_syntax as tborder
    import table_grid_model as tmodel


GridPosition = tmodel.GridPosition


def _is_number(value):
    try:
        float(value)
        return True
    except ValueError:
        return False


def is_grid_header_separator(row):
    return not tborder.is_grid_table(row.table) or row.separator == '='


class GridLogicalRow(object):

    def __init__(self, data_rows, bottom_separator):
        self.data_rows = data_rows
        self.bottom_separator = bottom_separator


class GridTable(object):

    def __init__(self, table):
        self.table = table
        source_text = table.source_text
        if source_text is None:
            source_text = table.render()
        self.document = tmodel.GridDocument.from_text(source_text)
        self.top_separator = tborder.SeparatorRow(table, '-')
        self.logical_rows = []
        self._refresh_compatibility_rows()

    def position(self, table_pos):
        return self.document.position(table_pos)

    def table_position(self, grid_pos):
        return self.document.table_position(grid_pos)

    def cell_rows(self, logical_row, field_num):
        position = self.document.resolve_position(
            GridPosition(logical_row, 0, field_num))
        return list(self.document.cells[position.cell_id].rows)

    def insert_cell_row(self, grid_pos):
        result = self.document.insert_cell_row(grid_pos)
        self._refresh_compatibility_rows()
        return result

    def delete_cell_row(self, grid_pos):
        result = self.document.delete_cell_row(grid_pos)
        self._refresh_compatibility_rows()
        return result

    def move_cell_row(self, grid_pos, offset):
        return self.document.move_cell_row(grid_pos, offset)

    def indent_cell_rows(self, start, end, indent):
        return self.document.indent_cell_rows(start, end, indent)

    def outdent_cell_rows(self, start, end, tab_size):
        return self.document.outdent_cell_rows(start, end, tab_size)

    def next_field(self, grid_pos):
        result = self.document.next_field(grid_pos)
        self._refresh_compatibility_rows()
        return result

    def previous_field(self, grid_pos):
        return self.document.previous_field(grid_pos)

    def next_field_from(self, table_pos):
        return self.document.next_field_from(table_pos)

    def previous_field_from(self, table_pos):
        return self.document.previous_field_from(table_pos)

    def position_near(self, table_pos, prefer='below'):
        return self.document.position_near(table_pos, prefer)

    def move_column(self, grid_pos, offset):
        return self.document.move_column(grid_pos, offset)

    def insert_column(self, grid_pos):
        return self.document.insert_column(grid_pos)

    def delete_column(self, grid_pos):
        return self.document.delete_column(grid_pos)

    def move_logical_row(self, grid_pos, offset):
        result = self.document.move_logical_row(grid_pos, offset)
        self._refresh_compatibility_rows()
        return result

    def insert_logical_row(self, grid_pos):
        result = self.document.insert_logical_row(grid_pos)
        self._refresh_compatibility_rows()
        return result

    def delete_logical_row(self, grid_pos):
        result = self.document.delete_logical_row(grid_pos)
        self._refresh_compatibility_rows()
        return result

    def commit(self):
        rendered = self.document.render_lines(self._cell_alignments())
        self.table.set_render_lines(rendered)
        self.table.source_text = '\n'.join(rendered)

    def _cell_alignments(self):
        alignments = {}
        header_boundary = None
        if self.table.syntax.detect_header:
            for boundary in range(1, len(self.document.horizontal_edges) - 1):
                edges = self.document.horizontal_edges[boundary]
                if edges and all(edge == '=' for edge in edges):
                    header_boundary = boundary
                    break
        if header_boundary is not None:
            for cell in self.document.cells:
                if cell.y1 <= header_boundary:
                    alignments[cell.id] = 'center'

        if self.table.syntax.align_number_right:
            body_start = header_boundary if header_boundary is not None else 0
            for column in range(len(self.document.column_widths)):
                cells = [cell for cell in self.document.cells
                         if cell.x0 == column and cell.y0 >= body_start]
                values = [value for cell in cells for value in cell.rows
                          if value.strip()]
                if values and all(_is_number(value) for value in values):
                    for cell in cells:
                        alignments[cell.id] = 'right'
        return alignments

    def _refresh_compatibility_rows(self):
        self.logical_rows = []
        column_count = len(self.document.column_widths)
        for unused_index, (start, end) in enumerate(
                self.document.logical_row_ranges()):
            rows = []
            row_count = sum(self.document.bands[index].height
                            for index in range(start, end))
            for unused_row in range(row_count):
                row = tbase.DataRow(self.table)
                for unused_column in range(column_count):
                    column = row.new_empty_column()
                    column.header = False
                    row.columns.append(column)
                rows.append(row)
            separator_style = self.document.horizontal_edges[end][0]
            self.logical_rows.append(GridLogicalRow(
                rows, tborder.SeparatorRow(
                    self.table, separator_style or '-')))


class GridTableDriver(tborder.BorderTableDriver):

    supports_multiline_grid = True

    def _document(self, table):
        source_text = table.source_text
        if source_text is None:
            source_text = table.render()
        return tmodel.GridDocument.try_from_text(source_text)

    def is_complete_grid(self, table):
        return self._document(table) is not None

    def _apply(self, table, table_pos, operation, resolver=None):
        grid = GridTable(table)
        grid_pos = (resolver(grid, table_pos) if resolver is not None
                    else grid.position(table_pos))
        message, new_grid_pos = operation(grid, grid_pos)
        grid.commit()
        return message, grid.table_position(new_grid_pos)

    def _apply_or_fallback(self, table, table_pos, operation, fallback):
        if self._document(table) is None:
            return fallback(table, table_pos)
        return self._apply(table, table_pos, operation)

    def _unsupported_or_fallback(self, table, table_pos, fallback, name):
        if self._document(table) is None:
            return fallback(table, table_pos)
        raise tbase.TableException(
            '{0} is not available for bordered grid tables'.format(name))

    def visual_to_internal_index(self, table, visual_pos):
        if self._document(table) is not None:
            return tbase.TablePos(visual_pos.row_num, visual_pos.field_num)
        return super(GridTableDriver, self).visual_to_internal_index(
            table, visual_pos)

    def internal_to_visual_index(self, table, internal_pos):
        if self._document(table) is not None:
            return tbase.TablePos(internal_pos.row_num, internal_pos.field_num)
        return super(GridTableDriver, self).internal_to_visual_index(
            table, internal_pos)

    def get_cursor(self, table, visual_pos):
        document = self._document(table)
        if document is not None:
            return document.cursor_column(visual_pos)
        return super(GridTableDriver, self).get_cursor(table, visual_pos)

    def visual_field_at_column(self, table, row_num, line_text, column):
        try:
            document = self._document(table)
        except tbase.TableException:
            source_text = table.source_text
            if source_text is None:
                source_text = table.render()
            document, field_num = tmodel.GridDocument.editing_document_at(
                source_text, row_num, column)
            rendered = document.render_lines()
            table.source_text = '\n'.join(rendered)
            table.set_render_lines(rendered)
            return field_num
        if document is not None:
            return document.field_at_column(row_num, column)
        return super(GridTableDriver, self).visual_field_at_column(
            table, row_num, line_text, column)

    def editor_align(self, table, table_pos):
        if self._document(table) is None:
            return super(GridTableDriver, self).editor_align(
                table, table_pos)
        grid = GridTable(table)
        grid.commit()
        return 'Table aligned', table_pos

    def editor_next_row(self, table, table_pos):
        if self._document(table) is None:
            return super(GridTableDriver, self).editor_next_row(
                table, table_pos)
        return self._apply(
            table, table_pos,
            lambda grid, pos: ('Cell row inserted',
                               grid.insert_cell_row(pos)),
            lambda grid, pos: grid.position_near(pos, 'below'))

    def editor_next_field(self, table, table_pos):
        if self._document(table) is None:
            return super(GridTableDriver, self).editor_next_field(
                table, table_pos)
        grid = GridTable(table)
        result = grid.next_field_from(table_pos)
        grid.commit()
        return 'Cursor position changed', grid.table_position(result)

    def editor_previous_field(self, table, table_pos):
        if self._document(table) is None:
            return super(GridTableDriver, self).editor_previous_field(
                table, table_pos)
        grid = GridTable(table)
        result = grid.previous_field_from(table_pos)
        grid.commit()
        return 'Cursor position changed', grid.table_position(result)

    def editor_insert_cell_row(self, table, table_pos):
        return self._apply(
            table, table_pos,
            lambda grid, pos: ('Cell row inserted',
                               grid.insert_cell_row(pos)))

    def editor_delete_cell_row(self, table, table_pos):
        return self._apply(
            table, table_pos,
            lambda grid, pos: ('Cell row deleted',
                               grid.delete_cell_row(pos)))

    def editor_move_cell_row_up(self, table, table_pos):
        return self._apply(
            table, table_pos,
            lambda grid, pos: ('Cell row moved up',
                               grid.move_cell_row(pos, -1)))

    def editor_move_cell_row_down(self, table, table_pos):
        return self._apply(
            table, table_pos,
            lambda grid, pos: ('Cell row moved down',
                               grid.move_cell_row(pos, 1)))

    def editor_indent_cell_rows(self, table, start_pos, end_pos, indent):
        return self._apply_range(
            table, start_pos, end_pos,
            lambda grid, start, end: (
                'Cell rows indented',
                grid.indent_cell_rows(start, end, indent)))

    def editor_outdent_cell_rows(self, table, start_pos, end_pos, tab_size):
        return self._apply_range(
            table, start_pos, end_pos,
            lambda grid, start, end: (
                'Cell rows outdented',
                grid.outdent_cell_rows(start, end, tab_size)))

    def editor_move_row_up(self, table, table_pos):
        if self._document(table) is None:
            return super(GridTableDriver, self).editor_move_row_up(
                table, table_pos)
        return self._apply(
            table, table_pos,
            lambda grid, pos: ('Logical row moved up',
                               grid.move_logical_row(pos, -1)),
            lambda grid, pos: grid.position_near(pos, 'below'))

    def editor_move_row_down(self, table, table_pos):
        if self._document(table) is None:
            return super(GridTableDriver, self).editor_move_row_down(
                table, table_pos)
        return self._apply(
            table, table_pos,
            lambda grid, pos: ('Logical row moved down',
                               grid.move_logical_row(pos, 1)),
            lambda grid, pos: grid.position_near(pos, 'below'))

    def editor_insert_row(self, table, table_pos):
        if self._document(table) is None:
            return super(GridTableDriver, self).editor_insert_row(
                table, table_pos)
        return self._apply(
            table, table_pos,
            lambda grid, pos: ('Logical row inserted',
                               grid.insert_logical_row(pos)),
            lambda grid, pos: grid.position_near(pos, 'below'))

    def editor_kill_row(self, table, table_pos):
        if self._document(table) is None:
            return super(GridTableDriver, self).editor_kill_row(
                table, table_pos)
        return self._apply(
            table, table_pos,
            lambda grid, pos: ('Logical row deleted',
                               grid.delete_logical_row(pos)),
            lambda grid, pos: grid.position_near(pos, 'below'))

    def editor_move_column_left(self, table, table_pos):
        return self._apply_or_fallback(
            table, table_pos,
            lambda grid, pos: ('Column moved to left',
                               grid.move_column(pos, -1)),
            super(GridTableDriver, self).editor_move_column_left)

    def editor_move_column_right(self, table, table_pos):
        return self._apply_or_fallback(
            table, table_pos,
            lambda grid, pos: ('Column moved to right',
                               grid.move_column(pos, 1)),
            super(GridTableDriver, self).editor_move_column_right)

    def editor_delete_column(self, table, table_pos):
        return self._apply_or_fallback(
            table, table_pos,
            lambda grid, pos: ('Column deleted',
                               grid.delete_column(pos)),
            super(GridTableDriver, self).editor_delete_column)

    def editor_insert_column(self, table, table_pos):
        return self._apply_or_fallback(
            table, table_pos,
            lambda grid, pos: ('Column inserted',
                               grid.insert_column(pos)),
            super(GridTableDriver, self).editor_insert_column)

    def editor_insert_single_hline(self, table, table_pos):
        return self._unsupported_or_fallback(
            table, table_pos,
            super(GridTableDriver, self).editor_insert_single_hline,
            'Insert horizontal line')

    def editor_insert_double_hline(self, table, table_pos):
        return self._unsupported_or_fallback(
            table, table_pos,
            super(GridTableDriver, self).editor_insert_double_hline,
            'Insert header line')

    def editor_insert_hline_and_move(self, table, table_pos):
        return self._unsupported_or_fallback(
            table, table_pos,
            super(GridTableDriver, self).editor_insert_hline_and_move,
            'Insert horizontal line and move')

    def editor_join_lines(self, table, table_pos):
        return self._unsupported_or_fallback(
            table, table_pos,
            super(GridTableDriver, self).editor_join_lines,
            'Join lines')

    def _apply_range(self, table, start_pos, end_pos, operation):
        grid = GridTable(table)
        start = grid.position(start_pos)
        end = grid.position(end_pos)
        message, new_grid_pos = operation(grid, start, end)
        grid.commit()
        return message, grid.table_position(new_grid_pos)
