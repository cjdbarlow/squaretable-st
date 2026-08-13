# Span-Aware Grid Editing Design

**Status:** Implemented in the current uncommitted worktree

## Purpose

SquareTable will edit complete Pandoc and reStructuredText grid tables without
destroying cells declared by the table's border geometry. Missing vertical
boundaries declare column spans, and missing horizontal edge segments declare
row spans. Users create or remove spans by editing those visible boundaries;
there is no hidden span state and no merge/split command in this scope.

This work also resolves the defects found in the review of the multiline-grid
feature: unsafe palette invocation, multi-caret logical-row edits, pipe-table
whitespace regressions, selection-sensitive keymap regressions, incomplete-grid
handling, and unreliable standalone test discovery.

No commits will be created as part of this implementation.

## Scope

The span-aware path applies only to complete bordered grids using the Pandoc or
reStructuredText table syntax. It supports:

- lossless parsing and rendering of rectangular cells with row spans,
  column spans, or both;
- cell-row insert, delete, move, indent, and outdent operations;
- field navigation through physical content positions;
- full logical-row insert, delete, and move operations;
- alignment that retains the declared cell topology;
- header separators represented by `=` edges;
- display-width-aware layout for the repository's supported wide characters;
- fresh span inference after users manually add or remove source boundaries.

Incomplete grids continue through the legacy table driver. Pipe tables and all
other syntaxes retain their previous behaviour. Explicit commands for merging
or splitting cells are out of scope.

Existing column operations keep the current span policy: moving, inserting,
or deleting an atomic column involved in a span is refused rather than
implicitly splitting or discarding the merged cell. Any legacy command that
cannot safely preserve a span-aware grid must fail before mutation.

## Geometry Model

### Coordinate lattice

The dedicated grid model uses logical boundary coordinates rather than raw
character offsets. Consecutive x-boundaries define atomic columns; consecutive
y-boundaries define horizontal bands.

A normal cell occupies the rectangle `(x0, y0) -> (x1, y1)`. A three-band row
span occupies `(x0, y0) -> (x1, y3)`, and a two-column span occupies
`(x0, y0) -> (x2, y1)`.

The lattice contains:

- logical points at all inferred x/y boundary intersections;
- horizontal edges styled `-`, `=`, or absent;
- vertical edges styled `|` or absent;
- physical content-line heights for every horizontal band.

Literal `+` characters that anchor a horizontal `-` or `=` run provide
junction evidence across the whole table. The top border is not authoritative:
a spanning header may omit an internal junction that a later separator
reveals. Points also exist where a span intentionally omits a literal
junction. The adjoining edge segments, rather than a `+` alone, determine
whether a boundary exists.

### Parsing

Parsing operates on the original source lines retained by the table parser.
All character positions are converted to visual columns with the existing
wide-character helpers before coordinates are compared.

The parser:

1. extracts and validates a consistent indentation prefix;
2. requires complete top and bottom horizontal borders;
3. collects x-boundaries from validated horizontal junctions across the whole
   table, including boundaries omitted by spanning top or header cells;
4. identifies full and partial separator lines as y-boundaries;
5. records horizontal edge style for every atomic column interval;
6. records vertical edges for every x-boundary within each content band;
7. creates atomic `(column, band)` slots;
8. joins neighbouring slots across absent edges; and
9. converts each connected component into one rectangular `GridCell`.

A `|` is structural only when it occurs at an established x-boundary. Pipes
elsewhere remain cell content, including Markdown `\|` escapes and
reStructuredText substitution references such as `|name|`. A horizontal run
is structural only when its endpoints are valid `+` junctions; text such as
`|---|` remains content. Candidate x-boundaries are collected from complete
structural separator rows, so a literal `+---+` within a content row cannot
invent new geometry.

A connected component must fill its complete bounding rectangle. Inconsistent
visual coordinates, content that pushes structural boundaries away from the
declared lattice, changing vertical boundaries inside one physical band, open
outer edges, contradictory edge styles, invalid junction anchors, and
L-shaped components are invalid. They raise `TableException` without altering
the buffer. The parser does not guess shifted boundaries because doing so can
reinterpret literal pipes as geometry and lose data.

### Cells and content positions

Each `GridCell` records its x/y extents and its ordered physical content slots.
A row-spanning cell's slots are flattened across every band it covers. Partial
separator lines in other columns are not content slots and do not divide that
cell.

Positions map a physical content line and visible field to a cell plus a slot
index. A caret can therefore move within a rowspan across partial horizontal
edges that do not cross that cell.

### Rendering

The renderer reconstructs content lines and separator lines from the lattice:

- present horizontal edges render as their stored `-` or `=` style;
- absent horizontal edges render as spaces;
- present vertical edges render as `|`;
- absent vertical edges become interior cell width;
- a node renders `+` when a horizontal edge meets it, `|` when only a
  continuing vertical edge crosses it, and a space otherwise.

Existing atomic widths and band heights are lower bounds, limiting unrelated
format churn. A non-spanning cell constrains one atomic width. A colspan
constrains the combined width of all covered columns, including the character
positions gained from omitted internal vertical edges. If edited content needs
more room, the deficit is added deterministically to the rightmost covered
atomic column.

The renderer removes one structural padding space at each cell's left edge
when parsing and restores it when rendering. Additional leading whitespace is
cell content, so grid-list indentation survives independently of the legacy
`keep_space_left` preference.

## Editing Semantics

### Cell rows

Every horizontal band has at least one physical content line.

Inserting after an active cell slot increases the containing band's height at
its bottom. The active cell's later values shift to make room after the caret;
all other cells crossing that band gain a blank trailing slot, preserving their
content order.

Deleting clears or removes the active value and shifts only later values in
that same cell. A band loses its trailing physical line only when that line is
blank in every cell crossing the band and the band would still retain one
line. Only the band containing the deleted slot is eligible for contraction.

Moving swaps adjacent content values within the active cell's flattened slot
sequence. A move can cross a partial separator when the corresponding
horizontal edge is absent over the active cell, but it cannot cross that
cell's actual top or bottom edge.

Indenting and outdenting operate on selected slots only when both selection
endpoints map to the same cell. Separator lines crossed by a rowspan selection
are ignored. Existing list continuation and ordered-list renumbering rules are
retained.

### Navigation

Tab and Shift-Tab traverse visible fields in physical reading order. A cell
spanning multiple physical content lines can be visited once on each relevant
line, matching the existing multiline navigation model. Navigation never lands
on a separator line.

### Logical rows

A full-width horizontal edge divides logical rows. Moving a logical row carries
its complete set of bands, partial separators, cells, and bottom full-width
border. A logical row cannot move across a full-width `=` header boundary.

Insertion creates a one-band, one-line unspanned logical row using the current
atomic columns. Deletion removes the complete logical row; deleting the only
row leaves one blank unspanned row.

### Atomic columns

Existing move, insert, and delete column commands remain available when every
affected cell is unspanned. The model rejects the operation before mutation if
the affected atomic column or its movement neighbour participates in a row or
column span. Safe operations preserve header separators and rebuild a valid
complete grid.

### Declarative span changes

The source is reparsed for every command, so manual geometry edits immediately
change the inferred cells:

- removing a vertical `|` boundary consistently through a band joins the
  adjacent atomic slots into a colspan;
- restoring that vertical edge splits the colspan;
- removing a horizontal `-` or `=` segment joins the slots above and below
  into a rowspan; and
- restoring that segment, with the appropriate `+` junctions, splits the
  rowspan.

There is no cached or hidden span declaration that can disagree with the text.

## Plugin Integration and Safety

The generic parser retains original source lines on its `TextTable`. The grid
driver builds `GridDocument` from those lines and attaches rendered lines back
to the table for the existing merge routine. The normalized legacy row model
remains the fallback for pipe and incomplete tables.

The grid driver owns span-aware cursor placement and every operation that can
modify a complete grid. Commands that are not span-safe raise `TableException`
before the table or view is changed. Commands invoked on a separator map to a
deterministic adjacent content position where that command is meaningful;
alignment does not require a content position. Expected failures return the
original selection unchanged.

New palette commands validate that there is exactly one appropriate selection
and a complete supported grid before constructing an operational context.
Context-creation failures become status messages rather than uncaught
exceptions.

Cell-row and logical-row structural commands require one caret on complete
grids. Complete-grid detection parses the entire contiguous candidate with the
shared grid model, so partial rowspan separators cannot divide the candidate
or bypass this guard. This prevents sequential rewrites from applying later
carets to stale physical positions.

Grid-specific selection bindings remain restricted to complete grids. The
custom Sublime context evaluates each selection separately and implements
`match_all` using all/any semantics. Legacy Tab, Shift-Tab, and Enter behaviour
remains available for selections in pipe and other table syntaxes.

Pandoc and reStructuredText syntax constructors no longer override
`TableConfiguration.keep_space_left`. Pipe tables honour the setting; grid
indentation is handled by the dedicated renderer.

## Error Handling

Grid parsing and operations are transactional: validation and the requested
model mutation complete before rendered lines replace the view. Expected user
errors report `TableException` through Sublime's status bar and retain the
original selection and text. Legacy normalized-model mutation invalidates any
stored source or render override so later rendering cannot return stale grid
text.

Incomplete grids are not errors for legacy editing. They fail the complete-grid
predicate and use the previous table driver, allowing a table to be constructed
incrementally.

## Tests

Tests follow red-green-refactor cycles and cover:

- exact parse/render round trips for the supplied multi-rowspan table;
- exact parse/render round trips for Pandoc's canonical spanning-header table;
- a simple colspan and combined row/column span;
- inferred cell rectangles and edge matrices;
- manual removal and restoration of vertical edges to create/split colspans;
- manual removal and restoration of horizontal segments and `+` junctions to
  create/split rowspans;
- invalid L-shaped components, inconsistent vertical edges, missing outer
  borders, and inconsistent display coordinates;
- wide-character content and width expansion;
- raw and escaped Markdown pipes plus reStructuredText substitution
  references inside cells;
- `|---|` content, invalid junction anchors, and rejected shifted boundaries;
- literal `+---+` content that must not introduce a boundary;
- insertion, deletion, movement, indentation, and list renumbering inside
  ordinary, row-spanning, and column-spanning cells;
- movement across partial separators absent from the active rowspan;
- preservation of neighbouring cell content and internal separator geometry;
- navigation and cursor placement through spanned physical rows;
- logical-row insertion, deletion, movement, and header-boundary rejection;
- incomplete-grid fallback and Pandoc pipe compatibility;
- palette invocation outside a table;
- multi-caret rejection for all complete-grid structural commands;
- partial-rowspan grid detection and mixed-selection context semantics;
- separator-caret alignment, navigation, row commands, and error recovery;
- safe ordinary-grid column operations and refusal when affected by a span;
- selection-sensitive keymaps on grids and legacy tables;
- configured `keep_space_left=False` for pipe tables; and
- clean standard `python -m unittest discover` execution outside Sublime.

The Sublime-runtime integration module remains runnable inside Sublime but is
excluded or reported as skipped during standalone discovery. Syntax-warning
tests compile source in memory so they do not create `__pycache__` artifacts.

## Success Criteria

- The supplied rowspan table survives alignment and cell edits without span or
  content loss.
- Valid rectangular rowspans and colspans are inferred solely from visible
  boundaries.
- Adding or removing source edges changes inferred spans on the next command.
- All complete-grid mutations preserve valid geometry or fail without changes.
- Pipe tables and incomplete grids retain legacy behaviour.
- Reviewed palette, multi-caret, whitespace, keymap, and discovery defects have
  regression coverage and are fixed.
- The complete standalone suite passes with standard unittest discovery.
- The worktree contains no new commit.
