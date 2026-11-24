"""Fit OpenSCAD's glyph bounds into the space left of the selected icons."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

from . import icons, scad
from .models import Label, TextBlock

EDGE_MM = 1.0
GAP_MM = 1.0


@lru_cache(maxsize=512)
def _glyph_bounds(text: str, font: str, size: float) -> tuple[float, float, float, float]:
    with tempfile.TemporaryDirectory(prefix="label-metrics-") as temp:
        source = Path(temp) / "metrics.scad"
        output = source.with_suffix(".echo")
        source.write_text(
            f"m = textmetrics({scad._scad_value(text)}, size={size}, "
            f'font={scad._scad_value(font)}, halign="left", valign="center");\n'
            "echo([m.position.x, m.position.y, m.size.x, m.size.y]);\n",
            encoding="utf-8",
        )
        try:
            subprocess.run(
                [scad.OPENSCAD, "--enable=textmetrics", "-o", str(output), str(source)],
                check=True, capture_output=True, timeout=scad.RENDER_TIMEOUT,
                env={**os.environ, "HOME": temp},
            )
            echo = next(line for line in output.read_text().splitlines() if line.startswith("ECHO: "))
            x, y, width, height = json.loads(echo.removeprefix("ECHO: "))
            return float(x), float(y), float(width), float(height)
        except (OSError, subprocess.SubprocessError, StopIteration, ValueError, TypeError) as exc:
            raise scad.RenderError("Auto-fit could not measure the text in OpenSCAD.") from exc


def _text_right_edge(label: Label, width: float, height: float) -> float:
    """Project the actual icon variants and use their conservative SVG viewBox bounds."""
    right = width - EDGE_MM
    f = label.fastener
    if f.show and (f.head != "none" or f.shaft != "none" or f.security):
        # Cullenect.scad anchors the fastener at labelX - driverX / 2 (driverX = 6).
        icon = icons.fastener_svg(f.head, f.driver, f.shaft, f.threads, f.flange, f.security)
        left = float(ET.parse(icon).getroot().attrib["viewBox"].split()[0])
        right = min(right, width - 3 + left - GAP_MM)
    if label.hardware != "none":
        # Cullenect.scad anchors hardware at labelX - labelY / 2.
        icon = icons.hardware_svg(label.hardware)
        left = float(ET.parse(icon).getroot().attrib["viewBox"].split()[0])
        right = min(right, width - height / 2 + left - GAP_MM)
    return right


def fitted_text(label: Label) -> dict[str, TextBlock]:
    width, height = scad.label_size_mm(label)
    blocks = {}
    for slot, block in (("Text1", label.text1), ("Text2", label.text2)):
        if block.text.strip():
            bounds = _glyph_bounds(block.text, f"{block.font}:{block.style}", block.size)
            if bounds[2] > 0 and bounds[3] > 0:
                blocks[slot] = (block, bounds)
    if not blocks:
        return {}

    right = _text_right_edge(label, width, height)
    available_width = right - EDGE_MM - (len(blocks) - 1) * GAP_MM
    if available_width <= 0:
        raise scad.RenderError("Auto-fit has no room for text. Use a wider label.")

    scale = min(
        1.0,
        available_width / sum(bounds[2] for _, bounds in blocks.values()),
        (height - 2 * EDGE_MM) / max(bounds[3] for _, bounds in blocks.values()),
    )
    return {
        slot: block.model_copy(update={
            "size": block.size * scale,
            "align": "left",
            "dx": EDGE_MM - x * scale if slot == "Text1" else right - (x + w) * scale,
            "dy": -(y + h / 2) * scale,
        })
        for slot, (block, (x, y, w, h)) in blocks.items()
    }
