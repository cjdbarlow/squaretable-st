import re

try:
    from . import table_base as tbase
    from . import table_list as tlist
    from .widechar_support import wlen
except (ImportError, ValueError):
    import table_base as tbase
    import table_list as tlist
    from widechar_support import wlen


_FULL_BORDER_RE = re.compile(r'^\+(?:[-=]+\+)+$')


class GridBand(object):

    def __init__(self, height, source_start, source_end):
        self.height = height
        self.source_start = source_start
        self.source_end = source_end


class GridCell(object):

    def __init__(self, cell_id, x0, y0, x1, y1, rows=None,
                 boundary_slots=None):
        self.id = cell_id
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1
        self.rows = list(rows or [])
        self.boundary_slots = set(boundary_slots or [])

    def bounds(self):
        return self.x0, self.y0, self.x1, self.y1


class GridPosition(object):

    def __init__(self, logical_row, cell_row, field_num, cell_id=None,
                 slot_index=None):
        self.logical_row = logical_row
        self.cell_row = cell_row
        self.field_num = field_num
        self.cell_id = cell_id
        self.slot_index = cell_row if slot_index is None else slot_index

    def __eq__(self, other):
        return (isinstance(other, GridPosition) and
                self.logical_row == other.logical_row and
                self.cell_row == other.cell_row and
                self.field_num == other.field_num)

    def __repr__(self):
        return 'GridPosition({0}, {1}, {2})'.format(
            self.logical_row, self.cell_row, self.field_num)


class _DisjointSet(object):

    def __init__(self, values):
        self.parents = dict((value, value) for value in values)

    def find(self, value):
        parent = self.parents[value]
        if parent != value:
            self.parents[value] = self.find(parent)
        return self.parents[value]

    def union(self, first, second):
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root != second_root:
            self.parents[second_root] = first_root


class GridDocument(object):

    def __init__(self, prefix, x_positions, bands, horizontal_edges,
                 vertical_edges, source_lines, content_boundaries,
                 boundary_source_rows, horizontal_junctions):
        self.prefix = prefix
        self.x_positions = list(x_positions)
        self.column_widths = [
            self.x_positions[index + 1] - self.x_positions[index] - 1
            for index in range(len(self.x_positions) - 1)
        ]
        self.bands = list(bands)
        self.horizontal_edges = [list(row) for row in horizontal_edges]
        self.vertical_edges = [list(row) for row in vertical_edges]
        self.source_lines = list(source_lines)
        self.content_boundaries = dict(content_boundaries)
        self.boundary_source_rows = list(boundary_source_rows)
        self.horizontal_junctions = [list(row)
                                     for row in horizontal_junctions]
        self.cells = []
        self._cell_by_slot = {}
        self._infer_cells()

    @classmethod
    def try_from_text(cls, text):
        lines = _normalized_grid_lines(text)
        if not lines:
            return None
        prefix_match = re.match(r'^(\s*)', lines[0])
        prefix = prefix_match.group(1)
        first = lines[0][len(prefix):]
        if _FULL_BORDER_RE.match(first) is None:
            return None
        if len(lines) < 3:
            return None
        last = lines[-1][len(prefix):] if lines[-1].startswith(prefix) else ''
        if _FULL_BORDER_RE.match(last) is None:
            return None
        return cls.from_text(text)

    @classmethod
    def from_text(cls, text):
        lines = _normalized_grid_lines(text)
        tbase.check_condition(lines, 'Grid table must not be empty')
        prefix = _grid_prefix(lines[0])
        bodies = []
        for line in lines:
            tbase.check_condition(
                line.startswith(prefix),
                'Grid table indentation must be consistent')
            bodies.append(line[len(prefix):])

        tbase.check_condition(
            _FULL_BORDER_RE.match(bodies[0]) is not None,
            'Grid table must start with a complete horizontal border')
        tbase.check_condition(
            len(bodies) >= 3 and
            _FULL_BORDER_RE.match(bodies[-1]) is not None,
            'Grid table must end with a complete horizontal border')

        expected_width = wlen(bodies[0])
        tbase.check_condition(
            all(wlen(line) == expected_width for line in bodies),
            'Grid lines must keep structural boundaries aligned')

        x_positions = _collect_x_boundaries(bodies)
        tbase.check_condition(
            len(x_positions) >= 2 and x_positions[0] == 0 and
            x_positions[-1] == expected_width - 1,
            'Grid table boundaries are malformed')

        separator_rows = []
        separator_edges = {}
        separator_junctions = {}
        for row_num, line in enumerate(bodies):
            edges = _separator_edges(line, x_positions, expected_width)
            if any(edge is not None for edge in edges):
                separator_rows.append(row_num)
                separator_edges[row_num] = edges
                separator_junctions[row_num] = [
                    _char_at_visual(line, position) == '+'
                    for position in x_positions]

        tbase.check_condition(
            separator_rows and separator_rows[0] == 0 and
            separator_rows[-1] == len(bodies) - 1,
            'Grid table must have complete outer borders')

        bands = []
        horizontal_edges = []
        horizontal_junctions = []
        vertical_edges = []
        content_boundaries = {}
        for boundary_index, row_num in enumerate(separator_rows):
            horizontal_edges.append(separator_edges[row_num])
            horizontal_junctions.append(separator_junctions[row_num])
            if boundary_index == len(separator_rows) - 1:
                continue
            next_row = separator_rows[boundary_index + 1]
            tbase.check_condition(
                next_row > row_num + 1,
                'Grid table borders must contain a content band')
            band = GridBand(next_row - row_num - 1,
                            row_num + 1, next_row)
            bands.append(band)
            vertical, boundaries = _band_vertical_edges(
                bodies, band, x_positions)
            vertical_edges.append(vertical)
            content_boundaries.update(boundaries)

        tbase.check_condition(
            all(edge is not None for edge in horizontal_edges[0]) and
            all(edge is not None for edge in horizontal_edges[-1]),
            'Grid table outer borders must be complete')

        return cls(prefix, x_positions, bands, horizontal_edges,
                   vertical_edges, bodies, content_boundaries,
                   separator_rows, horizontal_junctions)

    @classmethod
    def from_editing_text(cls, text, active_row, active_column):
        document, unused_field_num = cls.editing_document_at(
            text, active_row, active_column)
        return document

    @classmethod
    def editing_document_at(cls, text, active_row, active_column):
        try:
            document = cls.from_text(text)
            return (document,
                    document.field_at_column(active_row, active_column))
        except tbase.TableException as strict_error:
            try:
                return cls._recover_active_content_line(
                    text, active_row, active_column)
            except tbase.TableException:
                raise strict_error

    @classmethod
    def _recover_active_content_line(cls, text, active_row,
                                     active_column):
        lines = _normalized_grid_lines(text)
        tbase.check_condition(lines, 'Grid table must not be empty')
        tbase.check_condition(
            0 <= active_row < len(lines),
            'Active grid row is out of range')

        prefix = _grid_prefix(lines[0])
        tbase.check_condition(
            all(line.startswith(prefix) for line in lines),
            'Grid table indentation must be consistent')
        bodies = [line[len(prefix):] for line in lines]
        expected_widths = sorted(set(
            wlen(line) for line in bodies
            if _FULL_BORDER_RE.match(line) is not None))
        tbase.check_condition(
            expected_widths,
            'Grid table requires a complete horizontal border')

        recovered = {}
        for expected_width in expected_widths:
            try:
                document, field_num = cls._recover_edit_with_width(
                    prefix, bodies, expected_width,
                    active_row, active_column)
                key = (document.render(), field_num)
                priority = int(
                    wlen(bodies[active_row]) != expected_width)
                previous = recovered.get(key)
                if previous is None or priority > previous[0]:
                    recovered[key] = (priority, document, field_num)
            except tbase.TableException:
                continue
        if recovered:
            best_priority = max(value[0] for value in recovered.values())
            recovered = dict(
                (key, value) for key, value in recovered.items()
                if value[0] == best_priority)
        tbase.check_condition(
            len(recovered) == 1,
            'Grid edit has no unique baseline width')
        unused_priority, document, field_num = next(
            iter(recovered.values()))
        return document, field_num

    @classmethod
    def _recover_edit_with_width(cls, prefix, bodies, expected_width,
                                 active_row, active_column):
        ragged_rows = [
            row for row, line in enumerate(bodies)
            if wlen(line) != expected_width]
        if len(ragged_rows) > 1:
            return cls._recover_shared_boundary_edit(
                prefix, bodies, expected_width, ragged_rows,
                active_row, active_column)
        tbase.check_condition(
            ragged_rows == [active_row],
            'Only the active grid row may be temporarily ragged')

        active_line = bodies[active_row]
        delta = wlen(active_line) - expected_width
        tbase.check_condition(
            delta != 0 and active_line.startswith('|') and
            active_line.endswith('|'),
            'Active grid row is not recoverable content')

        body_column = max(0, active_column - len(prefix))
        body_column = min(body_column, len(active_line))
        caret_visual = wlen(active_line[:body_column])
        edit_start = caret_visual - max(delta, 0)
        tbase.check_condition(
            0 < edit_start < wlen(active_line),
            'Active grid edit is outside cell content')

        x_positions = _collect_x_boundaries(bodies)
        tbase.check_condition(
            len(x_positions) >= 2 and x_positions[0] == 0 and
            x_positions[-1] == expected_width - 1,
            'Grid table boundaries are malformed')

        def edited_position(position):
            return position if position < edit_start else position + delta

        present = [
            _char_at_visual(active_line, edited_position(position)) == '|'
            for position in x_positions]
        tbase.check_condition(
            present[0] and present[-1],
            'Grid content rows must have complete outer edges')

        placeholder = [' '] * expected_width
        for position, has_boundary in zip(x_positions, present):
            if has_boundary:
                placeholder[position] = '|'
        canonical = list(bodies)
        canonical[active_row] = ''.join(placeholder)
        document = cls.from_text('\n'.join(
            prefix + line for line in canonical))

        band_index, line_index = document._band_line_for_row(active_row)
        for cell in document._visible_cells(band_index):
            left = edited_position(document.x_positions[cell.x0])
            right = edited_position(document.x_positions[cell.x1])
            tbase.check_condition(
                _char_at_visual(active_line, left) == '|' and
                _char_at_visual(active_line, right) == '|',
                'Active grid cell boundaries could not be recovered')
            offset = document._cell_row_offset(
                cell, band_index, line_index)
            cell.rows[offset] = _cell_text(active_line, left, right)
        field_num = document.field_at_column(
            active_row, len(prefix) + edit_start)
        return document, field_num

    @classmethod
    def _recover_shared_boundary_edit(cls, prefix, bodies,
                                      expected_width, ragged_rows,
                                      active_row, active_column):
        separator_rows = [
            row for row in ragged_rows
            if _FULL_BORDER_RE.match(bodies[row]) is not None]
        tbase.check_condition(
            separator_rows,
            'A grid boundary edit requires an anchoring border')
        separator_deltas = [
            wlen(bodies[row]) - expected_width
            for row in separator_rows]
        tbase.check_condition(
            len(set(separator_deltas)) == 1 and
            separator_deltas[0] in (-1, 1),
            'Ragged grid borders must share one boundary edit')
        boundary_delta = separator_deltas[0]

        content_rows = [row for row in ragged_rows
                        if row not in separator_rows]
        tbase.check_condition(
            content_rows,
            'A grid boundary edit requires changed content geometry')
        tbase.check_condition(
            all(bodies[row].startswith('|') and
                bodies[row].endswith('|')
                for row in content_rows),
            'Boundary edits require content or complete borders')

        content_edits = {}
        for row in content_rows:
            content_delta = (wlen(bodies[row]) - expected_width -
                             boundary_delta)
            tbase.check_condition(
                content_delta == 0 or row == active_row,
                'Only active grid content may also change width')
            if content_delta:
                body_column = max(0, active_column - len(prefix))
                body_column = min(body_column, len(bodies[row]))
                caret_visual = wlen(bodies[row][:body_column])
                content_start = caret_visual - max(content_delta, 0)
                tbase.check_condition(
                    0 < content_start < wlen(bodies[row]),
                    'Active grid edit is outside cell content')
            else:
                content_start = 0
            content_edits[row] = (content_start, content_delta)

        aligned = [line for line in bodies
                   if wlen(line) == expected_width]
        x_positions = _collect_x_boundaries(aligned)
        tbase.check_condition(
            len(x_positions) >= 3 and x_positions[0] == 0 and
            x_positions[-1] == expected_width - 1,
            'Grid table boundaries are malformed')

        structural_separators = set(separator_rows)
        for row, line in enumerate(bodies):
            if wlen(line) != expected_width:
                continue
            if any(edge is not None for edge in
                   _separator_edges(line, x_positions, expected_width)):
                structural_separators.add(row)
        ordered_separators = sorted(structural_separators)
        affected_bands = set()
        for row in content_rows:
            above = [candidate for candidate in ordered_separators
                     if candidate < row]
            below = [candidate for candidate in ordered_separators
                     if candidate > row]
            tbase.check_condition(
                above and below,
                'Edited grid content must lie inside a complete band')
            band = (above[-1], below[0])
            tbase.check_condition(
                band[0] in separator_rows or band[1] in separator_rows,
                'Edited content must touch its changed border')
            affected_bands.add(band)
        tbase.check_condition(
            len(affected_bands) == 1,
            'A boundary edit must affect one content band')

        candidates = x_positions[1:-1]
        if active_row in ragged_rows:
            active_body_column = max(0, active_column - len(prefix))
            active_body_column = min(
                active_body_column, len(bodies[active_row]))
            caret_visual = wlen(
                bodies[active_row][:active_body_column])
            content_delta = content_edits.get(active_row, (0, 0))[1]
            inferred = caret_visual - max(
                boundary_delta + content_delta, 0)
            inserted_anchor = (
                boundary_delta > 0 and content_delta == 0 and
                _char_at_visual(bodies[active_row], inferred) in '|+')
            if (inferred in candidates and content_delta == 0 and
                    (boundary_delta < 0 or inserted_anchor)):
                candidates = [inferred]

        recovered = {}
        for edit_start in candidates:
            try:
                document = cls._recover_boundary_candidate(
                    prefix, bodies, expected_width, separator_rows,
                    content_edits, x_positions, edit_start,
                    boundary_delta)
                signature = document.render()
                recovered[signature] = (document, edit_start)
            except tbase.TableException:
                continue

        tbase.check_condition(
            len(recovered) == 1,
            'Grid boundary edit is incomplete or ambiguous')
        document, edit_start = next(iter(recovered.values()))

        body_column = max(0, active_column - len(prefix))
        body_column = min(body_column, len(bodies[active_row]))
        caret_visual = wlen(bodies[active_row][:body_column])
        content_start, content_delta = content_edits.get(
            active_row, (0, 0))
        if content_delta > 0 and caret_visual > content_start:
            caret_visual = max(
                content_start, caret_visual - content_delta)
        elif content_delta < 0 and caret_visual >= content_start:
            caret_visual -= content_delta
        if active_row in ragged_rows or active_row in content_edits:
            if boundary_delta > 0:
                if caret_visual == edit_start + 1:
                    caret_visual = edit_start + 1
                elif caret_visual > edit_start + 1:
                    caret_visual -= boundary_delta
            elif caret_visual >= edit_start:
                caret_visual -= boundary_delta
        field_num = document.field_at_column(
            active_row, len(prefix) + caret_visual)
        return document, field_num

    @classmethod
    def _recover_boundary_candidate(cls, prefix, bodies,
                                    expected_width, separator_rows,
                                    content_edits, x_positions,
                                    edit_start, boundary_delta):
        canonical = list(bodies)
        for row in separator_rows:
            canonical[row] = _boundary_edit_separator_line(
                bodies[row], expected_width, edit_start,
                boundary_delta)
        for row, (content_start, content_delta) in content_edits.items():
            canonical[row] = _boundary_edit_content_line(
                bodies[row], expected_width, x_positions,
                edit_start, boundary_delta,
                content_start, content_delta)

        document = cls.from_text('\n'.join(
            prefix + line for line in canonical))
        for row, (content_start, content_delta) in content_edits.items():
            band_index, line_index = document._band_line_for_row(row)
            for cell in document._visible_cells(band_index):
                left = _compound_edited_position(
                    document.x_positions[cell.x0], edit_start,
                    boundary_delta, content_start, content_delta)
                right = _compound_edited_position(
                    document.x_positions[cell.x1], edit_start,
                    boundary_delta, content_start, content_delta)
                tbase.check_condition(
                    left is not None and right is not None and
                    _char_at_visual(bodies[row], left) == '|' and
                    _char_at_visual(bodies[row], right) == '|',
                    'Grid cell boundaries could not be recovered')
                offset = document._cell_row_offset(
                    cell, band_index, line_index)
                cell.rows[offset] = _cell_text(
                    bodies[row], left, right)
        return document

    def _infer_cells(self):
        column_count = len(self.column_widths)
        slots = [(x, y) for y in range(len(self.bands))
                 for x in range(column_count)]
        components = _DisjointSet(slots)

        for y in range(len(self.bands)):
            for x in range(column_count - 1):
                if not self.vertical_edges[y][x + 1]:
                    components.union((x, y), (x + 1, y))

        for y in range(len(self.bands) - 1):
            for x in range(column_count):
                if self.horizontal_edges[y + 1][x] is None:
                    components.union((x, y), (x, y + 1))

        grouped = {}
        for slot in slots:
            grouped.setdefault(components.find(slot), []).append(slot)

        bounds_and_slots = []
        for component_slots in grouped.values():
            x0 = min(x for x, unused_y in component_slots)
            x1 = max(x for x, unused_y in component_slots) + 1
            y0 = min(y for unused_x, y in component_slots)
            y1 = max(y for unused_x, y in component_slots) + 1
            expected = set((x, y) for y in range(y0, y1)
                           for x in range(x0, x1))
            tbase.check_condition(
                set(component_slots) == expected,
                'Grid cells must be rectangular')
            self._validate_cell_perimeter(x0, y0, x1, y1)
            bounds_and_slots.append((y0, x0, x1, y1, component_slots))

        bounds_and_slots.sort()
        for cell_id, (y0, x0, x1, y1, component_slots) in enumerate(
                bounds_and_slots):
            rows, boundary_slots = self._cell_rows(x0, y0, x1, y1)
            cell = GridCell(cell_id, x0, y0, x1, y1, rows,
                            boundary_slots)
            self.cells.append(cell)
            for slot in component_slots:
                self._cell_by_slot[slot] = cell

    def _validate_cell_perimeter(self, x0, y0, x1, y1):
        for y in range(y0, y1):
            tbase.check_condition(
                self.vertical_edges[y][x0] and
                self.vertical_edges[y][x1],
                'Grid cell has an open vertical edge')
        for x in range(x0, x1):
            tbase.check_condition(
                self.horizontal_edges[y0][x] is not None and
                self.horizontal_edges[y1][x] is not None,
                'Grid cell has an open horizontal edge')

    def _cell_rows(self, x0, y0, x1, y1):
        rows = []
        boundary_slots = set()
        for band_index in range(y0, y1):
            band = self.bands[band_index]
            for source_row in range(band.source_start, band.source_end):
                boundaries = self.content_boundaries[source_row]
                rows.append(_cell_text(
                    self.source_lines[source_row],
                    boundaries[x0], boundaries[x1]))
            boundary = band_index + 1
            if boundary < y1:
                source_row = self.boundary_source_rows[boundary]
                text = _cell_text(
                    self.source_lines[source_row],
                    self.x_positions[x0], self.x_positions[x1])
                if text:
                    boundary_slots.add(boundary)
                    rows.append(text)
        return rows, boundary_slots

    def position(self, table_pos):
        boundary = self._boundary_for_row(table_pos.row_num)
        if boundary is None:
            band_index, line_index = self._band_line_for_row(
                table_pos.row_num)
            visible = self._visible_cells(band_index)
            slot_for_cell = lambda cell: self._cell_row_offset(
                cell, band_index, line_index)
            logical_row = self._logical_row_for_band(band_index)
            cell_row = self._logical_content_offset(
                logical_row, band_index, line_index)
        else:
            visible = self._visible_boundary_cells(boundary)
            tbase.check_condition(
                visible,
                'Expected a grid-table content row')
            slot_for_cell = lambda cell: self._boundary_cell_row_offset(
                cell, boundary)
            adjacent_band = min(boundary, len(self.bands) - 1)
            logical_row = self._logical_row_for_band(adjacent_band)
            start, unused_end = self.logical_row_ranges()[logical_row]
            cell_row = sum(self.bands[index].height
                           for index in range(start, boundary))
        tbase.check_condition(
            0 <= table_pos.field_num < len(visible),
            'Grid field index is out of range')
        cell = visible[table_pos.field_num]
        slot_index = slot_for_cell(cell)
        return GridPosition(logical_row, cell_row, table_pos.field_num,
                            cell.id, slot_index)

    def table_position(self, grid_pos):
        grid_pos = self.resolve_position(grid_pos)
        cell = self.cells[grid_pos.cell_id]
        band_index, line_index = self._band_line_for_cell_slot(
            cell, grid_pos.slot_index)
        if line_index is None:
            visible = self._visible_boundary_cells(band_index)
            row_num = self._boundary_row(band_index)
        else:
            visible = self._visible_cells(band_index)
            row_num = self._band_row_start(band_index) + line_index
        field_num = [candidate.id for candidate in visible].index(cell.id)
        return tbase.TablePos(row_num, field_num)

    def cursor_column(self, table_pos):
        widths = self._resolved_widths()
        try:
            grid_pos = self.position(table_pos)
        except tbase.TableException:
            boundary = self._boundary_for_row(table_pos.row_num)
            tbase.check_condition(boundary is not None,
                                  'Expected a grid-table row')
            field_num = min(max(table_pos.field_num, 0),
                            len(widths) - 1)
            return (len(self.prefix) +
                    _rendered_x_positions(widths)[field_num] + 1)
        cell = self.cells[grid_pos.cell_id]
        boundary_visual = cell.x0 + sum(widths[:cell.x0])
        rendered = self.render_lines()[table_pos.row_num]
        body = rendered[len(self.prefix):]
        return (len(self.prefix) +
                _visual_index(body, boundary_visual) + 2)

    def field_at_column(self, row_num, column):
        tbase.check_condition(
            0 <= row_num < len(self.source_lines),
            'Grid row index is out of range')
        body_column = max(0, column - len(self.prefix))
        visual_column = wlen(self.source_lines[row_num][:body_column])
        boundary = self._boundary_for_row(row_num)
        if boundary is None:
            band_index, unused_line_index = self._band_line_for_row(row_num)
            visible = self._visible_cells(band_index)
        else:
            visible = self._visible_boundary_cells(boundary)

        for field_num, cell in enumerate(visible):
            if (self.x_positions[cell.x0] <= visual_column <=
                    self.x_positions[cell.x1]):
                return field_num

        for field_num, right in enumerate(self.x_positions[1:]):
            if visual_column <= right:
                return field_num
        return len(self.column_widths) - 1

    def position_near(self, table_pos, prefer='below'):
        try:
            return self.position(table_pos)
        except tbase.TableException:
            boundary = self._boundary_for_row(table_pos.row_num)
            tbase.check_condition(boundary is not None,
                                  'Expected a grid-table row')
            entries = self._physical_positions()
            if prefer == 'below':
                candidates = [entry for entry in entries
                              if entry.row_num > table_pos.row_num]
                if candidates:
                    return self.position(candidates[0])
            elif prefer == 'above':
                candidates = [entry for entry in entries
                              if entry.row_num < table_pos.row_num]
                if candidates:
                    return self.position(candidates[-1])
            else:
                raise tbase.TableException(
                    'Grid position preference must be above or below')
            tbase.check_condition(entries, 'Grid table has no content rows')
            endpoint = entries[-1] if prefer == 'below' else entries[0]
            return self.position(endpoint)

    def next_field_from(self, table_pos):
        try:
            return self.next_field(self.position(table_pos))
        except tbase.TableException:
            entries = self._physical_positions()
            below = [entry for entry in entries
                     if entry.row_num > table_pos.row_num]
            if below:
                return self.position(below[0])
            tbase.check_condition(entries, 'Grid table has no content rows')
            return self.next_field(self.position(entries[-1]))

    def previous_field_from(self, table_pos):
        try:
            return self.previous_field(self.position(table_pos))
        except tbase.TableException:
            entries = self._physical_positions()
            above = [entry for entry in entries
                     if entry.row_num < table_pos.row_num]
            tbase.check_condition(above, 'Cannot move before the grid table')
            return self.position(above[-1])

    def resolve_position(self, grid_pos):
        if grid_pos.cell_id is not None:
            tbase.check_condition(
                0 <= grid_pos.cell_id < len(self.cells),
                'Grid cell index is out of range')
            cell = self.cells[grid_pos.cell_id]
            tbase.check_condition(
                0 <= grid_pos.slot_index < len(cell.rows),
                'Grid cell row index is out of range')
            return grid_pos

        logical_ranges = self.logical_row_ranges()
        tbase.check_condition(
            0 <= grid_pos.logical_row < len(logical_ranges),
            'Logical row index is out of range')
        start, end = logical_ranges[grid_pos.logical_row]
        physical = []
        for band_index in range(start, end):
            for line_index in range(self.bands[band_index].height):
                physical.append((band_index, line_index))
        tbase.check_condition(
            0 <= grid_pos.cell_row < len(physical),
            'Cell row index is out of range')
        band_index, line_index = physical[grid_pos.cell_row]
        visible = self._visible_cells(band_index)
        tbase.check_condition(
            0 <= grid_pos.field_num < len(visible),
            'Grid field index is out of range')
        cell = visible[grid_pos.field_num]
        return GridPosition(
            grid_pos.logical_row, grid_pos.cell_row, grid_pos.field_num,
            cell.id, self._cell_row_offset(cell, band_index, line_index))

    def insert_cell_row(self, grid_pos):
        grid_pos = self.resolve_position(grid_pos)
        cell = self.cells[grid_pos.cell_id]
        band_index, unused_line = self._band_line_for_cell_slot(
            cell, grid_pos.slot_index)
        preserved_start = tlist.ordered_list_start(
            cell.rows, grid_pos.slot_index)
        continuation = tlist.continuation_for(
            cell.rows[grid_pos.slot_index]) or ''
        continuation = continuation.rstrip()

        for crossing in self._cells_covering_band(band_index):
            if crossing.id == cell.id:
                crossing.rows.insert(grid_pos.slot_index + 1, continuation)
            else:
                crossing.rows.insert(
                    self._band_end_offset(crossing, band_index), '')
        self.bands[band_index].height += 1
        cell.rows = tlist.renumber_ordered_list(
            cell.rows, grid_pos.slot_index + 1, preserved_start)
        return self._position_for_cell_slot(cell, grid_pos.slot_index + 1)

    def delete_cell_row(self, grid_pos):
        grid_pos = self.resolve_position(grid_pos)
        cell = self.cells[grid_pos.cell_id]
        containing_band, line_index = self._band_line_for_cell_slot(
            cell, grid_pos.slot_index)
        preserved_start = tlist.ordered_list_start(
            cell.rows, grid_pos.slot_index)

        if len(cell.rows) == 1:
            cell.rows[0] = ''
        else:
            del cell.rows[grid_pos.slot_index]
            cell.rows.append('')

        target = min(grid_pos.slot_index, len(cell.rows) - 1)
        cell.rows = tlist.renumber_ordered_list(
            cell.rows, target, preserved_start)
        if line_index is not None:
            self._contract_blank_band(cell, containing_band)
        target = min(target, len(cell.rows) - 1)
        return self._position_for_cell_slot(cell, target)

    def move_cell_row(self, grid_pos, offset):
        grid_pos = self.resolve_position(grid_pos)
        tbase.check_condition(offset in (-1, 1),
                              'Cell row offset must be -1 or 1')
        cell = self.cells[grid_pos.cell_id]
        target = grid_pos.slot_index + offset
        tbase.check_condition(0 <= target < len(cell.rows),
                              'Cannot move beyond the current cell')
        preserved_start = tlist.ordered_list_start(
            cell.rows, grid_pos.slot_index)
        cell.rows[grid_pos.slot_index], cell.rows[target] = (
            cell.rows[target], cell.rows[grid_pos.slot_index])
        cell.rows = tlist.renumber_ordered_list(
            cell.rows, target, preserved_start)
        return self._position_for_cell_slot(cell, target)

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

    def move_column(self, grid_pos, offset):
        grid_pos = self.resolve_position(grid_pos)
        tbase.check_condition(offset in (-1, 1),
                              'Column offset must be -1 or 1')
        active = self.cells[grid_pos.cell_id]
        tbase.check_condition(active.x1 - active.x0 == 1,
                              'Column operation touches a spanning cell')
        source = active.x0
        target = source + offset
        tbase.check_condition(
            0 <= target < len(self.column_widths),
            'Cannot move beyond the grid table')
        self._assert_unspanned_columns((source, target))

        self.column_widths[source], self.column_widths[target] = (
            self.column_widths[target], self.column_widths[source])
        for edges in self.horizontal_edges:
            edges[source], edges[target] = edges[target], edges[source]
        for cell in self.cells:
            if cell.x0 == source:
                cell.x0, cell.x1 = target, target + 1
            elif cell.x0 == target:
                cell.x0, cell.x1 = source, source + 1
        self._refresh_geometry_indexes()
        return self._position_for_cell_slot(active, grid_pos.slot_index)

    def insert_column(self, grid_pos):
        grid_pos = self.resolve_position(grid_pos)
        active = self.cells[grid_pos.cell_id]
        column = active.x0
        self._assert_unspanned_columns((column,))
        band_index, line_index = self._band_line_for_cell_slot(
            active, grid_pos.slot_index)
        tbase.check_condition(line_index is not None,
                              'Cannot insert a column from a boundary slot')

        self.column_widths.insert(column, max(3, self.column_widths[column]))
        for boundary, edges in enumerate(self.horizontal_edges):
            edges.insert(column, edges[column])
            self.horizontal_junctions[boundary].insert(column + 1, True)
        for edges in self.vertical_edges:
            edges.insert(column + 1, True)
        for cell in self.cells:
            if cell.x0 >= column:
                cell.x0 += 1
                cell.x1 += 1
            elif cell.x1 > column:
                cell.x1 += 1
        for band, band_data in enumerate(self.bands):
            self.cells.append(GridCell(
                -1, column, band, column + 1, band + 1,
                [''] * band_data.height))
        self._refresh_geometry_indexes()
        inserted = self._cell_by_slot[(column, band_index)]
        return self._position_for_cell_slot(inserted, line_index)

    def delete_column(self, grid_pos):
        grid_pos = self.resolve_position(grid_pos)
        tbase.check_condition(len(self.column_widths) > 1,
                              'Cannot delete the only grid column')
        active = self.cells[grid_pos.cell_id]
        column = active.x0
        self._assert_unspanned_columns((column,))
        band_index, line_index = self._band_line_for_cell_slot(
            active, grid_pos.slot_index)
        tbase.check_condition(line_index is not None,
                              'Cannot delete a column from a boundary slot')

        self.cells = [cell for cell in self.cells
                      if not (cell.x0 <= column < cell.x1)]
        for cell in self.cells:
            if cell.x0 > column:
                cell.x0 -= 1
                cell.x1 -= 1
        old_count = len(self.column_widths)
        del self.column_widths[column]
        for edges in self.horizontal_edges:
            del edges[column]
        node = column + 1 if column < old_count - 1 else column
        for boundary, junctions in enumerate(self.horizontal_junctions):
            del junctions[node]
        for edges in self.vertical_edges:
            del edges[node]
        self._refresh_geometry_indexes()
        target = min(column, len(self.column_widths) - 1)
        cell = self._cell_by_slot[(target, band_index)]
        slot = self._cell_row_offset(cell, band_index, line_index)
        return self._position_for_cell_slot(cell, slot)

    def _edit_cell_range(self, start, end, edit_rows):
        start = self.resolve_position(start)
        end = self.resolve_position(end)
        tbase.check_condition(
            start.cell_id == end.cell_id,
            'Selection must stay within one grid-table cell')
        tbase.check_condition(
            start.slot_index <= end.slot_index,
            'Selection rows are out of order')
        cell = self.cells[start.cell_id]
        preserved_start = tlist.ordered_list_start(
            cell.rows, start.slot_index)
        indexes = range(start.slot_index, end.slot_index + 1)
        try:
            cell.rows = edit_rows(cell.rows, indexes)
        except ValueError as err:
            raise tbase.TableException(str(err))
        cell.rows = tlist.renumber_ordered_list(
            cell.rows, start.slot_index, preserved_start)
        return self._position_for_cell_slot(cell, start.slot_index)

    def _assert_unspanned_columns(self, columns):
        columns = set(columns)
        for cell in self.cells:
            touches = any(cell.x0 <= column < cell.x1
                          for column in columns)
            if touches and (cell.x1 - cell.x0 > 1 or
                            cell.y1 - cell.y0 > 1):
                raise tbase.TableException(
                    'Column operation touches a spanning cell')

    def _refresh_geometry_indexes(self):
        self.x_positions = _rendered_x_positions(self.column_widths)
        self.cells.sort(key=lambda cell: (cell.y0, cell.x0,
                                          cell.y1, cell.x1))
        self._cell_by_slot = {}
        for cell_id, cell in enumerate(self.cells):
            cell.id = cell_id
            for y in range(cell.y0, cell.y1):
                for x in range(cell.x0, cell.x1):
                    self._cell_by_slot[(x, y)] = cell

    def next_field(self, grid_pos):
        current = self.table_position(self.resolve_position(grid_pos))
        entries = self._physical_positions()
        index = entries.index(current)
        if index + 1 < len(entries):
            return self.position(entries[index + 1])
        logical_row = len(self.logical_row_ranges())
        self._insert_blank_logical_row(logical_row)
        return self.resolve_position(GridPosition(logical_row, 0, 0))

    def previous_field(self, grid_pos):
        current = self.table_position(self.resolve_position(grid_pos))
        entries = self._physical_positions()
        index = entries.index(current)
        if index == 0:
            return self.position(entries[0])
        return self.position(entries[index - 1])

    def move_logical_row(self, grid_pos, offset):
        grid_pos = self.resolve_position(grid_pos)
        tbase.check_condition(offset in (-1, 1),
                              'Logical row offset must be -1 or 1')
        ranges = self.logical_row_ranges()
        target = grid_pos.logical_row + offset
        tbase.check_condition(0 <= target < len(ranges),
                              'Cannot move beyond the grid table')
        shared_boundary = ranges[min(grid_pos.logical_row, target)][1]
        tbase.check_condition(
            all(edge != '=' for edge in
                self.horizontal_edges[shared_boundary]),
            'Cannot move across a header border')
        chunks = self._logical_source_chunks()
        chunks[grid_pos.logical_row], chunks[target] = (
            chunks[target], chunks[grid_pos.logical_row])
        self._reparse_chunks(chunks)
        return self._resolved_logical_position(
            target, grid_pos.cell_row, grid_pos.field_num)

    def insert_logical_row(self, grid_pos):
        grid_pos = self.resolve_position(grid_pos)
        logical_row = grid_pos.logical_row
        self._insert_blank_logical_row(logical_row)
        return self._resolved_logical_position(
            logical_row, 0, grid_pos.field_num)

    def delete_logical_row(self, grid_pos):
        grid_pos = self.resolve_position(grid_pos)
        chunks = self._logical_source_chunks()
        chunks.pop(grid_pos.logical_row)
        if not chunks:
            chunks.append(self._blank_logical_chunk())
        self._reparse_chunks(chunks)
        logical_row = min(grid_pos.logical_row,
                          len(self.logical_row_ranges()) - 1)
        return self._resolved_logical_position(
            logical_row, grid_pos.cell_row, grid_pos.field_num)

    def logical_row_ranges(self):
        full_boundaries = [
            index for index, edges in enumerate(self.horizontal_edges)
            if all(edge is not None for edge in edges)
        ]
        return list(zip(full_boundaries, full_boundaries[1:]))

    def _physical_positions(self):
        result = []
        for band_index, band in enumerate(self.bands):
            visible = self._visible_cells(band_index)
            for line_index in range(band.height):
                row_num = self._band_row_start(band_index) + line_index
                result.extend(tbase.TablePos(row_num, field_num)
                              for field_num in range(len(visible)))
            boundary = band_index + 1
            boundary_visible = self._visible_boundary_cells(boundary)
            row_num = self._boundary_row(boundary)
            result.extend(tbase.TablePos(row_num, field_num)
                          for field_num in range(len(boundary_visible)))
        return result

    def _insert_blank_logical_row(self, logical_row):
        chunks = self._logical_source_chunks()
        tbase.check_condition(
            0 <= logical_row <= len(chunks),
            'Logical row index is out of range')
        chunks.insert(logical_row, self._blank_logical_chunk())
        self._reparse_chunks(chunks)

    def _blank_logical_chunk(self):
        widths = self._resolved_widths()
        content = self.prefix + '|' + '|'.join(
            ' ' * width for width in widths) + '|'
        border = self.prefix + '+' + '+'.join(
            '-' * width for width in widths) + '+'
        return [content, border]

    def _logical_source_chunks(self):
        lines = self.render_lines()
        chunks = []
        for start, end in self.logical_row_ranges():
            start_row = self._boundary_row(start)
            end_row = self._boundary_row(end)
            chunks.append(lines[start_row + 1:end_row + 1])
        return chunks

    def _boundary_row(self, boundary):
        return boundary + sum(self.bands[index].height
                              for index in range(boundary))

    def _reparse_chunks(self, chunks):
        top = self.render_lines()[0]
        lines = [top]
        for chunk in chunks:
            lines.extend(chunk)
        replacement = GridDocument.from_text('\n'.join(lines))
        self.__dict__.clear()
        self.__dict__.update(replacement.__dict__)

    def _resolved_logical_position(self, logical_row, cell_row, field_num):
        start, end = self.logical_row_ranges()[logical_row]
        row_count = sum(self.bands[index].height
                        for index in range(start, end))
        cell_row = min(cell_row, row_count - 1)
        band_index = start
        remaining = cell_row
        while remaining >= self.bands[band_index].height:
            remaining -= self.bands[band_index].height
            band_index += 1
        field_count = len(self._visible_cells(band_index))
        field_num = min(field_num, field_count - 1)
        return self.resolve_position(
            GridPosition(logical_row, cell_row, field_num))

    def _logical_row_for_band(self, band_index):
        for logical_row, (start, end) in enumerate(self.logical_row_ranges()):
            if start <= band_index < end:
                return logical_row
        raise tbase.TableException('Content band is outside a logical row')

    def _logical_content_offset(self, logical_row, band_index, line_index):
        start, unused_end = self.logical_row_ranges()[logical_row]
        return (sum(self.bands[index].height
                    for index in range(start, band_index)) + line_index)

    def _visible_cells(self, band_index):
        return sorted(
            set(self._cell_by_slot[(x, band_index)]
                for x in range(len(self.column_widths))),
            key=lambda cell: cell.x0)

    def _visible_boundary_cells(self, boundary):
        return sorted(
            [cell for cell in self.cells
             if boundary in cell.boundary_slots],
            key=lambda cell: cell.x0)

    def _cells_covering_band(self, band_index):
        return [cell for cell in self.cells
                if cell.y0 <= band_index < cell.y1]

    def _band_end_offset(self, cell, band_index):
        return (sum(self.bands[index].height
                    for index in range(cell.y0, band_index + 1)) +
                sum(1 for boundary in cell.boundary_slots
                    if cell.y0 < boundary <= band_index))

    def _contract_blank_band(self, active_cell, band_index):
        tbase.check_condition(
            active_cell.y0 <= band_index < active_cell.y1,
            'Deleted cell row is outside its cell')
        band = self.bands[band_index]
        if band.height <= 1:
            return
        crossing = self._cells_covering_band(band_index)
        trailing = [self._band_end_offset(cell, band_index) - 1
                    for cell in crossing]
        if any(crossing[index].rows[offset].strip()
               for index, offset in enumerate(trailing)):
            return
        for index, cell in enumerate(crossing):
            del cell.rows[trailing[index]]
        band.height -= 1

    def _position_for_cell_slot(self, cell, slot_index):
        provisional = GridPosition(0, 0, 0, cell.id, slot_index)
        return self.position(self.table_position(provisional))

    def _band_row_start(self, band_index):
        return 1 + sum(self.bands[index].height + 1
                       for index in range(band_index))

    def _band_line_for_row(self, row_num):
        for band_index, band in enumerate(self.bands):
            start = self._band_row_start(band_index)
            if start <= row_num < start + band.height:
                return band_index, row_num - start
        raise tbase.TableException('Expected a grid-table content row')

    def _boundary_for_row(self, row_num):
        for boundary in range(len(self.bands) + 1):
            if self._boundary_row(boundary) == row_num:
                return boundary
        return None

    def _band_line_for_cell_slot(self, cell, slot_index):
        remaining = slot_index
        for band_index in range(cell.y0, cell.y1):
            height = self.bands[band_index].height
            if remaining < height:
                return band_index, remaining
            remaining -= height
            boundary = band_index + 1
            if boundary in cell.boundary_slots:
                if remaining == 0:
                    return boundary, None
                remaining -= 1
        raise tbase.TableException('Grid cell row index is out of range')

    def render_lines(self, cell_alignments=None):
        cell_alignments = cell_alignments or {}
        widths = self._resolved_widths()
        lines = []
        for boundary in range(len(self.bands) + 1):
            lines.append(self.prefix +
                         self._render_separator(
                             boundary, widths, cell_alignments))
            if boundary == len(self.bands):
                continue
            for line_index in range(self.bands[boundary].height):
                lines.append(self.prefix + self._render_content_line(
                    boundary, line_index, widths, cell_alignments))
        return lines

    def render(self, cell_alignments=None):
        return '\n'.join(self.render_lines(cell_alignments))

    def _resolved_widths(self):
        widths = list(self.column_widths)
        changed = True
        while changed:
            changed = False
            for cell in self.cells:
                available = (sum(widths[cell.x0:cell.x1]) +
                             (cell.x1 - cell.x0 - 1))
                required = max([wlen(value) + 2 for value in cell.rows] + [3])
                if required > available:
                    widths[cell.x1 - 1] += required - available
                    changed = True
        return widths

    def _render_separator(self, boundary, widths, cell_alignments):
        segments = self.horizontal_edges[boundary]
        result = []
        for x in range(len(self.x_positions)):
            left_style = segments[x - 1] if x > 0 else None
            right_style = segments[x] if x < len(segments) else None
            vertical_above = (boundary > 0 and
                              self.vertical_edges[boundary - 1][x])
            vertical_below = (boundary < len(self.bands) and
                              self.vertical_edges[boundary][x])
            continuous = (0 < x < len(self.x_positions) - 1 and
                          left_style == right_style and
                          left_style is not None and
                          not vertical_above and not vertical_below)
            if self.horizontal_junctions[boundary][x]:
                result.append('+')
            elif continuous:
                result.append(left_style)
            elif left_style is not None or right_style is not None:
                result.append('+')
            elif vertical_above or vertical_below:
                result.append('|')
            else:
                result.append(' ')
            if x < len(segments):
                style = segments[x]
                result.append((style * widths[x]) if style else
                              (' ' * widths[x]))
        rendered = ''.join(result)
        coordinates = _rendered_x_positions(widths)
        spanning = [cell for cell in self.cells
                    if boundary in cell.boundary_slots]
        for cell in reversed(sorted(spanning, key=lambda item: item.x0)):
            offset = self._boundary_cell_row_offset(cell, boundary)
            value = cell.rows[offset]
            left = coordinates[cell.x0]
            right = coordinates[cell.x1]
            interior_width = right - left - 1
            body = _aligned_cell_body(
                value, interior_width, cell_alignments.get(cell.id))
            rendered = rendered[:left + 1] + body + rendered[right:]
        return rendered

    def _render_content_line(self, band_index, line_index, widths,
                             cell_alignments):
        result = []
        x = 0
        while x < len(self.column_widths):
            cell = self._cell_by_slot[(x, band_index)]
            tbase.check_condition(
                x == cell.x0,
                'Grid content line begins inside a spanning cell')
            result.append('|')
            interior_width = (sum(widths[cell.x0:cell.x1]) +
                              (cell.x1 - cell.x0 - 1))
            value = cell.rows[self._cell_row_offset(
                cell, band_index, line_index)]
            result.append(_aligned_cell_body(
                value, interior_width, cell_alignments.get(cell.id)))
            x = cell.x1
        result.append('|')
        return ''.join(result)

    def _cell_row_offset(self, cell, band_index, line_index):
        return (sum(self.bands[index].height
                    for index in range(cell.y0, band_index)) +
                sum(1 for boundary in cell.boundary_slots
                    if cell.y0 < boundary <= band_index) +
                line_index)

    def _boundary_cell_row_offset(self, cell, boundary):
        return (sum(self.bands[index].height
                    for index in range(cell.y0, boundary)) +
                sum(1 for candidate in cell.boundary_slots
                    if cell.y0 < candidate < boundary))


def _grid_prefix(line):
    match = re.match(r'^(\s*)\+', line)
    tbase.check_condition(match is not None,
                          'Grid table must start with a horizontal border')
    return match.group(1)


def _aligned_cell_body(value, width, alignment):
    value = value.rstrip()
    if alignment == 'center':
        value = value.strip()
    padding = max(2, width - wlen(value))
    if alignment == 'right':
        left = padding - 1
    elif alignment == 'center':
        left = 1 + (padding - 2) // 2
    else:
        left = 1
    right = padding - left
    return ' ' * left + value + ' ' * right


def _normalized_grid_lines(text):
    return [line.rstrip() for line in text.splitlines()]


def _visual_index(text, column):
    visual = 0
    for index, char in enumerate(text):
        if visual == column:
            return index
        next_visual = visual + wlen(char)
        tbase.check_condition(
            not visual < column < next_visual,
            'Grid boundary splits a wide character')
        visual = next_visual
    if visual == column:
        return len(text)
    raise tbase.TableException('Grid line is shorter than its border')


def _visual_char(text, column):
    index = _visual_index(text, column)
    return text[index] if index < len(text) else ''


def _char_at_visual(text, column):
    try:
        return _visual_char(text, column)
    except tbase.TableException:
        return None


def _edited_boundary_position(position, edit_start, delta):
    if position < edit_start:
        return position
    if position == edit_start and delta < 0:
        return None
    if position == edit_start:
        return position
    return position + delta


def _compound_edited_position(position, edit_start, boundary_delta,
                              content_start, content_delta):
    edited = _edited_boundary_position(
        position, edit_start, boundary_delta)
    if edited is None or content_delta == 0:
        return edited
    if edited < content_start:
        return edited
    return edited + content_delta


def _boundary_edit_content_line(line, expected_width, x_positions,
                                edit_start, boundary_delta,
                                content_start, content_delta):
    inserted = _compound_edited_position(
        edit_start, edit_start, boundary_delta,
        content_start, content_delta)
    if boundary_delta > 0:
        tbase.check_condition(
            _char_at_visual(line, inserted) == '|',
            'Inserted grid content boundary must be |')
    else:
        joined = edit_start
        if content_delta and joined >= content_start:
            joined += content_delta
        tbase.check_condition(
            _char_at_visual(line, joined - 1) != '|' and
            _char_at_visual(line, joined) != '|',
            'Deleted grid boundary must remove the structural |')

    placeholder = [' '] * expected_width
    for position in x_positions:
        actual = _compound_edited_position(
            position, edit_start, boundary_delta,
            content_start, content_delta)
        if actual is not None and _char_at_visual(line, actual) == '|':
            placeholder[position] = '|'
    tbase.check_condition(
        placeholder[0] == '|' and placeholder[-1] == '|',
        'Grid content rows must have complete outer edges')
    return ''.join(placeholder)


def _boundary_edit_separator_line(line, expected_width,
                                  edit_start, delta):
    if delta > 0:
        tbase.check_condition(
            _char_at_visual(line, edit_start) == '+',
            'Inserted grid border boundary must be +')

    result = []
    for position in range(expected_width):
        actual = _edited_boundary_position(position, edit_start, delta)
        if actual is not None:
            char = _char_at_visual(line, actual)
        else:
            before = _char_at_visual(line, edit_start - 1)
            after = _char_at_visual(line, edit_start)
            tbase.check_condition(
                before == after and before in '-=',
                'Deleted grid border boundary must join equal styles')
            char = before
        tbase.check_condition(
            char in '+-=',
            'Complete grid borders may only contain +, - or =')
        result.append(char)
    return ''.join(result)


def _has_vertical_at(text, column):
    visual = 0
    for char in text:
        if visual == column:
            return char == '|'
        next_visual = visual + wlen(char)
        if visual < column < next_visual:
            return False
        visual = next_visual
    return False


def _visual_slice(text, start, end):
    return text[_visual_index(text, start):_visual_index(text, end)]


def _cell_text(line, left, right):
    text = _visual_slice(line, left + 1, right).rstrip()
    if text.startswith(' '):
        text = text[1:]
    return text


def _collect_x_boundaries(lines):
    positions = set()
    for line in lines:
        if _FULL_BORDER_RE.match(line) is None:
            continue
        visual_positions = [0]
        for char in line:
            visual_positions.append(visual_positions[-1] + wlen(char))
        for index, char in enumerate(line):
            if char != '+' or index + 2 >= len(line):
                continue
            style = line[index + 1]
            if style not in '-=':
                continue
            end = index + 1
            while end < len(line) and line[end] == style:
                end += 1
            if end < len(line) and line[end] == '+':
                positions.add(visual_positions[index])
                positions.add(visual_positions[end])
    return sorted(positions)


def _separator_edges(line, x_positions, expected_width):
    if wlen(line) != expected_width:
        return [None] * (len(x_positions) - 1)
    raw_edges = []
    for left, right in zip(x_positions, x_positions[1:]):
        try:
            segment = _visual_slice(line, left + 1, right)
        except tbase.TableException:
            raw_edges.append(None)
            continue
        if segment and all(char == '-' for char in segment):
            edge = '-'
        elif segment and all(char == '=' for char in segment):
            edge = '='
        else:
            edge = None
        raw_edges.append(edge)

    edges = []
    malformed_structural_edge = False
    for index, style in enumerate(raw_edges):
        if style is None:
            edges.append(None)
            continue
        left_char = _char_at_visual(line, x_positions[index])
        right_char = _char_at_visual(line, x_positions[index + 1])
        left_continues = (index > 0 and
                          raw_edges[index - 1] == style and
                          left_char == style)
        right_continues = (index + 1 < len(raw_edges) and
                           raw_edges[index + 1] == style and
                           right_char == style)
        valid = ((left_char == '+' or left_continues) and
                 (right_char == '+' or right_continues))
        edges.append(style if valid else None)
        if not valid:
            malformed_structural_edge = (
                malformed_structural_edge or
                left_char == '+' or right_char == '+' or
                left_continues or right_continues)

    if malformed_structural_edge:
        raise tbase.TableException(
            'Grid horizontal edges require valid + anchors')
    return edges


def _band_vertical_edges(lines, band, x_positions):
    mappings = dict(
        (row_num, _map_content_boundaries(lines[row_num], x_positions))
        for row_num in range(band.source_start, band.source_end))
    first_keys = set(mappings[band.source_start])
    tbase.check_condition(
        all(set(mapping) == first_keys for mapping in mappings.values()),
        'Grid vertical edges must be consistent within a band')
    result = [index in first_keys for index in range(len(x_positions))]
    tbase.check_condition(
        result[0] and result[-1],
        'Grid content rows must have complete outer edges')
    return result, mappings


def _map_content_boundaries(line, x_positions):
    visual_width = wlen(line)
    mapping = dict(
        (index, position) for index, position in enumerate(x_positions)
        if _char_at_visual(line, position) == '|')
    tbase.check_condition(
        mapping.get(0) == 0 and
        mapping.get(len(x_positions) - 1) == visual_width - 1,
        'Grid content rows must have complete outer edges')
    return mapping


def _rendered_x_positions(widths):
    positions = [0]
    for width in widths:
        positions.append(positions[-1] + width + 1)
    return positions
