"""Turn a pasted list into labels.

The common way a label library actually starts is a list you already have somewhere — a
drawer inventory, a BOM, a column from a spreadsheet. Retyping it one dialog at a time is
the real cost, so one paste becomes the whole batch, with the shared settings (width,
surface, colour, icon) chosen once for all of them.
"""
from __future__ import annotations

from .models import Label

SEPARATORS = ("|", "\t")     # 'text | second text', or a spreadsheet column paste
COMMENT = "#"


def parse_lines(text: str) -> list[tuple[str, str]]:
    """One line -> (text1, text2). Blank lines and #comments are skipped.

    A tab is treated like the explicit '|' separator so pasting two columns straight out of
    a spreadsheet does the obvious thing.
    """
    out: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(COMMENT):
            continue
        first, second = line, ""
        for sep in SEPARATORS:
            if sep in line:
                left, _, right = line.partition(sep)
                first, second = left.strip(), right.strip()
                break
        if first or second:
            out.append((first, second))
    return out


def build_labels(text: str, template: Label) -> list[Label]:
    """Apply the shared template to every parsed line.

    The template carries everything except the words: width, surface, colour, fastener and
    hardware icon, quantity. Each label's library name defaults to its own text, so the
    list stays readable without a second pass of typing.
    """
    labels: list[Label] = []
    for first, second in parse_lines(text):
        label = template.model_copy(deep=True)
        label.id = ""
        label.created_at = None
        label.updated_at = None
        label.text1 = template.text1.model_copy(update={"text": first})
        label.text2 = template.text2.model_copy(update={"text": second})
        label.name = (first or second)[:200]
        labels.append(label)
    return labels
