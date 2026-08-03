"""Does the text actually fit on the label?

The .scad lays text out from an anchor and never clips, so text wider than the label
simply continues past the edge — no error, nothing in the export to suggest a problem.
On a 1U (36mm) label, "M3 x 12 socket cap screws" produces geometry 83mm wide. You find
out after slicing, or after printing.

Measured from the render rather than from font metrics: the render is the ground truth,
it's already cached, and it accounts for the icons as well as the text.
"""
from __future__ import annotations

from pydantic import BaseModel

from .models import Label
from .scad import label_size_mm, mesh_bounds, render_label

# The body's own rounded corners contribute a hair of geometry; anything under this is
# noise rather than overflow.
TOLERANCE_MM = 0.5
MIN_READABLE_MM = 2.5      # below this a shrunk label stops being worth printing


class FitReport(BaseModel):
    fits: bool
    label_width_mm: float
    content_width_mm: float
    overflow_mm: float
    # What would fix it, so the UI can offer an action rather than just a complaint.
    suggested_width_u: float | None = None
    # EXPLICIT per-block sizes rather than one number plus a scaling rule. The single-number
    # form was ambiguous — apply it to the largest block, or to every block? — and the first
    # thing it did was trip up its own test. These are applied as-is.
    suggested_text1_size: float | None = None
    suggested_text2_size: float | None = None
    message: str = ""


def _content_width(label: Label) -> float:
    width, _ = label_size_mm(label)
    min_x, max_x, _, _ = mesh_bounds(render_label(label, "3mf"))
    return max(max_x, width) - min(min_x, 0.0)


def _sizes_that_fit(label: Label, width: float) -> tuple[float, float] | None:
    """Find a font size that actually fits, by rendering rather than by arithmetic.

    Scaling the size by width/content looks like it should work and doesn't: an icon takes
    a fixed amount of room regardless of the text, so the text's share doesn't scale
    linearly with the label. The first estimate therefore overshoots — verified by a test
    that caught exactly this. So the estimate is a starting point, then it is CHECKED, and
    reduced until it holds. Renders are cached, so a repeat check is free.
    """
    content = _content_width(label)
    factor = (width / content) if content else 1.0

    for _ in range(4):
        # Both blocks shrink together so their relative sizing is preserved.
        s1 = round(max(label.text1.size * factor, 0.1), 1)
        s2 = round(max(label.text2.size * factor, 0.1), 1)
        if max(s1, s2) < MIN_READABLE_MM:
            return None                     # shrinking further isn't worth printing
        candidate = label.model_copy(deep=True)
        candidate.text1 = candidate.text1.model_copy(update={"size": s1})
        candidate.text2 = candidate.text2.model_copy(update={"size": s2})
        if _content_width(candidate) - width <= TOLERANCE_MM:
            return s1, s2
        factor *= 0.88                      # overshot — step down and check again
    return None


def check(label: Label) -> FitReport:
    width, _ = label_size_mm(label)
    min_x, max_x, _, _ = mesh_bounds(render_label(label, "3mf"))
    content = max(max_x, width) - min(min_x, 0.0)
    overflow = content - width

    if overflow <= TOLERANCE_MM:
        return FitReport(fits=True, label_width_mm=width, content_width_mm=content,
                         overflow_mm=0.0)

    # Next whole Gridfinity unit that would hold it: width = 42u - 6.
    needed_u = (content + 6) / 42
    suggested_u = round(needed_u + 0.049, 1)

    sizes = _sizes_that_fit(label, width)

    fixes = []
    if sizes:
        fixes.append(f"shrink the text to {sizes[0]:g}mm")
    fixes.append(f"use a {suggested_u:g}U label ({suggested_u * 42 - 6:.0f}mm)")
    message = (f"The content is {content:.0f}mm wide but the label is {width:.0f}mm — "
               + " or ".join(fixes) + ".")

    return FitReport(
        fits=False, label_width_mm=width, content_width_mm=content,
        overflow_mm=round(overflow, 2),
        suggested_width_u=suggested_u,
        suggested_text1_size=sizes[0] if sizes else None,
        suggested_text2_size=sizes[1] if sizes else None,
        message=message,
    )
