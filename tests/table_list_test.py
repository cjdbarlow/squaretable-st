import unittest

try:
    from .. import table_list
except (ImportError, ValueError):
    import table_list


class ListContinuationTest(unittest.TestCase):

    def test_plain_text_has_no_continuation(self):
        self.assertIsNone(table_list.continuation_for("plain text"))

    def test_unordered_item_preserves_indent_and_marker(self):
        self.assertEqual("    * ",
                         table_list.continuation_for("    * nested"))

    def test_ordered_item_increments_and_preserves_delimiter(self):
        self.assertEqual("10) ",
                         table_list.continuation_for("9) item"))

    def test_task_item_becomes_unchecked(self):
        self.assertEqual("- [ ] ",
                         table_list.continuation_for("- [x] done"))

    def test_empty_item_still_continues(self):
        self.assertEqual("- ", table_list.continuation_for("- "))

    def test_rendered_empty_marker_still_continues(self):
        self.assertEqual("- ", table_list.continuation_for("-"))
        self.assertEqual("6. ", table_list.continuation_for("5."))


class OrderedListTest(unittest.TestCase):

    def test_renumbers_each_indent_level_from_its_first_number(self):
        rows = ["4. four", "    8) nested", "    3) nested", "9. five"]
        self.assertEqual(
            ["4. four", "    8) nested", "    9) nested", "5. five"],
            table_list.renumber_ordered_list(rows, 1))

    def test_blank_row_stops_the_affected_block(self):
        rows = ["1. one", "7. two", "", "5. separate", "8. list"]
        self.assertEqual(
            ["1. one", "2. two", "", "5. separate", "8. list"],
            table_list.renumber_ordered_list(rows, 1))

    def test_same_level_unordered_item_starts_a_new_sequence(self):
        rows = ["3. one", "- other", "9. separate"]
        self.assertEqual(rows,
                         table_list.renumber_ordered_list(rows, 0))

    def test_preserves_start_captured_before_structural_edit(self):
        before = ["4. four", "5. five", "6. six"]
        preserved = table_list.ordered_list_start(before, 0)

        self.assertEqual(
            ["4. five", "5. six"],
            table_list.renumber_ordered_list(
                ["5. five", "6. six"], 0, preserved))


class ListIndentTest(unittest.TestCase):

    def test_indents_only_selected_items(self):
        rows = ["- one", "- two", "- three"]
        self.assertEqual(
            ["- one", "    - two", "    - three"],
            table_list.indent_list_items(rows, [1, 2], "    "))

    def test_outdent_removes_at_most_one_level(self):
        rows = ["        - deep", "- root"]
        self.assertEqual(
            ["    - deep", "- root"],
            table_list.outdent_list_items(rows, [0, 1], 4))

    def test_non_list_selection_is_rejected(self):
        with self.assertRaises(ValueError):
            table_list.indent_list_items(["plain"], [0], "    ")
