try:
    from . import table_base as tbase
    from . import table_border_syntax as tborder
    from . import table_list as tlist
except (ImportError, ValueError):
    import table_base as tbase
    import table_border_syntax as tborder
    import table_list as tlist


def is_grid_header_separator(row):
    return not tborder.is_grid_table(row.table) or row.separator == '='


class GridPosition(object):

    def __init__(self, logical_row, cell_row, field_num):
        self.logical_row = logical_row
        self.cell_row = cell_row
        self.field_num = field_num

    def __eq__(self, other):
        return (isinstance(other, GridPosition) and
                self.logical_row == other.logical_row and
                self.cell_row == other.cell_row and
                self.field_num == other.field_num)

    def __repr__(self):
        return "GridPosition({0}, {1}, {2})".format(
            self.logical_row, self.cell_row, self.field_num)


class GridLogicalRow(object):

    def __init__(self, data_rows, bottom_separator):
        self.data_rows = data_rows
        self.bottom_separator = bottom_separator


class GridTable(object):

    def __init__(self, table):
        self.table = table
        self.top_separator = None
        self.logical_rows = []
        self._parse()

    def _parse(self):
        rows = self.table.rows
        tbase.check_condition(
            rows and isinstance(rows[0], tborder.SeparatorRow),
            "Grid table must start with a horizontal border")

        self.top_separator = rows[0]
        data_rows = []
        for row in rows[1:]:
            if isinstance(row, tborder.SeparatorRow):
                tbase.check_condition(
                    data_rows,
                    "Grid table borders must contain a logical row")
                self.logical_rows.append(GridLogicalRow(data_rows, row))
                data_rows = []
            else:
                tbase.check_condition(row.is_data(),
                                      "Grid table contains an invalid row")
                data_rows.append(row)

        tbase.check_condition(not data_rows,
                              "Grid table must end with a horizontal border")
        tbase.check_condition(self.logical_rows,
                              "Grid table must contain a logical row")

    def position(self, table_pos):
        physical_row = 1
        for logical_index, logical_row in enumerate(self.logical_rows):
            row_count = len(logical_row.data_rows)
            if physical_row <= table_pos.row_num < physical_row + row_count:
                cell_row = table_pos.row_num - physical_row
                self._validate_field(logical_index, table_pos.field_num)
                return GridPosition(logical_index, cell_row,
                                    table_pos.field_num)
            physical_row += row_count + 1
        raise tbase.TableException("Expected a grid-table cell row")

    def table_position(self, grid_pos):
        self._validate_position(grid_pos)
        physical_row = 1
        for logical_index in range(grid_pos.logical_row):
            physical_row += len(self.logical_rows[logical_index].data_rows) + 1
        return tbase.TablePos(physical_row + grid_pos.cell_row,
                              grid_pos.field_num)

    def cell_rows(self, logical_row, field_num):
        self._validate_field(logical_row, field_num)
        return [self._cell_text(row[field_num])
                for row in self.logical_rows[logical_row].data_rows]

    def insert_cell_row(self, grid_pos):
        self._validate_position(grid_pos)
        cells = self._cell_matrix(grid_pos.logical_row)
        values = cells[grid_pos.field_num]
        preserved_start = tlist.ordered_list_start(
            values, grid_pos.cell_row)
        continuation = tlist.continuation_for(values[grid_pos.cell_row])
        insert_at = grid_pos.cell_row + 1
        values.insert(insert_at, continuation or '')
        cells[grid_pos.field_num] = tlist.renumber_ordered_list(
            values, insert_at, preserved_start)
        self._write_cells(grid_pos.logical_row, cells)
        return GridPosition(grid_pos.logical_row, insert_at,
                            grid_pos.field_num)

    def delete_cell_row(self, grid_pos):
        self._validate_position(grid_pos)
        cells = self._cell_matrix(grid_pos.logical_row)
        values = cells[grid_pos.field_num]
        preserved_start = tlist.ordered_list_start(
            values, grid_pos.cell_row)

        if len(values) == 1:
            values[0] = ''
        else:
            del values[grid_pos.cell_row]

        cell_row = min(grid_pos.cell_row, len(values) - 1)
        cells[grid_pos.field_num] = tlist.renumber_ordered_list(
            values, cell_row, preserved_start)
        cells = self._trim_blank_tail(cells)
        self._write_cells(grid_pos.logical_row, cells)
        height = len(self.logical_rows[grid_pos.logical_row].data_rows)
        return GridPosition(grid_pos.logical_row,
                            min(cell_row, height - 1),
                            grid_pos.field_num)

    def move_cell_row(self, grid_pos, offset):
        self._validate_position(grid_pos)
        tbase.check_condition(offset in (-1, 1),
                              "Cell row offset must be -1 or 1")
        target = grid_pos.cell_row + offset
        rows = self.logical_rows[grid_pos.logical_row].data_rows
        tbase.check_condition(0 <= target < len(rows),
                              "Cannot move beyond the current cell")

        cells = self._cell_matrix(grid_pos.logical_row)
        values = cells[grid_pos.field_num]
        preserved_start = tlist.ordered_list_start(
            values, grid_pos.cell_row)
        values[grid_pos.cell_row], values[target] = (
            values[target], values[grid_pos.cell_row])
        cells[grid_pos.field_num] = tlist.renumber_ordered_list(
            values, target, preserved_start)
        self._write_cells(grid_pos.logical_row, cells)
        return GridPosition(grid_pos.logical_row, target,
                            grid_pos.field_num)

    def indent_cell_rows(self, start, end, indent):
        return self._edit_cell_range(
            start, end,
            lambda rows, indexes: tlist.indent_list_items(
                rows, indexes, indent))

    def outdent_cell_rows(self, start, end, tab_size):
        return self._edit_cell_range(
            start, end,
            lambda rows, indexes: tlist.outdent_list_items(
                rows, indexes, tab_size))

    def next_field(self, grid_pos):
        self._validate_position(grid_pos)
        rows = self.logical_rows[grid_pos.logical_row].data_rows
        field_count = len(rows[grid_pos.cell_row])
        if grid_pos.field_num + 1 < field_count:
            return GridPosition(grid_pos.logical_row, grid_pos.cell_row,
                                grid_pos.field_num + 1)
        if grid_pos.cell_row + 1 < len(rows):
            return GridPosition(grid_pos.logical_row,
                                grid_pos.cell_row + 1, 0)
        if grid_pos.logical_row + 1 < len(self.logical_rows):
            return GridPosition(grid_pos.logical_row + 1, 0, 0)

        self.logical_rows.append(GridLogicalRow(
            [self._blank_data_row(field_count)],
            tborder.SeparatorRow(self.table, '-')))
        return GridPosition(len(self.logical_rows) - 1, 0, 0)

    def previous_field(self, grid_pos):
        self._validate_position(grid_pos)
        if grid_pos.field_num > 0:
            return GridPosition(grid_pos.logical_row, grid_pos.cell_row,
                                grid_pos.field_num - 1)
        if grid_pos.cell_row > 0:
            row = self.logical_rows[grid_pos.logical_row].data_rows[
                grid_pos.cell_row - 1]
            return GridPosition(grid_pos.logical_row,
                                grid_pos.cell_row - 1, len(row) - 1)
        if grid_pos.logical_row > 0:
            previous = self.logical_rows[grid_pos.logical_row - 1].data_rows
            return GridPosition(grid_pos.logical_row - 1,
                                len(previous) - 1,
                                len(previous[-1]) - 1)
        return grid_pos

    def move_logical_row(self, grid_pos, offset):
        self._validate_position(grid_pos)
        tbase.check_condition(offset in (-1, 1),
                              "Logical row offset must be -1 or 1")
        target = grid_pos.logical_row + offset
        tbase.check_condition(0 <= target < len(self.logical_rows),
                              "Cannot move beyond the grid table")
        shared_row = min(grid_pos.logical_row, target)
        separator = self.logical_rows[shared_row].bottom_separator
        tbase.check_condition(separator.separator != '=',
                              "Cannot move across a header border")

        self.logical_rows[grid_pos.logical_row], self.logical_rows[target] = (
            self.logical_rows[target], self.logical_rows[grid_pos.logical_row])
        return GridPosition(target, grid_pos.cell_row, grid_pos.field_num)

    def insert_logical_row(self, grid_pos):
        self._validate_position(grid_pos)
        column_count = len(
            self.logical_rows[grid_pos.logical_row].data_rows[0])
        logical_row = GridLogicalRow(
            [self._blank_data_row(column_count)],
            tborder.SeparatorRow(self.table, '-'))
        self.logical_rows.insert(grid_pos.logical_row, logical_row)
        return GridPosition(grid_pos.logical_row, 0, grid_pos.field_num)

    def delete_logical_row(self, grid_pos):
        self._validate_position(grid_pos)
        if len(self.logical_rows) == 1:
            column_count = len(self.logical_rows[0].data_rows[0])
            self.logical_rows[0].data_rows = [
                self._blank_data_row(column_count)]
            return GridPosition(0, 0, grid_pos.field_num)

        self.logical_rows.pop(grid_pos.logical_row)

        logical_row = min(grid_pos.logical_row, len(self.logical_rows) - 1)
        row_count = len(self.logical_rows[logical_row].data_rows)
        return GridPosition(logical_row,
                            min(grid_pos.cell_row, row_count - 1),
                            grid_pos.field_num)

    def commit(self):
        rows = [self.top_separator]
        for logical_row in self.logical_rows:
            rows.extend(logical_row.data_rows)
            rows.append(logical_row.bottom_separator)
        self.table.rows = rows
        self.table.pack()

    def _validate_field(self, logical_row, field_num):
        tbase.check_condition(0 <= logical_row < len(self.logical_rows),
                              "Logical row index is out of range")
        rows = self.logical_rows[logical_row].data_rows
        tbase.check_condition(rows and 0 <= field_num < len(rows[0]),
                              "Cell index is out of range")

    def _validate_position(self, grid_pos):
        self._validate_field(grid_pos.logical_row, grid_pos.field_num)
        rows = self.logical_rows[grid_pos.logical_row].data_rows
        tbase.check_condition(0 <= grid_pos.cell_row < len(rows),
                              "Cell row index is out of range")

    def _cell_matrix(self, logical_row):
        rows = self.logical_rows[logical_row].data_rows
        return [[self._cell_text(row[field_num]) for row in rows]
                for field_num in range(len(rows[0]))]

    def _edit_cell_range(self, start, end, edit_rows):
        self._validate_position(start)
        self._validate_position(end)
        tbase.check_condition(
            start.logical_row == end.logical_row and
            start.field_num == end.field_num,
            "Selection must stay within one grid-table cell")
        tbase.check_condition(start.cell_row <= end.cell_row,
                              "Selection rows are out of order")

        cells = self._cell_matrix(start.logical_row)
        values = cells[start.field_num]
        preserved_start = tlist.ordered_list_start(values, start.cell_row)
        indexes = range(start.cell_row, end.cell_row + 1)
        try:
            values = edit_rows(values, indexes)
        except ValueError as err:
            raise tbase.TableException(str(err))
        cells[start.field_num] = tlist.renumber_ordered_list(
            values, start.cell_row, preserved_start)
        self._write_cells(start.logical_row, cells)
        return GridPosition(start.logical_row, start.cell_row,
                            start.field_num)

    def _write_cells(self, logical_row, cells):
        height = max([len(values) for values in cells] + [1])
        row_group = self.logical_rows[logical_row]
        rows = list(row_group.data_rows[:height])
        while len(rows) < height:
            rows.append(self._blank_data_row(len(cells)))

        for field_num, values in enumerate(cells):
            for row_num, row in enumerate(rows):
                value = values[row_num] if row_num < len(values) else ''
                row[field_num].data = ' ' + value
        row_group.data_rows = rows

    def _blank_data_row(self, column_count):
        row = tbase.DataRow(self.table)
        for unused_index in range(column_count):
            row.columns.append(row.new_empty_column())
        return row

    @staticmethod
    def _trim_blank_tail(cells):
        height = max([len(values) for values in cells] + [1])
        while height > 1:
            if any(height <= len(values) and values[height - 1].strip()
                   for values in cells):
                break
            height -= 1
        return [values[:height] for values in cells]

    @staticmethod
    def _cell_text(column):
        text = column.data.rstrip()
        return text[1:] if text.startswith(' ') else text


class GridTableDriver(tborder.BorderTableDriver):

    supports_multiline_grid = True

    def _apply(self, table, table_pos, operation):
        grid = GridTable(table)
        grid_pos = grid.position(table_pos)
        message, new_grid_pos = operation(grid, grid_pos)
        grid.commit()
        return message, grid.table_position(new_grid_pos)

    def _apply_or_fallback(self, table, table_pos, operation, fallback):
        if not tborder.is_grid_table(table):
            return fallback(table, table_pos)
        return self._apply(table, table_pos, operation)

    def editor_next_row(self, table, table_pos):
        return self._apply_or_fallback(
            table, table_pos,
            lambda grid, pos: ("Cell row inserted",
                               grid.insert_cell_row(pos)),
            super(GridTableDriver, self).editor_next_row)

    def editor_next_field(self, table, table_pos):
        return self._apply_or_fallback(
            table, table_pos,
            lambda grid, pos: ("Cursor position changed",
                               grid.next_field(pos)),
            super(GridTableDriver, self).editor_next_field)

    def editor_previous_field(self, table, table_pos):
        return self._apply_or_fallback(
            table, table_pos,
            lambda grid, pos: ("Cursor position changed",
                               grid.previous_field(pos)),
            super(GridTableDriver, self).editor_previous_field)

    def editor_insert_cell_row(self, table, table_pos):
        return self._apply(
            table, table_pos,
            lambda grid, pos: ("Cell row inserted",
                               grid.insert_cell_row(pos)))

    def editor_delete_cell_row(self, table, table_pos):
        return self._apply(
            table, table_pos,
            lambda grid, pos: ("Cell row deleted",
                               grid.delete_cell_row(pos)))

    def editor_move_cell_row_up(self, table, table_pos):
        return self._apply(
            table, table_pos,
            lambda grid, pos: ("Cell row moved up",
                               grid.move_cell_row(pos, -1)))

    def editor_move_cell_row_down(self, table, table_pos):
        return self._apply(
            table, table_pos,
            lambda grid, pos: ("Cell row moved down",
                               grid.move_cell_row(pos, 1)))

    def editor_indent_cell_rows(self, table, start_pos, end_pos, indent):
        return self._apply_range(
            table, start_pos, end_pos,
            lambda grid, start, end: (
                "Cell rows indented",
                grid.indent_cell_rows(start, end, indent)))

    def editor_outdent_cell_rows(self, table, start_pos, end_pos, tab_size):
        return self._apply_range(
            table, start_pos, end_pos,
            lambda grid, start, end: (
                "Cell rows outdented",
                grid.outdent_cell_rows(start, end, tab_size)))

    def editor_move_row_up(self, table, table_pos):
        return self._apply_or_fallback(
            table, table_pos,
            lambda grid, pos: ("Logical row moved up",
                               grid.move_logical_row(pos, -1)),
            super(GridTableDriver, self).editor_move_row_up)

    def editor_move_row_down(self, table, table_pos):
        return self._apply_or_fallback(
            table, table_pos,
            lambda grid, pos: ("Logical row moved down",
                               grid.move_logical_row(pos, 1)),
            super(GridTableDriver, self).editor_move_row_down)

    def editor_insert_row(self, table, table_pos):
        return self._apply_or_fallback(
            table, table_pos,
            lambda grid, pos: ("Logical row inserted",
                               grid.insert_logical_row(pos)),
            super(GridTableDriver, self).editor_insert_row)

    def editor_kill_row(self, table, table_pos):
        return self._apply_or_fallback(
            table, table_pos,
            lambda grid, pos: ("Logical row deleted",
                               grid.delete_logical_row(pos)),
            super(GridTableDriver, self).editor_kill_row)

    def _apply_range(self, table, start_pos, end_pos, operation):
        grid = GridTable(table)
        start = grid.position(start_pos)
        end = grid.position(end_pos)
        message, new_grid_pos = operation(grid, start, end)
        grid.commit()
        return message, grid.table_position(new_grid_pos)
