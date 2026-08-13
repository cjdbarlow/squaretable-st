# SquareTable

SquareTable is a Sublime Text 4 plugin for editing plain-text tables. It is a fork of [SublimeTableEditor](https://github.com/vkocubinsky/SublimeTableEditor), extended for multiline Pandoc and reStructuredText grid tables.

## Installation

Open `Preferences → Browse Packages…`, then clone this repository into that directory:

```shell
git clone https://github.com/cjdbarlow/squaretable-st.git SquareTable
```

Alternatively, copy the repository contents into a folder named `SquareTable`. Restart Sublime Text after installation.

## Quick start

Open the command palette and select either:

* `SquareTable: Enable for current view`
* `SquareTable: Enable for current syntax`

Then type:

```text
|Name|Phone|
```

Press `Ctrl+K`, then `Enter`:

```text
| Name | Phone |
|------|-------|
|      |       |
```

Use `Tab` and `Shift+Tab` to move between cells. SquareTable aligns the table as you move.

If automatic syntax detection is wrong, select `SquareTable: Set table syntax '…' for current view`. This also enables SquareTable for that view.

## Commands

| Keys                     | Action                                                                          |                                 |
| ------------------------ | ------------------------------------------------------------------------------- | ------------------------------- |
| `Ctrl+Shift+A`           | Align the table.                                                                |                                 |
| `Tab` / `Shift+Tab`      | Move to the next or previous cell.                                              |                                 |
| `Enter`                  | Move down, creating a row when required. In a complete grid, insert a cell row. |                                 |
| `Alt+Left` / `Alt+Right` | Move the current column.                                                        |                                 |
| `Alt+Shift+Left`         | Delete the current column.                                                      |                                 |
| `Alt+Shift+Right`        | Insert a column to the left.                                                    |                                 |
| `Alt+Up` / `Alt+Down`    | Move the current row. In a complete grid, move the logical row.                 |                                 |
| `Alt+Shift+Up`           | Delete the current row.                                                         |                                 |
| `Alt+Shift+Down`         | Insert a row above the current row.                                             |                                 |
| `Ctrl+K`, then `-`       | Insert a single separator below.                                                |                                 |
| `Ctrl+K`, then `=`       | Insert a header separator below.                                                |                                 |
| `Ctrl+K`, then `Enter`   | Insert a separator below and move to the following row.                         |                                 |
| `Alt+Enter`              | Move the remainder of the current cell to the row below.                        |                                 |
| `Ctrl+J`                 | Join the current row with the next row.                                         |                                 |
| `Ctrl+K`, then `\        | `                                                                               | Convert the selection from CSV. |

At the beginning or end of a line, `Enter` retains its normal newline behaviour. Separator commands do not apply to Textile tables. Separator, split and join commands do not apply to complete bordered grids.

## Supported table syntaxes

| Mode               | Intended syntax                                                        |
| ------------------ | ---------------------------------------------------------------------- |
| `Simple`           | Pipe tables using `\                                                   |
| `EmacsOrgMode`     | Org tables using `\                                                    |
| `Pandoc`           | Bordered Pandoc grid tables.                                           |
| `MultiMarkdown`    | MultiMarkdown and Pandoc pipe tables; colspan support is experimental. |
| `reStructuredText` | reStructuredText simple and grid tables.                               |
| `Textile`          | Textile tables; rowspan and colspan support is experimental.           |

Automatic detection uses the view syntax:

| View syntax               | SquareTable mode   |
| ------------------------- | ------------------ |
| Markdown or MultiMarkdown | `MultiMarkdown`    |
| reStructuredText          | `reStructuredText` |
| Textile                   | `Textile`          |
| Anything else             | `Simple`           |

Pandoc mode is not selected automatically. Use `MultiMarkdown` for Pandoc pipe tables and `Pandoc` for bordered grid tables.


## Multiline grid tables

Multiline editing **applies only to complete bordered tables** in `Pandoc` or `reStructuredText` mode.

### Logical rows and cell rows

A **logical row** is all content between two complete horizontal borders. A **cell row** is one physical line within a cell:

```text
| ------- | ----------- |
| Name    | Tasks       |
| ======= | =========== |
| Alice   | - One       |
|         | - Two       |
|         | - Three     |
|         | - Four      |
| ------- | ----------- |
| Bob     | - One       |
|         | - Two       |
```

Short cells are padded with blank cell rows. A trailing physical row is removed only when it is blank across every cell in the logical row.

### Rowspans and colspans

Grid junctions form a coordinate system. Each cell is a rectangle bounded by those coordinates; spans are inferred from the visible borders rather than stored as metadata.

* Remove an internal `|` throughout a content band to join adjacent cells into a colspan.
* Remove a horizontal segment and its anchoring `+` to continue a cell as a rowspan.
* Restore the `|`, separator segment or `+` to split the cell again.

This table contains both forms:

```text
+---+---+
| Title |
+===+===+
| A | B |
|   +---+
| C | D |
+---+---+

+---+-----+
| Title   |
+===+=====+
| A | B   |
|   +-----+
| C | D   |
|   | sdf |
+--------+
|        |
+--------+
```

`Title` spans both columns. The left body cell contains `A` and `C` across both bands; `B` and `D` remain separate.

A `|` is structural only at a column coordinate declared by the grid. Literal pipes, Markdown escapes such as `\|`, and reStructuredText substitutions such as `|name|` remain content. Later separators may declare columns hidden beneath an earlier colspan. Text such as `+---+` in a content row also remains content.

A partial separator may carry content in the cell that crosses it. Alignment and cell-row commands preserve rectangular rowspans, colspans and combined spans. Non-rectangular geometry is rejected without changing the table.

### Cell-row commands

| Keys                                    | Action                                                        |
+-----------------------------------------+---------------------------------------------------------------+
| `Enter`                                 | Insert a cell row below the caret without splitting its text. |
| `Ctrl+Alt+Shift+Down`                   | Insert a cell row below the caret.                            |
| `Ctrl+Alt+Shift+Up`                     | Delete the current cell row.                                  |
| `Ctrl+Alt+Up` / `Ctrl+Alt+Down`         | Move the current row within its cell.                         |
| `Tab` / `Shift+Tab` with a selection    | Indent or outdent selected list rows.                         |
| `Tab` / `Shift+Tab` without a selection | Move to the next or previous cell.                            |

Cell-row operations change only the active cell and cannot cross a horizontal border. Deleting the only cell row leaves an empty cell. The six explicit cell-row operations also appear in the command palette under `SquareTable:`.

### List editing

Inserting after a recognised list item continues its indentation and marker. Supported markers are:

* `-`, `*` and `+`
* Decimal numbers followed by `.` or `)`
* Task items, which continue as unchecked `- [ ]` items

Ordered lists are renumbered after insertion, deletion, movement, indentation or outdenting. Each indentation level is independent; the starting number and delimiter are preserved. Renumbering stops at a blank or non-list row.

Alphabetic and Roman numeral markers are not supported. An indentation selection must stay within one cell and one logical row. Indentation follows `tab_size` and `translate_tabs_to_spaces`.

### Safety limits

Complete-grid structural editing requires one caret and no selection. Pipe tables retain their existing multi-caret and selected-region behaviour.

Logical-row commands carry every cell row and the bottom separator. A logical row cannot move across an `=` header border.

Column move, insert and delete commands are available only when the affected atomic columns contain unspanned cells. SquareTable refuses an operation before mutation if it would touch a rowspan or colspan. Horizontal separator, split-down and join-lines commands are also refused because they cannot yet preserve complete-grid geometry safely.

## Settings

SquareTable is disabled unless `enable_table_editor` is true. Settings may be applied globally, per syntax or to the current view.

| Setting                                | Default        | Effect                                                           |
+----------------------------------------+----------------+------------------------------------------------------------------+
| `enable_table_editor`                  | `false`        | Enable SquareTable key bindings.                                 |
| `table_editor_syntax`                  | automatic      | Force one of the six modes listed above.                         |
| `table_editor_border_style`            | syntax default | Use `simple`, `emacs` or `grid` borders in `Simple` mode.        |
| `table_editor_custom_column_alignment` | `true`         | Recognise `<`, `>` and `#` alignment rows in `Simple` mode.      |
| `table_editor_align_number_right`      | `true`         | Right-align numeric columns.                                     |
| `table_editor_detect_header`           | `true`         | Centre detected headers.                                         |
| `table_editor_keep_space_left`         | `false`        | Preserve leading spaces in cell content.                         |
| `table_editor_intelligent_formatting`  | `true`         | Remove redundant trailing cells when packing legacy span syntax. |

For example:

```json
{
    "enable_table_editor": true,
    "table_editor_syntax": "Pandoc",
    "table_editor_align_number_right": true,
    "table_editor_detect_header": true
}
```

The command palette can enable or disable SquareTable, leading-space preservation, numeric alignment and header detection for the current view.

## CSV, CJK and demo

### CSV conversion

Select delimited text, then press `Ctrl+K`, followed by `|`. SquareTable detects the CSV dialect and renders the selection using the active table syntax. If detection fails, each input line becomes a single cell.

### CJK support

SquareTable accounts for double-width CJK characters when aligning columns. Use a monospaced font with suitable CJK glyphs.

## Credits and licence

SquareTable is derived from [SublimeTableEditor](https://github.com/vkocubinsky/SublimeTableEditor) by Valery Kocubinsky and keeps the original [Apache License 2.0](COPYING).
