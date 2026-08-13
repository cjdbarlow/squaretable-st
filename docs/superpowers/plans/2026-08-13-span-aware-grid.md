# Span-Aware Grid Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` for every production change. This plan
> is executed inline because the user requested changes in the current
> worktree. Do not commit.

**Goal:** Replace destructive rectangular-grid normalization with a dedicated
point/edge lattice that preserves and edits rectangular rowspans and colspans,
while fixing the reviewed plugin and test-harness regressions.

**Architecture:** `table_grid_model.py` parses original grid source into atomic
x/y boundaries, styled edges, horizontal bands, and rectangular `GridCell`
components. `table_grid.py` performs edits on that model and adapts it to the
existing driver API. The legacy `TextTable` model remains the fallback for pipe
and incomplete tables.

**Tech Stack:** Python 3 / Sublime Text 4 plugin API / `unittest`

**Spec:** `docs/superpowers/specs/2026-08-13-span-aware-grid-design.md`

## Global Constraints

- Do not create, amend, or rewrite any Git commit.
- Preserve the user's existing uncommitted `README.md` changes.
- Use `apply_patch` for file edits.
- Write and run each regression test before its production change.
- Complete grids must never fall through to a span-destructive legacy edit.
- Incomplete grids and Pandoc pipe tables retain legacy behaviour.
- Span declarations come only from visible `|`, `-`, `=`, and `+` geometry.
- Explicit merge/split commands are out of scope.
- Column operations involving a span fail before mutation.

---

### Task 1: Make source text and standalone tests reliable

**Files:**

- Modify: `table_base.py:239-246,383-387,747-783`
- Modify: `table_package_test.py:1-107`
- Create: `test_suite.py`

**Interfaces:**

- Produces: `TextTable.source_text: str | None`
- Produces: `TextTable.set_render_lines(lines)` and
  `TextTable.clear_render_lines()`
- Produces: standard `python3 -m unittest discover` loading all standalone
  modules without importing `table_plugin_test` outside Sublime

- [ ] **Step 1: Write failing source-retention and render-override tests**

Add to `table_lib_test.py`:

```python
class SourceTextTest(unittest.TestCase):

    def test_parser_retains_exact_source_text(self):
        text = "+---+\n| a |\n+---+"
        table = table_lib.pandoc_syntax().table_parser.parse_text(text)
        self.assertEqual(text, table.source_text)

    def test_explicit_render_lines_override_normalized_rows(self):
        table = table_lib.pandoc_syntax().table_parser.parse_text(
            "+---+\n| a |\n+---+")
        table.set_render_lines(["one", "two"])
        self.assertEqual(["one", "two"], table.render_lines())
        table.clear_render_lines()
        self.assertNotEqual(["one", "two"], table.render_lines())
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  table_lib_test.SourceTextTest
```

Expected: failure because `source_text`, `set_render_lines`, and
`clear_render_lines` do not exist.

- [ ] **Step 3: Add source retention and transactional rendered lines**

In `TextTable.__init__`, initialize:

```python
self.source_text = None
self._render_lines_override = None
```

Add:

```python
def set_render_lines(self, lines):
    self._render_lines_override = list(lines)

def clear_render_lines(self):
    self._render_lines_override = None

def render_lines(self):
    if self._render_lines_override is not None:
        return list(self._render_lines_override)
    return [self.prefix + row.render() for row in self.rows]
```

At the beginning of `BaseTableParser.parse_text`, after creating the table:

```python
table.source_text = text
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Step 2 command. Expected: both tests pass.

- [ ] **Step 5: Replace the bytecode-writing package test**

First change `test_plugin_compiles_without_syntax_warnings` to compile in
memory:

```python
def test_plugin_compiles_without_syntax_warnings(self):
    with open('table_plugin.py', encoding='utf-8') as stream:
        source = stream.read()
    with warnings.catch_warnings():
        warnings.simplefilter('error', SyntaxWarning)
        compile(source, 'table_plugin.py', 'exec')
```

Replace the unused `subprocess` and `sys` imports with `warnings`.

- [ ] **Step 6: Add an explicit standalone discovery loader**

Create `test_suite.py`:

```python
import importlib.util


STANDALONE_MODULES = (
    'table_lib_test',
    'table_grid_model_test',
    'table_grid_test',
    'table_list_test',
    'table_package_test',
    'table_plugin_unit_test',
)


def load_tests(loader, unused_tests, unused_pattern):
    names = list(STANDALONE_MODULES)
    if importlib.util.find_spec('sublime') is not None:
        names.append('table_plugin_test')
    return loader.loadTestsFromNames(names)
```

Create `table_grid_model_test.py` initially with only `import unittest`; Task 2
will populate it.

- [ ] **Step 7: Verify discovery and repository cleanliness**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -q
git diff --check
git status --short
```

Expected: the existing standalone tests pass, discovery runs a non-zero test
count, `table_plugin_test` does not error outside Sublime, and no new
`__pycache__` entry appears in Git status.

---

### Task 2: Parse grid source into a point/edge lattice

**Files:**

- Create: `table_grid_model.py`
- Modify: `table_grid_model_test.py`

**Interfaces:**

- Produces: `GridDocument.from_text(text) -> GridDocument`
- Produces: `GridDocument.try_from_text(text) -> GridDocument | None`
- Produces: `GridCell(x0, y0, x1, y1, rows)`
- Produces: `GridBand(height, source_start, source_end)`
- Produces: `GridDocument.cells`, `bands`, `column_widths`,
  `horizontal_edges`, and `vertical_edges`
- Throws: `table_base.TableException` for complete but malformed grids

- [ ] **Step 1: Write failing rectangular and colspan inference tests**

Add:

```python
import table_base as tbase
import table_grid_model as model


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
+---+---+
| merged  |
+---+---+""")
        self.assertEqual([(0, 0, 2, 1)],
                         [cell.bounds() for cell in grid.cells])
        self.assertEqual(["merged"], grid.cells[0].rows)
```

- [ ] **Step 2: Run the two tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  table_grid_model_test.GridGeometryParseTest
```

Expected: import failure because `table_grid_model` does not exist.

- [ ] **Step 3: Implement geometry value objects and visual-coordinate helpers**

Create plain Python classes compatible with Sublime's runtime:

```python
class GridBand(object):
    def __init__(self, height, source_start, source_end):
        self.height = height
        self.source_start = source_start
        self.source_end = source_end


class GridCell(object):
    def __init__(self, x0, y0, x1, y1, rows=None):
        self.x0, self.y0 = x0, y0
        self.x1, self.y1 = x1, y1
        self.rows = list(rows or [])

    def bounds(self):
        return self.x0, self.y0, self.x1, self.y1


def visual_positions(text):
    positions = [0]
    column = 0
    for char in text:
        column += wlen(char)
        positions.append(column)
    return positions
```

Import `wlen` from `widechar_support` using the repository's relative/absolute
fallback pattern.

- [ ] **Step 4: Implement boundary and band parsing**

`GridDocument.from_text` must:

```python
@classmethod
def from_text(cls, text):
    lines = text.splitlines()
    prefix = _common_grid_prefix(lines)
    bodies = [line[len(prefix):] for line in lines]
    _validate_complete_outer_border(bodies)
    x_visuals = _collect_x_boundaries(bodies)
    separators = _separator_rows(bodies, x_visuals)
    bands = _bands_between(separators)
    horizontal = _horizontal_edges(bodies, separators, x_visuals)
    vertical = _vertical_edges(bodies, bands, x_visuals)
    return cls(prefix, x_visuals, bands, horizontal, vertical, bodies)
```

Separator recognition is segment-based: a line is a y-boundary when it
contains at least one `-` or `=` run between inferred x-boundaries. A band is
the non-empty sequence of content lines between adjacent y-boundaries.

- [ ] **Step 5: Infer cells with union/find and rectangular validation**

Create one slot for every `(x_interval, band)`. Union horizontally when the
intervening vertical edge is absent and vertically when the intervening
horizontal segment is absent. For every component:

```python
x0 = min(x for x, unused_y in slots)
x1 = max(x for x, unused_y in slots) + 1
y0 = min(y for unused_x, y in slots)
y1 = max(y for unused_x, y in slots) + 1
expected = {(x, y) for x in range(x0, x1)
                     for y in range(y0, y1)}
tbase.check_condition(set(slots) == expected,
                      'Grid cells must be rectangular')
```

Also validate that every internal edge in the component is absent and every
outer perimeter edge is present. Extract one content row per physical content
line covered by the cell, removing one structural leading space and trailing
layout padding.

- [ ] **Step 6: Verify rectangular and colspan parsing GREEN**

Run the Step 2 command. Expected: both tests pass.

- [ ] **Step 7: Add failing rowspan, combined-span, and invalid-shape tests**

Add:

```python
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
```

- [ ] **Step 8: Run the new tests, confirm the expected RED, then complete validation**

Run the Step 2 command. Confirm at least one new assertion fails because
vertical unions/rectangle validation are incomplete. Complete the minimal edge
validation and rerun until the full class passes.

- [ ] **Step 9: Add complete-grid classification tests**

```python
def test_try_from_text_returns_none_for_pipe_and_incomplete_tables(self):
    self.assertIsNone(model.GridDocument.try_from_text('| A | B |'))
    self.assertIsNone(model.GridDocument.try_from_text('+---+\n| A |'))

def test_try_from_text_keeps_malformed_complete_grid_as_error(self):
    with self.assertRaises(tbase.TableException):
        model.GridDocument.try_from_text(
            '+---+---+\n| A     |\n|   +---+\n|   | B |\n+---+---+')
```

Implement `try_from_text` so only non-grid and incomplete input return `None`;
a complete-looking malformed grid remains an actionable error.

---

### Task 3: Render spans losslessly and respond to manual edges

**Files:**

- Modify: `table_grid_model.py`
- Modify: `table_grid_model_test.py`

**Interfaces:**

- Produces: `GridDocument.render_lines() -> list[str]`
- Produces: `GridDocument.render() -> str`
- Produces: `GridDocument.cell_at(row_num, visual_field_num) -> GridCell`

- [ ] **Step 1: Write failing exact round-trip tests**

Add a `ROWSPAN_FIXTURE` constant containing the complete user-supplied table
from `pasted-text.txt`. Add:

```python
class GridGeometryRenderTest(unittest.TestCase):

    def assert_round_trip(self, text):
        self.assertEqual(text, model.GridDocument.from_text(text).render())

    def test_round_trips_simple_colspan(self):
        self.assert_round_trip("""\
+---+---+
| merged  |
+---+---+""")

    def test_round_trips_supplied_multi_rowspan_table(self):
        self.assert_round_trip(ROWSPAN_FIXTURE)
```

- [ ] **Step 2: Run render tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  table_grid_model_test.GridGeometryRenderTest
```

Expected: failure because `render` is absent.

- [ ] **Step 3: Implement edge-driven separator rendering**

For each y-boundary, render every atomic horizontal segment with its stored
style or spaces. Render nodes with this precedence:

```python
if left_horizontal or right_horizontal:
    node = '+'
elif vertical_above or vertical_below:
    node = '|'
else:
    node = ' '
```

This reproduces partial separators such as `|       +---+`.

- [ ] **Step 4: Implement cell-driven content rendering**

For every band line, find the cell covering each atomic slot. Render one cell
only at its `x0`, using the combined covered width:

```python
interior_width = (sum(column_widths[cell.x0:cell.x1]) +
                  (cell.x1 - cell.x0 - 1))
value = cell.rows[cell_slot_offset(cell, band, line)]
body = ' ' + value
body += ' ' * max(0, interior_width - wlen(body))
```

Emit `|` only where the vertical-edge matrix says a boundary exists.

- [ ] **Step 5: Implement width constraints**

Retain parsed atomic widths as lower bounds. For every cell row, require:

```python
required = wlen(value) + 2
available = (sum(widths[cell.x0:cell.x1]) +
             (cell.x1 - cell.x0 - 1))
if required > available:
    widths[cell.x1 - 1] += required - available
```

Run constraints until no width changes remain, then render. This handles
nested span constraints deterministically.

- [ ] **Step 6: Verify round trips GREEN**

Run the Step 2 command. Expected: both fixtures round-trip exactly.

- [ ] **Step 7: Add manual declaration and Unicode tests**

Add tests that parse an ordinary two-column/two-band grid, remove the middle
`|` from one band to produce a colspan, and replace a horizontal segment with
spaces to produce a rowspan. Assert the cell bounds change, then restore the
source characters and assert the original four cells return.

Add:

```python
def test_expands_rightmost_covered_column_for_wide_content(self):
    grid = model.GridDocument.from_text("""\
+---+---+
| 漢字    |
+---+---+""")
    lines = grid.render_lines()
    self.assertEqual(len(set(wlen(line) for line in lines)), 1)
```

Run the render test class, confirm new failures if visual-width expansion is
incomplete, then implement only the missing width behaviour.

---

### Task 4: Implement cell-row operations over spanned cells

**Files:**

- Modify: `table_grid_model.py`
- Rewrite relevant internals: `table_grid.py:15-328`
- Modify: `table_grid_test.py`

**Interfaces:**

- Produces: `GridPosition(cell_id, slot_index, row_num, field_num)`
- Produces: `GridDocument.position(TablePos) -> GridPosition`
- Produces: `GridDocument.table_position(GridPosition) -> TablePos`
- Produces: span-aware `insert_cell_row`, `delete_cell_row`,
  `move_cell_row`, `indent_cell_rows`, and `outdent_cell_rows`
- Preserves: `table_grid.GridTable(table)` as the public adapter used by
  existing tests and `GridTableDriver`

- [ ] **Step 1: Write failing position and rowspan-slot tests**

Add a compact partial-separator fixture and assert:

```python
grid = self.parse_grid("""\
+---+---+
| A | B |
|   +---+
|   | D |
+---+---+""")
first = grid.position(tbase.TablePos(1, 0))
second = grid.position(tbase.TablePos(3, 0))
self.assertEqual(first.cell_id, second.cell_id)
self.assertEqual((0, 1), (first.slot_index, second.slot_index))
```

Run the focused test and verify RED because rectangular `GridTable` treats
partial separators as data rows.

- [ ] **Step 2: Adapt `GridTable` to `GridDocument`**

On construction, require `table.source_text` and parse it through
`GridDocument`. Re-export or wrap `GridPosition` so driver callers retain a
single position type. `commit()` must validate, render, then atomically call:

```python
self.table.set_render_lines(self.document.render_lines())
```

It must not overwrite `table.rows` or call legacy `pack()`.

- [ ] **Step 3: Implement band-aware insertion and test RED/GREEN**

Write tests for insertion inside an ordinary cell, a rowspan before a partial
separator, and a colspan. Assert neighbouring cell values retain order and
partial edges remain unchanged.

Implementation order:

```python
band, line = document.slot_coordinate(position)
for cell in document.cells_covering_band(band):
    if cell.id == position.cell_id:
        cell.rows.insert(position.slot_index + 1, continuation)
    else:
        cell.rows.insert(document.band_end_offset(cell, band), '')
document.bands[band].height += 1
document.renumber_cell(position.cell_id, position.slot_index + 1,
                       preserved_start)
```

Run only insertion tests after writing each one; observe RED before adding its
minimal production behaviour.

- [ ] **Step 4: Implement deletion and safe band contraction RED/GREEN**

Tests must cover deletion from a rowspan, deletion when another cell uses the
band's final line, contraction when the final line is blank everywhere, and
the one-line minimum.

After shifting the active cell values, inspect the containing band's final
slot in every crossing cell. Remove that slot and decrement height only when
all are blank and height is greater than one.

- [ ] **Step 5: Implement movement across absent partial edges RED/GREEN**

Add a test that moves `A2` within a rowspan from below a Detail-only separator
to above it. Assert the partial separator source row is unchanged. Add the
opposite test for a cell actually bounded by that separator and expect
`TableException`.

Movement swaps adjacent entries only in `GridCell.rows`; being in the same
cell is the proof that no active-cell edge is crossed.

- [ ] **Step 6: Implement selection edits over rowspan slots RED/GREEN**

Add tests selecting list items above and below a partial separator within one
rowspan. Assert indentation and ordered renumbering ignore the physical
separator row. Preserve the existing rejection tests for endpoints in
different cells.

- [ ] **Step 7: Run all model and cell-operation tests**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  table_grid_model_test table_grid_test table_list_test
```

Expected: all pass with no warnings.

---

### Task 5: Integrate navigation, logical rows, and safe command routing

**Files:**

- Modify: `table_grid_model.py`
- Modify: `table_grid.py:330-439`
- Modify: `table_grid_test.py`
- Modify: `table_base.py`

**Interfaces:**

- Produces: `GridDocument.next_position` and `previous_position`
- Produces: `GridDocument.logical_rows()` as ranges bounded by full-width
  horizontal edges
- Produces: `GridTableDriver.get_cursor` based on rendered grid geometry
- Produces: complete-grid routing for every inherited driver command

- [ ] **Step 1: Write failing span-aware navigation tests**

Test reading order through the compact rowspan fixture. Starting on `A` at the
first physical line, Tab must visit `B`, then the same rowspan's next physical
slot, then `D`. Shift-Tab must reverse those positions and never return a
separator row.

Run the new tests and verify RED against the rectangular navigation code.

- [ ] **Step 2: Implement a physical-position index**

Build ordered entries `(physical_row, visual_field, cell_id, slot_index)` for
every visible cell occurrence on every content line. `next_position` and
`previous_position` move through this list. At the end, `next_position` appends
a blank unspanned logical row through the model before returning its first
entry.

- [ ] **Step 3: Override grid cursor placement**

`GridTableDriver.get_cursor(table, table_pos)` must use the committed or freshly
parsed `GridDocument` to locate the rendered left edge of the visible cell and
return the first content column. Add plugin-unit coverage with a caret in a
colspan and below a partial separator.

- [ ] **Step 4: Write failing logical-row span-preservation tests**

Create two logical rows where the first contains internal rowspans and
colspans. Move it down, then assert its complete rendered segment—including
partial separator lines—is unchanged. Test insertion, deletion, and rejection
across a full-width `=` border.

- [ ] **Step 5: Implement logical-row slicing**

Full-width horizontal boundaries are those with a present horizontal edge in
every atomic interval. Logical rows are the source/model ranges between
successive full-width boundaries. Move their bands, cells, and internal edge
rows as one unit, remapping y-coordinates afterward.

- [ ] **Step 6: Route alignment and row operations exclusively through the model**

Override `editor_align`, field navigation, cell operations, and logical-row
operations in `GridTableDriver`. `_apply_or_fallback` must use
`GridDocument.try_from_text(table.source_text)` rather than the old
first-border predicate.

- [ ] **Step 7: Add incomplete-grid fallback RED/GREEN**

Retain `+---+\n| a |` as the regression fixture. Assert Enter uses
`BorderTableDriver.editor_next_row` instead of raising “must end with a
horizontal border.” Implement fallback only after observing the failure.

- [ ] **Step 8: Make inherited structural commands safe**

Add tests for move/insert/delete column, horizontal-line insertion, and join on
a spanned grid. Column operations touching a span and other unsupported
operations must raise before `table.render_lines()` changes. Unspanned grid
operations may use a model implementation or the legacy driver only after a
test proves the geometry is unchanged.

Audit every `TableDriver` and `BorderTableDriver` public `editor_*` method; no
complete-grid mutation may remain inherited accidentally.

- [ ] **Step 9: Run core regression suites**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  table_lib_test table_grid_model_test table_grid_test table_list_test
```

Expected: all pass.

---

### Task 6: Fix plugin safety and compatibility regressions

**Files:**

- Modify: `table_plugin.py:22-93,223-255,295-495,529-580`
- Modify: `table_plugin_unit_test.py`
- Modify: all three `Default (*.sublime-keymap)` files
- Modify: `table_package_test.py`
- Modify: `table_pandoc_syntax.py:28-36`
- Modify: `table_re_structured_text_syntax.py:27-35`
- Modify: `table_grid_test.py`

**Interfaces:**

- Produces: safe command context creation with status-message failures
- Produces: one-caret policy for all complete-grid structural commands
- Preserves: legacy selected-text navigation outside complete grids
- Preserves: configured pipe-table whitespace behaviour

- [ ] **Step 1: Write a failing palette-safety test**

In `table_plugin_unit_test.py`, run every new palette-exposed command against
`ordinary text`. Assert no exception, no text change, and one status message.
Verify RED: current context creation raises `IndexError` before the handler.

- [ ] **Step 2: Move context construction into the validation boundary**

`run_one_sel` and `CellRowsSelectionCommand.run` must catch expected context
failures before any view mutation. Convert empty/non-table parse conditions to
`TableException`. Add `is_enabled`/`is_visible` for cell commands when feasible,
but retain runtime validation because command enablement is not a security
boundary.

- [ ] **Step 3: Write a failing multi-caret logical-row test**

Use A/B/C logical rows with carets on A and B. Assert `MoveRowDown` leaves text
unchanged and reports the one-caret message. Verify RED: current output is
B/C/A.

- [ ] **Step 4: Centralize the complete-grid single-caret guard**

Apply a mixin/helper to cell-row and logical-row insert/delete/move commands.
Only complete grids are restricted; legacy multi-caret table behaviour remains
unchanged.

- [ ] **Step 5: Write and fix pipe whitespace regressions**

Add tests using `TableConfiguration.keep_space_left = False` and a Pandoc pipe
cell containing three leading spaces. Verify it renders with legacy trimming.
Remove unconditional `self.keep_space_left = True` assignments from Pandoc and
reStructuredText constructors. Grid indentation remains covered by model
round-trip tests.

- [ ] **Step 6: Write failing selected-navigation keymap tests**

Update package tests to require:

- non-empty selections on complete grids bind Tab/Shift-Tab to indent/outdent;
- empty selections retain navigation;
- non-empty selections outside complete grids retain legacy navigation.

Verify the third condition fails with current global `selection_empty: true`.

- [ ] **Step 7: Scope the keybindings on all platforms**

Keep the empty-selection navigation bindings. Add non-empty-selection legacy
navigation bindings guarded by `table_editor_multiline_grid != true`, while the
grid indent/outdent bindings remain guarded by
`table_editor_multiline_grid == true`. Apply identical logical contexts to
Linux, macOS, and Windows files.

- [ ] **Step 8: Guard direct-edit commands before mutation**

`TableEditorSplitColumnDown` currently removes source text before rebuilding a
context. Add a complete-grid/span check before `remove_rest_line`; reject when
the dedicated model does not implement the operation. Add a regression test
asserting exact text preservation on the supplied rowspan fixture.

- [ ] **Step 9: Run plugin and package suites**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  table_plugin_unit_test table_package_test table_grid_test
```

Expected: all pass.

---

### Task 7: Document spans and verify the complete worktree

**Files:**

- Modify: `README.md` without discarding its current uncommitted content
- Modify: tests only if final integration evidence exposes a missing case

**Interfaces:**

- Documents: lattice-declared rowspans/colspans, manual edge editing,
  supported operations, and safe refusals

- [ ] **Step 1: Update README span documentation**

Extend “Multiline grid additions” with compact examples:

```text
+---+---+
| colspan|
+---+---+

+---+---+
| row | A |
| span+---+
|     | B |
+---+---+
```

Explain that missing `|` edges create colspans and missing horizontal segments
create rowspans; restoring the edges splits them. Clarify that partial borders
apply only to the cells they cross.

- [ ] **Step 2: Run the fresh full standalone suite**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v
```

Expected: a non-zero number of tests, all passing, with the Sublime-only module
excluded or skipped cleanly.

- [ ] **Step 3: Run syntax and whitespace verification**

```bash
python3 - <<'PY'
from pathlib import Path
import warnings

for path in sorted(Path('.').glob('*.py')):
    with warnings.catch_warnings():
        warnings.simplefilter('error', SyntaxWarning)
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')
print('compiled all Python sources without SyntaxWarning')
PY
git diff --check
```

Expected: compile message, exit zero, and no whitespace errors.

- [ ] **Step 4: Re-run the four original defect reproductions**

Verify:

- palette cell commands on ordinary text do not raise;
- two grid row-move carets do not mutate the table;
- explicit `keep_space_left=False` remains false for Pandoc pipe tables; and
- Enter on an unfinished grid uses legacy editing.

- [ ] **Step 5: Verify the supplied rowspan table manually through the model**

Parse the exact attachment fixture, assert exact render equality, perform an
insert and move inside a spanning cell, reparse the result, and assert the same
cell bounds and partial-edge matrix remain.

- [ ] **Step 6: Inspect final scope without committing**

```bash
git status --short --branch
git diff --stat
git diff --check
```

Expected: only intended implementation, test, documentation, design, and plan
changes; no commit created by this work.

---

## Review Corrections (approved 2026-08-13)

The following tasks correct verified review findings. They are executed inline
in the existing worktree because the user explicitly requested implementation
without commits. Every production change is preceded by the named failing
regression.

### Task 9: Make grid geometry coordinate-driven and lossless

**Files:**

- Modify: `table_grid_model.py`
- Modify: `table_grid_model_test.py`

**Interfaces:**

- `GridDocument.from_text(text)` discovers x-boundaries from validated
  horizontal junctions across all source lines.
- Structural pipes are recognized only at established visual coordinates.
- Partial boundary lines retain content inside cells that cross the boundary.

- [ ] Add failing exact-round-trip tests for Pandoc's canonical spanning-header
  table, raw `|`, escaped `\|`, an rST `|name|` substitution, and `|---|`
  content.
- [ ] Add failing malformed-input tests for a shifted structural boundary and
  a horizontal edge with a missing `+` anchor.
- [ ] Verify those tests fail for boundary discovery, pipe coercion, or
  separator misclassification rather than fixture errors.
- [ ] Replace nearest-boundary assignment with exact visual-coordinate
  matching, discover junction coordinates across the table, validate edge
  anchors, and render continuous edges through undeclared internal junctions.
- [ ] Preserve non-empty content on partial separator rows in the spanning
  cell's ordered physical slots and render it back at the boundary.
- [ ] Run `table_grid_model_test` and `table_grid_test` to green.

### Task 10: Keep deletion and cached rendering local and current

**Files:**

- Modify: `table_grid_model.py`
- Modify: `table_grid_model_test.py`
- Modify: `table_base.py`
- Modify: `table_lib_test.py`

**Interfaces:**

- Band contraction consumes the deletion slot's band index.
- `TextTable.pack()` invalidates source/render derivatives for normalized-model
  mutations; parsers restore exact source after their final pack.

- [ ] Add a failing two-band rowspan regression where deleting in the lower
  band must not contract a blank line in the upper band.
- [ ] Pass the containing band explicitly to contraction and inspect only that
  band's trailing row.
- [ ] Add a failing regression showing `pack()` after a render override must not
  render stale lines.
- [ ] Invalidate `source_text` and `_render_lines_override` at the beginning of
  `pack()`, and move parser source assignment after the final pack.
- [ ] Run the focused model and source-retention tests to green.

### Task 11: Restore safe atomic-column operations and separator carets

**Files:**

- Modify: `table_grid_model.py`
- Modify: `table_grid.py`
- Modify: `table_grid_test.py`

**Interfaces:**

- `GridDocument.move_column`, `insert_column`, and `delete_column` mutate an
  atomic column only when all affected cells are unspanned.
- `GridDocument.position_near(table_pos, direction)` maps full separators to
  adjacent content while partial separators with content map directly.
- Alignment commits without requiring a content position.

- [ ] Add failing driver tests for moving, inserting, and deleting columns in
  an ordinary complete grid plus refusal when an affected cell is spanned.
- [ ] Implement atomic-column transforms that preserve unaffected span edges,
  widths, cells, and header styles, then rebuild cell indexes.
- [ ] Add failing tests for align, Tab, Shift-Tab, and logical-row commands from
  top, internal, partial, and bottom separators.
- [ ] Give each driver operation an explicit separator policy: alignment keeps
  the original row, forward navigation chooses below, reverse navigation
  chooses above, and logical-row operations choose the adjacent logical row.
- [ ] Run all grid-model and grid-driver tests to green.

### Task 12: Make Sublime routing and error recovery span-safe

**Files:**

- Modify: `table_plugin.py`
- Modify: `table_plugin_unit_test.py`

**Interfaces:**

- Complete-grid context detection parses the contiguous grid candidate with
  `GridDocument.try_from_text` rather than relying on a restrictive row regex.
- `on_query_context` evaluates each selection and honors `match_all`.
- Failed operations return the exact original `Region`.

- [ ] Add failing tests proving partial separators remain inside the detected
  candidate and multi-caret logical-row edits are rejected there.
- [ ] Add failing mixed-selection tests for both equal and not-equal custom
  context queries with `match_all=True` and `False`.
- [ ] Add failing command tests on complete-grid borders asserting unchanged
  text, unchanged selection, and a status message without a traceback.
- [ ] Implement shared-model candidate validation, per-selection context
  reduction, and original-selection error returns in abstract and split
  commands.
- [ ] Run all plugin and package tests to green.

### Task 13: Document and verify the corrected contract

**Files:**

- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-13-span-aware-grid-design.md`

- [ ] Update documentation to state that boundaries are coordinate-based,
  literal pipes remain content, and partial separator lines may contain
  rowspan-cell content.
- [ ] Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -q`.
- [ ] Compile every Python source in memory with `SyntaxWarning` promoted to an
  error.
- [ ] Run `git diff --check`, inspect `git status --short`, and verify HEAD did
  not change.
