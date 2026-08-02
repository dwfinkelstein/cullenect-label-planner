"""Label model — a 1:1 typed mirror of the Cullenect.scad customizer parameters.

Every field maps onto one OpenSCAD variable (see scad.py for the mapping). Keeping
the names close to the upstream .scad makes it obvious what a change does to the
geometry, and makes a future upstream bump easy to diff.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Align = Literal["left", "center", "right"]
Surface = Literal["emboss", "deboss", "flush"]

# Fonts bundled in the image (Dockerfile installs these families).
FONTS = ["Open Sans", "Open Sans Condensed", "Ubuntu", "Montserrat"]
FONT_STYLES = [
    "Regular", "Black", "Bold", "ExtraBold", "ExtraLight", "Light", "Medium",
    "SemiBold", "Thin", "Italic", "Black Italic", "Bold Italic",
    "ExtraBold Italic", "ExtraLight Italic", "Light Italic", "Medium Italic",
    "SemiBold Italic", "Thin Italic",
]

FASTENER_HEADS = ["none", "socket", "countersunk", "roundh", "pan"]
FASTENER_SHAFTS = ["none", "machine", "tapping"]
FASTENER_THREADS = ["none", "full", "partial"]
FASTENER_DRIVERS = [
    "none", "slot", "phillips", "phillips_slot", "phillips_square", "torx",
    "hex", "square", "triangle",
]
HARDWARE = [
    "none", "washer", "washer_locking", "threaded_insert", "nut", "nut_square",
    "nut_nylon", "tnut_1", "tnut_2", "magnet", "crimp_ring_open",
    "crimp_ring_closed", "crimp_fork_open", "crimp_fork_closed",
    "crimp_spade_open", "crimp_spade_closed", "crimp_receptacle_open",
    "crimp_receptacle_closed", "crimp_butt_splice",
]


def one_of(allowed: list[str], field_name: str):
    """Reject a value the vendored .scad has no branch for.

    These fields are passed to OpenSCAD as -D overrides. An unknown value doesn't error
    there — the .scad's if-chain simply matches nothing and silently renders a label with
    the icon missing, which is only discovered after a print. Rejecting at the edge turns
    a silent wrong result into a 422.
    """
    def _check(v: str) -> str:
        if v not in allowed:
            raise ValueError(f"{field_name} must be one of: {', '.join(allowed)}")
        return v
    return _check


class TextBlock(BaseModel):
    text: str = Field("", max_length=200)
    align: Align = "left"
    font: str = "Open Sans"
    style: str = "Regular"
    size: float = Field(5, ge=1, le=11)
    dx: float = Field(0, ge=-50, le=50)
    dy: float = Field(0, ge=-50, le=50)

    _v_font = field_validator("font")(one_of(FONTS, "font"))
    _v_style = field_validator("style")(one_of(FONT_STYLES, "style"))


class Fastener(BaseModel):
    show: bool = False
    head: str = "socket"
    shaft: str = "machine"
    threads: str = "full"
    driver: str = "phillips"
    flange: bool = False
    security: bool = False

    _v_head = field_validator("head")(one_of(FASTENER_HEADS, "head"))
    _v_shaft = field_validator("shaft")(one_of(FASTENER_SHAFTS, "shaft"))
    _v_threads = field_validator("threads")(one_of(FASTENER_THREADS, "threads"))
    _v_driver = field_validator("driver")(one_of(FASTENER_DRIVERS, "driver"))


class Label(BaseModel):
    """One row of the tracked label library."""

    id: str = ""
    name: str = Field("", max_length=200)   # library-only display name; never printed
    qty: int = Field(1, ge=1, le=50)        # how many copies to put on a plate
    tags: list[str] = []

    width_u: float = Field(1, gt=0, le=8)     # Gridfinity units
    surface: Surface = "emboss"
    text_color: str = "#333333"
    backward_compatible: bool = True

    text1: TextBlock = TextBlock()
    text2: TextBlock = TextBlock(text="", align="right", size=6)
    fastener: Fastener = Fastener()
    hardware: str = "none"

    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    _v_hardware = field_validator("hardware")(one_of(HARDWARE, "hardware"))

    @field_validator("text_color")
    @classmethod
    def _v_color(cls, v: str) -> str:
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            raise ValueError("text_color must be a #RRGGBB hex colour")
        return v

    def summary(self) -> str:
        return self.name or self.text1.text or self.text2.text or "(untitled)"


class Library(BaseModel):
    version: int = 1
    labels: list[Label] = []
