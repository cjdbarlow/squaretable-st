import re


LIST_ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?:(?P<number>\d+)(?P<delimiter>[.)])|(?P<bullet>[-+*]))"
    r"(?P<space>[ \t]*)"
    r"(?:(?P<task>\[[ xX]\])(?P<task_space>[ \t]*))?"
    r"(?P<body>.*)$")


class ListItem(object):

    def __init__(self, match):
        groups = match.groupdict()
        self.indent = groups['indent']
        self.number = (int(groups['number'])
                       if groups['number'] is not None else None)
        self.delimiter = groups['delimiter']
        self.bullet = groups['bullet']
        self.space = groups['space']
        self.task = groups['task']
        self.task_space = groups['task_space']
        self.body = groups['body']


def parse_list_item(text):
    match = LIST_ITEM_RE.match(text)
    if (match and not match.group('space') and
            (match.group('task') is not None or match.group('body'))):
        match = None
    return ListItem(match) if match else None


def continuation_for(text):
    item = parse_list_item(text)
    if item is None:
        return None

    if item.number is None:
        marker = item.bullet
    else:
        marker = str(item.number + 1) + item.delimiter

    task = ''
    if item.task is not None:
        task = '[ ]' + (item.task_space or ' ')
    return item.indent + marker + (item.space or ' ') + task


def _list_block(rows, anchor):
    if not 0 <= anchor < len(rows) or parse_list_item(rows[anchor]) is None:
        return None

    start = anchor
    while start > 0 and parse_list_item(rows[start - 1]) is not None:
        start -= 1

    end = anchor + 1
    while end < len(rows) and parse_list_item(rows[end]) is not None:
        end += 1
    return start, end


def _replace_number(text, number):
    match = LIST_ITEM_RE.match(text)
    start, end = match.span('number')
    return text[:start] + str(number) + text[end:]


def _ordered_sequence_start(rows, anchor, target):
    block = _list_block(rows, anchor)
    if block is None:
        return None

    start = anchor
    for index in range(anchor - 1, block[0] - 1, -1):
        item = parse_list_item(rows[index])
        if len(item.indent) < len(target.indent):
            break
        if len(item.indent) == len(target.indent):
            if (item.indent != target.indent or item.number is None or
                    item.delimiter != target.delimiter):
                break
            start = index
    return start


def ordered_list_start(rows, anchor):
    if not 0 <= anchor < len(rows):
        return None
    target = parse_list_item(rows[anchor])
    if target is None or target.number is None:
        return None
    start = _ordered_sequence_start(rows, anchor, target)
    first = parse_list_item(rows[start])
    return first.indent, first.delimiter, first.number


def renumber_ordered_list(rows, anchor, preserved_start=None):
    result = list(rows)
    block = _list_block(result, anchor)
    if block is None:
        return result

    override_index = None
    target = parse_list_item(result[anchor])
    if (preserved_start is not None and target is not None and
            target.number is not None and
            target.indent == preserved_start[0] and
            target.delimiter == preserved_start[1]):
        override_index = _ordered_sequence_start(result, anchor, target)

    counters = {}
    for index in range(block[0], block[1]):
        item = parse_list_item(result[index])
        indent_len = len(item.indent)
        for indent in list(counters):
            if (len(indent) > indent_len or
                    (len(indent) == indent_len and indent != item.indent)):
                del counters[indent]

        state = counters.get(item.indent)
        if item.number is None:
            counters.pop(item.indent, None)
        elif state is None or state[0] != item.delimiter:
            number = preserved_start[2] if index == override_index else item.number
            if number != item.number:
                result[index] = _replace_number(result[index], number)
            counters[item.indent] = (item.delimiter, number + 1)
        else:
            result[index] = _replace_number(result[index], state[1])
            counters[item.indent] = (item.delimiter, state[1] + 1)
    return result


def _selected_items(rows, indexes):
    selected = []
    for index in sorted(set(indexes)):
        if not 0 <= index < len(rows):
            raise ValueError("List row index is out of range")
        item = parse_list_item(rows[index])
        if item is None:
            raise ValueError("Selected row is not a list item")
        selected.append((index, item))
    return selected


def indent_list_items(rows, indexes, indent):
    if not indent:
        raise ValueError("Indent must not be empty")
    result = list(rows)
    for index, unused_item in _selected_items(result, indexes):
        result[index] = indent + result[index]
    return result


def outdent_list_items(rows, indexes, tab_size):
    if tab_size < 1:
        raise ValueError("Tab size must be positive")
    result = list(rows)
    for index, item in _selected_items(result, indexes):
        indent = item.indent
        if indent.endswith('\t'):
            indent = indent[:-1]
        else:
            indent = indent[:-min(tab_size, len(indent))]
        result[index] = indent + result[index][len(item.indent):]
    return result
