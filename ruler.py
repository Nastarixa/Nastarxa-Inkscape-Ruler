#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nastarxa Inkscape Ruler Extension - Inkscape 1.x extension.

Draws horizontal (top/bottom) and vertical (left/right) measuring rulers
around the bounding box of the selected object(s). Units can be mm, cm,
pt, pc, in, or px. Horizontal and vertical rulers are emitted as separate
groups. Pure stdlib fallback is included so the script also runs outside
Inkscape (e.g. from a terminal) for testing.

Inkscape 1.x passes the input SVG as the last command-line argument (with
options such as --id and --unit before it) and reads the result from stdout.
Stdin is supported as a fallback for standalone/terminal use.
"""

import math
import os
import re
import statistics
import sys
from urllib.parse import unquote
from xml.etree import ElementTree as ET

EXTENSION_NAME = "Nastarxa Inkscape Ruler Extension"
SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", INKSCAPE_NS)


def q(tag):
    return "{%s}%s" % (SVG_NS, tag)


# ---------------------------------------------------------------------------
# Units: CSS px to physical measurement systems. A document viewBox can make
# one SVG user unit larger or smaller than one CSS px, so the root scale is
# applied before measurements are displayed.
# ---------------------------------------------------------------------------
UNIT_TO_PX = {
    "px": 1.0,
    "mm": 96.0 / 25.4,
    "cm": 96.0 / 2.54,
    "in": 96.0,
    "pt": 96.0 / 72.0,
    "pc": 16.0,
}

UNIT_LABEL = {
    "px": "px",
    "mm": "mm",
    "cm": "cm",
    "in": "in",
    "pt": "pt",
    "pc": "pc",
}

_LENGTH_RE = re.compile(
    r"^\s*([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)\s*([a-zA-Z%]*)\s*$")


def length_in_px(value):
    """Parse an SVG length such as ``210mm`` or ``96`` into CSS pixels."""
    if value is None:
        return None
    match = _LENGTH_RE.match(str(value))
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "px").lower()
    if unit not in UNIT_TO_PX:
        return None
    return number * UNIT_TO_PX[unit]


def svg_user_unit_scale(root):
    """Return CSS px per document user unit from width/height and viewBox."""
    if root is None:
        return 1.0
    width = length_in_px(root.get("width"))
    height = length_in_px(root.get("height"))
    view_box = root.get("viewBox")
    if width is None or height is None or not view_box:
        return 1.0
    nums = [v for v in view_box.replace(",", " ").split() if v]
    if len(nums) < 4:
        return 1.0
    try:
        vb_w, vb_h = float(nums[2]), float(nums[3])
    except ValueError:
        return 1.0
    if vb_w <= 0 or vb_h <= 0:
        return 1.0
    sx, sy = width / vb_w, height / vb_h
    if sx <= 0 or sy <= 0:
        return 1.0
    if abs(sx - sy) <= 1e-6 * max(abs(sx), abs(sy)):
        return (sx + sy) / 2.0
    # Non-uniform viewBox scaling has no single correct answer; the geometric
    # mean keeps horizontal and vertical totals consistent.
    return math.sqrt(sx * sy)


def css_color(value, default):
    """Convert Inkscape's RGBA color string to a CSS color value."""
    if not value:
        return default
    value = str(value).strip()
    if value.startswith("0x") or value.startswith("0X"):
        digits = value[2:]
        if len(digits) == 6:
            digits += "ff"
        if len(digits) == 8:
            try:
                r, g, b, a = (int(digits[i:i + 2], 16) for i in (0, 2, 4, 6))
            except ValueError:
                return default
            if a == 255:
                return "#%02x%02x%02x" % (r, g, b)
            return "rgba(%d,%d,%d,%.3f)" % (r, g, b, a / 255.0)
        return default
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        if len(digits) == 6:
            return "#" + digits.lower()
        if len(digits) == 8:
            try:
                r, g, b, a = (int(digits[i:i + 2], 16) for i in (0, 2, 4, 6))
            except ValueError:
                return default
            if a == 255:
                return "#%02x%02x%02x" % (r, g, b)
            return "rgba(%d,%d,%d,%.3f)" % (r, g, b, a / 255.0)
        return default
    # Named colors or already-valid CSS values pass through.
    return value


def is_multiple(value, multiple, tolerance=1e-7):
    """True when value is an integer multiple of multiple."""
    if not multiple:
        return False
    return abs(value / multiple - round(value / multiple)) < tolerance


# INX defaults. Presets are complete style definitions: selecting one replaces
# these values deterministically. "Custom" leaves the current controls unchanged.
DEFAULTS = {
    "unit": "mm",
    "minor_divisions": 10,
    "offset": 6.0,
    "major_length": 14.0,
    "minor_length": 7.0,
    "font_size": 12.0,  # legacy fallback for old command lines
    "label_font_size": 12.0,
    "total_font_size": 12.0,
    "show_labels": True,
    "show_top": True,
    "show_bottom": False,
    "show_left": True,
    "show_right": False,
    "origin": "start",
    "tick_direction": "out",
    "label_mode": "all",
    "label_decimals": -1,
    "show_zero": True,
    "preset": "custom",
    "auto_fit": True,
    "line_width": 1.0,
    "text_gap": 3.0,
    "text_color": "0x222222ff",
    "text_border_color": "0xffffffff",
    "line_color": "0x333333ff",
    "group_with_object": True,
    "replace_selection": True,
}

PRESETS = {
    # Every preset is complete: selecting it replaces all style controls,
    # including the three color choosers. This makes the change visible.
    "minimal": {
        "offset": 4.0, "major_length": 10.0, "minor_length": 5.0,
        "label_font_size": 9.0, "total_font_size": 11.0,
        "line_width": 0.6, "text_gap": 2.0,
        "label_mode": "origin-total", "label_decimals": -1,
        "line_color": "0x888888ff",
        "text_color": "0x666666ff", "text_border_color": "0xf3f4f6ff",
    },
    "compact": {
        "offset": 3.0, "major_length": 8.0, "minor_length": 4.0,
        "label_font_size": 8.0, "total_font_size": 10.0,
        "line_width": 0.6, "text_gap": 1.0,
        "label_mode": "origin-total", "label_decimals": -1,
        "line_color": "0x4b5563ff",
        "text_color": "0x374151ff", "text_border_color": "0xf9fafbff",
    },
    "technical": {
        "offset": 8.0, "major_length": 18.0, "minor_length": 9.0,
        "label_font_size": 11.0, "total_font_size": 14.0,
        "line_width": 1.2, "text_gap": 4.0,
        "label_mode": "all", "label_decimals": 1,
        "line_color": "0x111827ff",
        "text_color": "0x374151ff", "text_border_color": "0xffffffff",
    },
    "blueprint": {
        "offset": 8.0, "major_length": 16.0, "minor_length": 8.0,
        "label_font_size": 11.0, "total_font_size": 14.0,
        "line_width": 1.0, "text_gap": 3.0,
        "label_mode": "all", "label_decimals": -1,
        "line_color": "0xffffffff",
        "text_color": "0xdbeafeff", "text_border_color": "0x003366ff",
    },
    "high-contrast": {
        "offset": 8.0, "major_length": 18.0, "minor_length": 9.0,
        "label_font_size": 12.0, "total_font_size": 16.0,
        "line_width": 1.4, "text_gap": 4.0,
        "label_mode": "all", "label_decimals": -1,
        "line_color": "0x000000ff",
        "text_color": "0xffffffff", "text_border_color": "0x000000ff",
    },
    "export": {
        "offset": 10.0, "major_length": 20.0, "minor_length": 10.0,
        "label_font_size": 14.0, "total_font_size": 18.0,
        "line_width": 2.0, "text_gap": 5.0,
        "label_mode": "all", "label_decimals": -1,
        "line_color": "0xffffffff",
        "text_color": "0xfef3c7ff", "text_border_color": "0x000000ff",
    },
    "warm": {
        "offset": 7.0, "major_length": 15.0, "minor_length": 7.0,
        "label_font_size": 11.0, "total_font_size": 15.0,
        "line_width": 1.2, "text_gap": 3.0,
        "label_mode": "all", "label_decimals": -1,
        "line_color": "0xb45309ff",
        "text_color": "0x7c2d12ff", "text_border_color": "0xfff7edff",
    },
}


# Inkscape optiongroups return the selected option's value attribute, but
# accept the displayed label too so older/custom builds behave consistently.
PRESET_ALIASES = {
    "custom": "custom",
    "minimal": "minimal",
    "compact": "compact",
    "technical": "technical",
    "blueprint": "blueprint",
    "high-contrast": "high-contrast",
    "high contrast": "high-contrast",
    "export": "export",
    "dark export": "export",
    "dark-export": "export",
    "warm": "warm",
}


def apply_preset(opts, raw_values):
    """Apply a complete style preset so the GUI always shows a real change.

    Inkscape passes every control on each run. The previous "only defaults"
    heuristic meant a preset could appear to do nothing once any control had
    been edited. A selected preset now wins over the dialog values; "Custom"
    keeps whatever the user entered.
    """
    preset = str(opts.get("preset", "custom")).strip().lower()
    preset = PRESET_ALIASES.get(preset, preset)
    if preset == "custom" or preset not in PRESETS:
        return opts
    opts.update(PRESETS[preset])
    return opts


# ---------------------------------------------------------------------------
# Minimal SVG path / transform handling (stdlib fallback only)
# ---------------------------------------------------------------------------
class Transform:
    """Affine transform a, b, c, d, e, f."""

    def __init__(self, a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0):
        self.m = (a, b, c, d, e, f)

    def __mul__(self, other):
        a, b, c, d, e, f = self.m
        A, B, C, D, E, F = other.m
        return Transform(
            a * A + c * B,
            b * A + d * B,
            a * C + c * D,
            b * C + d * D,
            a * E + c * F + e,
            b * E + d * F + f,
        )

    def inverse(self):
        """Return the inverse transform, or identity for a singular matrix."""
        a, b, c, d, e, f = self.m
        det = a * d - b * c
        if abs(det) < 1e-12:
            return Transform()
        ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
        ie = -(ia * e + ic * f)
        if_ = -(ib * e + id_ * f)
        return Transform(ia, ib, ic, id_, ie, if_)

    def apply(self, x, y):
        a, b, c, d, e, f = self.m
        return (a * x + c * y + e, b * x + d * y + f)

    @classmethod
    def parse(cls, text):
        if not text:
            return cls()
        tokens = [t for t in text.replace(",", " ").replace("(", " ").replace(")", " ").split() if t]
        m = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        i = 0
        while i < len(tokens):
            op = tokens[i]
            i += 1
            try:
                if op == "matrix" and i + 5 < len(tokens):
                    vals = [float(v) for v in tokens[i:i + 6]]
                    i += 6
                elif op == "translate" and i < len(tokens):
                    tx = float(tokens[i]); i += 1
                    ty = 0.0
                    if i < len(tokens) and _is_number(tokens[i]):
                        ty = float(tokens[i]); i += 1
                    vals = [1, 0, 0, 1, tx, ty]
                elif op == "scale" and i < len(tokens):
                    sx = float(tokens[i]); i += 1
                    sy = sx
                    if i < len(tokens) and _is_number(tokens[i]):
                        sy = float(tokens[i]); i += 1
                    vals = [sx, 0, 0, sy, 0, 0]
                elif op == "rotate" and i < len(tokens):
                    ang = math.radians(float(tokens[i])); i += 1
                    co, si = math.cos(ang), math.sin(ang)
                    vals = [co, si, -si, co, 0, 0]
                elif op == "skewX" and i < len(tokens):
                    vals = [1, 0, math.tan(math.radians(float(tokens[i]))), 1, 0, 0]
                    i += 1
                elif op == "skewY" and i < len(tokens):
                    vals = [1, math.tan(math.radians(float(tokens[i]))), 0, 1, 0, 0]
                    i += 1
                else:
                    continue
                m = (Transform(m[0], m[1], m[2], m[3], m[4], m[5]) * Transform(*vals)).m
            except (ValueError, IndexError):
                break
        return Transform(*m)


def _is_number(token):
    try:
        float(token)
        return True
    except ValueError:
        return False


def _cubic_extrema(p0, p1, p2, p3):
    """Points where a cubic Bezier touches horizontal/vertical extremes."""
    out = []
    for axis in (0, 1):
        a = -p0[axis] + 3 * p1[axis] - 3 * p2[axis] + p3[axis]
        b = 2 * (p0[axis] - 2 * p1[axis] + p2[axis])
        c = p1[axis] - p0[axis]
        roots = []
        if abs(a) < 1e-12:
            if abs(b) > 1e-12:
                roots.append(-c / b)
        else:
            disc = b * b - 4 * a * c
            if disc >= 0:
                sq = math.sqrt(disc)
                roots.extend(((-b + sq) / (2 * a), (-b - sq) / (2 * a)))
        for t in roots:
            if 0 < t < 1:
                mt = 1 - t
                out.append((
                    mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] +
                    3 * mt * t * t * p2[0] + t ** 3 * p3[0],
                    mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] +
                    3 * mt * t * t * p2[1] + t ** 3 * p3[1],
                ))
    return out


def _quad_extrema(p0, p1, p2):
    """Points where a quadratic Bezier touches horizontal/vertical extremes."""
    out = []
    for axis in (0, 1):
        den = p0[axis] - 2 * p1[axis] + p2[axis]
        if abs(den) < 1e-12:
            continue
        t = (p0[axis] - p1[axis]) / den
        if 0 < t < 1:
            mt = 1 - t
            out.append((mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
                        mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]))
    return out


def _arc_points(p0, rx, ry, phi, large, sweep, p1):
    """Endpoint plus true axis-aligned extrema of an SVG elliptical arc."""
    rx, ry = abs(rx), abs(ry)
    if (rx < 1e-12 or ry < 1e-12 or
            (abs(p0[0] - p1[0]) < 1e-12 and abs(p0[1] - p1[1]) < 1e-12)):
        return [p1]

    ph = math.radians(phi)
    cos_p, sin_p = math.cos(ph), math.sin(ph)
    dx2, dy2 = (p0[0] - p1[0]) / 2.0, (p0[1] - p1[1]) / 2.0
    x1p = cos_p * dx2 + sin_p * dy2
    y1p = -sin_p * dx2 + cos_p * dy2

    lam = x1p * x1p / (rx * rx) + y1p * y1p / (ry * ry)
    if lam > 1:
        scale = math.sqrt(lam)
        rx *= scale
        ry *= scale

    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp = coef * rx * y1p / ry
    cyp = -coef * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (p0[0] + p1[0]) / 2.0
    cy = sin_p * cxp + cos_p * cyp + (p0[1] + p1[1]) / 2.0

    theta1 = math.atan2((y1p - cyp) / ry, (x1p - cxp) / rx)
    theta2 = math.atan2((-y1p - cyp) / ry, (-x1p - cxp) / rx)
    delta = theta2 - theta1
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    angles = [theta1, theta2]
    if abs(cos_p * rx) > 1e-12:
        base_x = math.atan(-(sin_p * ry) / (cos_p * rx))
    else:
        base_x = math.pi / 2.0
    if abs(sin_p * rx) > 1e-12:
        base_y = math.atan((cos_p * ry) / (sin_p * rx))
    else:
        base_y = 0.0
    candidates = []
    for base in (base_x, base_y):
        candidates.extend(base + k * math.pi for k in (-1, 0, 1, 2))
    lo, hi = min(theta1, theta1 + delta), max(theta1, theta1 + delta)
    angles.extend(t for t in candidates if lo < t < hi)

    return [(
        cx + cos_p * rx * math.cos(t) - sin_p * ry * math.sin(t),
        cy + sin_p * rx * math.cos(t) + cos_p * ry * math.sin(t),
    ) for t in angles]


def parse_path_points(d):
    """Sample a path at endpoints and curve extrema for an accurate bbox.

    Bezier control handles are deliberately excluded: they are not on the
    curve and would inflate the measured object.
    """
    tokens = re.findall(
        r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?|[MmZzLlHhVvCcSsQqTtAa]",
        d)
    points = []
    i = 0
    cx = cy = sx = sy = 0.0
    px = py = None
    cmd = None
    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                cx, cy = sx, sy
                points.append((cx, cy))
                px = py = None
                cmd = None
                continue
        if cmd is None:
            i += 1
            continue
        upper = cmd.upper()
        relative = cmd.islower()
        try:
            if upper == "M":
                x, y = float(tokens[i]), float(tokens[i + 1]); i += 2
                if relative:
                    x += cx; y += cy
                cx, cy = x, y
                sx, sy = x, y
                points.append((cx, cy))
                px = py = None
                cmd = "l" if relative else "L"
            elif upper == "L":
                x, y = float(tokens[i]), float(tokens[i + 1]); i += 2
                if relative:
                    x += cx; y += cy
                cx, cy = x, y
                points.append((cx, cy))
                px = py = None
            elif upper == "H":
                x = float(tokens[i]); i += 1
                cx = cx + x if relative else x
                points.append((cx, cy))
                px = py = None
            elif upper == "V":
                y = float(tokens[i]); i += 1
                cy = cy + y if relative else y
                points.append((cx, cy))
                px = py = None
            elif upper in ("C", "S"):
                count = 6 if upper == "C" else 4
                vals = [float(v) for v in tokens[i:i + count]]; i += count
                if relative:
                    vals = [vals[j] + (cx if j % 2 == 0 else cy) for j in range(count)]
                p0 = (cx, cy)
                if upper == "C":
                    p1, p2, p3 = (vals[0], vals[1]), (vals[2], vals[3]), (vals[4], vals[5])
                else:
                    p1 = p0 if px is None else (2 * cx - px, 2 * cy - py)
                    p2, p3 = (vals[0], vals[1]), (vals[2], vals[3])
                points.extend([p0, p3] + _cubic_extrema(p0, p1, p2, p3))
                cx, cy = p3
                px, py = p2
            elif upper == "Q":
                vals = [float(v) for v in tokens[i:i + 4]]; i += 4
                if relative:
                    vals = [vals[j] + (cx if j % 2 == 0 else cy) for j in range(4)]
                p0 = (cx, cy)
                p1, p2 = (vals[0], vals[1]), (vals[2], vals[3])
                points.extend([p0, p2] + _quad_extrema(p0, p1, p2))
                cx, cy = p2
                px, py = p1
            elif upper == "T":
                x, y = float(tokens[i]), float(tokens[i + 1]); i += 2
                if relative:
                    x += cx; y += cy
                p0 = (cx, cy)
                p1 = p0 if px is None else (2 * cx - px, 2 * cy - py)
                p2 = (x, y)
                points.extend([p0, p2] + _quad_extrema(p0, p1, p2))
                cx, cy = p2
                px, py = p1
            elif upper == "A":
                vals = [float(v) for v in tokens[i:i + 7]]; i += 7
                x, y = vals[5], vals[6]
                if relative:
                    x += cx; y += cy
                points.extend(_arc_points(
                    (cx, cy), vals[0], vals[1], vals[2],
                    bool(vals[3]), bool(vals[4]), (x, y)))
                cx, cy = x, y
                px = py = None
            else:
                i += 1
        except (ValueError, IndexError):
            i += 1
    return points


def first_number(value, default=0.0):
    """Parse a numeric SVG attribute, tolerating units such as px or mm."""
    if value is None:
        return default
    match = re.match(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?",
                     str(value).strip())
    return float(match.group()) if match else default


def element_by_id(root, ident):
    """Find an element by id, including targets inside <defs>."""
    if root is None or not ident:
        return None
    for elem in root.iter():
        if elem.get("id") == ident:
            return elem
    return None


def use_href_id(elem):
    """Return the referenced id of a <use>, supporting href and xlink:href."""
    href = (elem.get("{http://www.w3.org/1999/xlink}href") or
            elem.get("href") or "").strip()
    if href.startswith("#"):
        return href[1:]
    if href.startswith("url(#") and href.endswith(")"):
        return href[5:-1]
    return ""


def bbox_of_element(elem, parent_transform=None, root=None, visited=None):
    """Return (x0, y0, x1, y1) for an element in document user units."""
    if parent_transform is None:
        parent_transform = Transform()
    seen = set(visited) if visited is not None else set()
    if id(elem) in seen:  # protect against recursive/cyclic <use>
        return None
    seen.add(id(elem))

    own = Transform.parse(elem.get("transform", ""))
    t = parent_transform * own

    tag = elem.tag.split("}")[-1]
    pts = []

    def add(x, y):
        pts.append(t.apply(x, y))

    def add_box(x, y, w, h):
        for p in ((x, y), (x + w, y), (x + w, y + h), (x, y + h)):
            add(*p)

    if tag == "rect" and elem.get("width") is not None and elem.get("height") is not None:
        add_box(first_number(elem.get("x")), first_number(elem.get("y")),
                first_number(elem.get("width")), first_number(elem.get("height")))
    elif tag == "circle":
        cx, cy = first_number(elem.get("cx")), first_number(elem.get("cy"))
        r = first_number(elem.get("r"))
        add_box(cx - r, cy - r, r * 2, r * 2)
    elif tag == "ellipse":
        cx, cy = first_number(elem.get("cx")), first_number(elem.get("cy"))
        rx, ry = first_number(elem.get("rx")), first_number(elem.get("ry"))
        add_box(cx - rx, cy - ry, rx * 2, ry * 2)
    elif tag == "line":
        add(first_number(elem.get("x1")), first_number(elem.get("y1")))
        add(first_number(elem.get("x2")), first_number(elem.get("y2")))
    elif tag in ("polygon", "polyline"):
        raw = elem.get("points", "")
        nums = [float(v) for v in raw.replace(",", " ").split() if _is_number(v)]
        for j in range(0, len(nums) - 1, 2):
            add(nums[j], nums[j + 1])
    elif tag == "path" and elem.get("d"):
        for x, y in parse_path_points(elem.get("d")):
            add(x, y)
    elif tag == "image":
        if elem.get("width") is not None and elem.get("height") is not None:
            add_box(first_number(elem.get("x")), first_number(elem.get("y")),
                    first_number(elem.get("width")), first_number(elem.get("height")))
    elif tag == "use":
        # Inkscape clones are <use> elements pointing at an object in <defs>.
        target = element_by_id(root, use_href_id(elem))
        if target is not None:
            offset = Transform(1, 0, 0, 1,
                               first_number(elem.get("x")),
                               first_number(elem.get("y")))
            cb = bbox_of_element(target, t * offset, root, seen)
            if cb:
                pts.extend([(cb[0], cb[1]), (cb[2], cb[3])])
    elif tag == "text":
        x, y = first_number(elem.get("x")), first_number(elem.get("y"))
        fs = 12.0
        for child in elem.iter():
            if child.get("font-size"):
                fs = first_number(child.get("font-size"), fs)
                break
        w = max(1, len("".join(elem.itertext()))) * fs * 0.6
        add(x, y); add(x + w, y); add(x, y - fs)

    # Symbols, flow roots, foreign objects and other containers may carry an
    # explicit box instead of drawable children.
    if not pts:
        if elem.get("width") is not None and elem.get("height") is not None:
            add_box(first_number(elem.get("x")), first_number(elem.get("y")),
                    first_number(elem.get("width")), first_number(elem.get("height")))
        elif elem.get("viewBox"):
            nums = [first_number(v) for v in
                    elem.get("viewBox").replace(",", " ").split()]
            if len(nums) >= 4 and nums[2] > 0 and nums[3] > 0:
                add_box(nums[0], nums[1], nums[2], nums[3])

    # Groups and any unsupported container types recurse into their children.
    # A selected parent may contain an old ruler; never let that ruler inflate
    # the bounding box of the real object.
    if not pts:
        old_rulers = generated_ruler_roots(root) if root is not None else []
        for child in elem:
            if not isinstance(child.tag, str):
                continue
            if any(r is child or _is_ancestor(r, child) for r in old_rulers):
                continue
            cb = bbox_of_element(child, t, root, seen)
            if cb:
                pts.extend([(cb[0], cb[1]), (cb[2], cb[3])])

    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def _is_ancestor(ancestor, elem):
    """True if ancestor contains elem somewhere below it."""
    for child in ancestor:
        if child is elem or _is_ancestor(child, elem):
            return True
    return False


def unique_id(root, base):
    """Return base or a numbered variant that does not collide in root."""
    used = {e.get("id") for e in root.iter() if e.get("id")}
    if base not in used:
        return base
    n = 2
    while "%s-%d" % (base, n) in used:
        n += 1
    return "%s-%d" % (base, n)


def generated_ruler_roots(root):
    """All ruler groups already in the document. Never restyle these."""
    return [e for e in root.iter()
            if isinstance(e.tag, str) and
            e.get("id", "").startswith("object-ruler-generated")]


def inside_generated_ruler(elem, roots):
    return any(_is_ancestor(r, elem) for r in roots)


def union_bbox(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def ancestor_transform(root, elem):
    """Composed transform of all ancestors of elem, in root coordinates."""
    chain = []
    cur = elem
    while cur is not None and cur is not root:
        parent = None
        for candidate in root.iter():
            if any(child is cur for child in candidate):
                parent = candidate
                break
        if parent is None:
            break
        chain.append(parent)
        cur = parent
    chain.reverse()
    t = Transform()
    for anc in chain:
        t = t * Transform.parse(anc.get("transform", ""))
    return t


def selected_bbox(root, ids):
    """Find bounding box of selected elements, ignoring old ruler geometry."""
    boxes = []
    old_rulers = generated_ruler_roots(root)
    for elem in [root] + list(root.iter()):
        if not isinstance(elem.tag, str):
            continue
        if inside_generated_ruler(elem, old_rulers):
            continue
        eid = elem.get("id")
        label = elem.get("{%s}label" % INKSCAPE_NS)
        if eid in ids or label in ids:
            b = bbox_of_element(elem, ancestor_transform(root, elem), root)
            if b:
                boxes.append(b)
    return union_bbox(boxes)


# ---------------------------------------------------------------------------
# Ruler generation
# ---------------------------------------------------------------------------
def nice_step(total, target_count):
    """Pick a pleasant step size (~target_count labels across total)."""
    if total <= 0:
        return 1.0
    rough = total / max(1, target_count)
    exp = math.floor(math.log10(rough))
    base = 10 ** exp
    for mult in (1, 2, 5, 10):
        step = mult * base
        if step >= rough:
            return step
    return 10 * base


def fmt_number(value, precision=6):
    """Compact, rounded string suitable for coordinates in SVG attributes."""
    if abs(value) < 10 ** (-precision):
        value = 0.0
    if abs(value - round(value)) < 10 ** (-precision):
        return str(int(round(value)))
    return ("%.*f" % (precision, value)).rstrip("0").rstrip(".")


def fmt_label(value, units_per_unit, decimals=-1):
    """Human-friendly measurement; decimals=-1 uses display-based precision."""
    if abs(value) < 1e-9:
        return "0"
    if decimals >= 0:
        return ("%.*f" % (decimals, value))
    # Show millimetre-level detail by default so a 19.299 mm object is not
    # reported as 19.3 mm. Inches and pixels still trim trailing zeros below.
    quantum = 0.001 / units_per_unit
    if quantum >= 1:
        rounded = round(value / quantum) * quantum
        return str(int(rounded)) if abs(rounded - round(rounded)) < 1e-9 else fmt_number(rounded)
    places = max(0, min(4, int(math.ceil(-math.log10(quantum)))))
    snapped = round(value / quantum) * quantum
    nearest = round(snapped)
    if abs(snapped - nearest) < quantum * 0.51:
        return str(nearest)
    s = ("%.*f" % (places, snapped)).rstrip("0").rstrip(".")
    return s or "0"


def approx_text_width(text, font_size):
    """Conservative sans-serif width estimate used only for spacing."""
    return len(text or "") * font_size * 0.62


def build_ruler_group(bbox, opts, root=None):
    """Return (group, width, height, object_x, object_y) for a NEW ruler.

    Existing ruler groups in root are never modified; generated ids get a
    numeric suffix when the document already contains the base id.
    """
    x0, y0, x1, y1 = bbox
    obj_w, obj_h = x1 - x0, y1 - y0
    if obj_w <= 0 or obj_h <= 0:
        raise ValueError("Selected object must have a positive width and height.")

    # Bounds are measured in document user units. Convert those to the chosen
    # display unit using the root viewBox scale. For a typical mm document
    # (width="210mm" viewBox="0 0 210 297") one user unit is one millimetre.
    user_scale = svg_user_unit_scale(root)
    units_per_unit = UNIT_TO_PX[opts["unit"]] / user_scale
    label = UNIT_LABEL[opts["unit"]]
    gap = float(opts["offset"])
    major_len = float(opts["major_length"])   # long ticks at start/end
    minor_len = float(opts["minor_length"])   # small ticks at 1 unit
    medium_len = major_len * 0.72              # medium ticks at multiples of 5
    sub_len = minor_len * 0.55                 # smallest subdivision ticks
    label_font_size = float(opts["label_font_size"])
    total_font_size = float(opts["total_font_size"])
    if label_font_size <= 0:
        label_font_size = float(opts["font_size"])
    if total_font_size <= 0:
        total_font_size = float(opts["font_size"])
    display_font_size = max(label_font_size, total_font_size)
    minor_div = max(1, int(opts["minor_divisions"]))
    show_labels = bool(opts["show_labels"])
    # One color chooser drives both fill and stroke on ruler lines. SVG lines
    # have no interior, so the stroke is the visible result.
    line_color = css_color(opts["line_color"], "#333333")
    line_fill_color = line_color
    line_border_color = line_color
    text_color = css_color(opts["text_color"], "#222222")
    text_border_color = css_color(opts["text_border_color"], "#ffffff")
    line_width = float(opts["line_width"])
    text_gap = float(opts["text_gap"])
    label_decimals = int(opts["label_decimals"])
    show_zero = bool(opts["show_zero"])
    label_mode = str(opts["label_mode"]).strip().lower()
    origin = str(opts["origin"]).strip().lower()
    if origin not in ("start", "center", "end"):
        origin = "start"
    tick_direction = str(opts["tick_direction"]).strip().lower()
    if tick_direction not in ("out", "in"):
        tick_direction = "out"

    sides = {
        "top": bool(opts["show_top"]),
        "bottom": bool(opts["show_bottom"]),
        "left": bool(opts["show_left"]),
        "right": bool(opts["show_right"]),
    }
    if not any(sides.values()):
        raise ValueError("Enable at least one ruler side (top, bottom, left or right).")

    fit = 1.0
    if opts["auto_fit"]:
        fit = min(1.0, max(0.5, min(obj_w, obj_h) / 60.0))
        gap *= fit
        major_len *= fit
        minor_len *= fit
        medium_len *= fit
        sub_len *= fit
        label_font_size *= fit
        total_font_size *= fit
        display_font_size *= fit
        text_gap *= fit
        line_width = max(0.2, line_width * fit)
    line_width_s = fmt_number(line_width)
    # Fixed, readable outline for labels; independent of ruler line width.
    text_border_width_s = fmt_number(2.0)
    # The 2 px text border is centred on the glyph outline. Bottom and right
    # labels start outside the ruler, so give them extra clearance for both
    # number and zero labels; top/left keep the configured text_gap.
    bottom_right_text_gap = text_gap + max(3.0, 0.25 * display_font_size)
    # The rotated total on left/right must clear the number-label column.
    vertical_total_pad = 2.0

    eps = 1e-7

    def tick_style(offset, value, total_px):
        """Return (CSS class, length) for a tick at this axis position."""
        if abs(offset) < eps or abs(offset - total_px) < eps:
            return "ruler-tick ruler-tick-end", major_len
        if is_multiple(value, 5.0):
            return "ruler-tick ruler-tick-medium", medium_len
        if is_multiple(value, 1.0):
            return "ruler-tick ruler-tick-small", minor_len
        return "ruler-tick ruler-tick-sub", sub_len

    def aligned_majors(total_px, step_px):
        """Major offsets aligned to the selected zero point."""
        anchor = {"start": 0.0, "center": total_px / 2.0,
                  "end": total_px}[origin]
        k_min = int(math.floor(-anchor / step_px)) - 1
        k_max = int(math.ceil((total_px - anchor) / step_px)) + 1
        found = []
        for k in range(k_min, k_max + 1):
            off = anchor + k * step_px
            if -eps <= off <= total_px + eps:
                off = min(total_px, max(0.0, off))
                if not any(abs(off - old) < eps for old in found):
                    found.append(off)
        return sorted(found)

    def axis_ticks(total_px, step_px):
        """Return sorted (offset_px, value_units, is_major) tick definitions."""
        majors = aligned_majors(total_px, step_px)
        total_units = total_px / units_per_unit

        def value_at(off):
            if origin == "center":
                return off / units_per_unit - total_units / 2.0
            if origin == "end":
                return off / units_per_unit - total_units
            return off / units_per_unit

        bounds = [0.0] + majors + [total_px]
        clean = []
        for value in bounds:
            if not clean or abs(value - clean[-1]) > eps:
                clean.append(value)

        found = {}

        def add(off, force_major=False):
            off = min(total_px, max(0.0, off))
            key = round(off, 6)
            major = (force_major or
                     any(abs(off - m) < eps for m in majors) or
                     off < eps or off > total_px - eps)
            if key not in found or major:
                found[key] = (off, value_at(off), major)

        for a, b in zip(clean, clean[1:]):
            if b - a < eps:
                continue
            for j in range(minor_div):
                add(a + (b - a) * j / minor_div)
        add(0.0, True)
        add(total_px, True)
        return [found[key] for key in sorted(found)]

    def horizontal_label_y(side_name, baseline_y, direction, size):
        """Place labels outside the ruler for both inward and outward ticks."""
        tip = baseline_y + direction * major_len
        outer_edge = min(baseline_y, tip) if side_name == "top" else max(baseline_y, tip)
        if side_name == "top":
            return outer_edge - text_gap
        # SVG text y is the baseline, so add one font height plus the larger
        # bottom clearance to keep the glyph clear of the line.
        return outer_edge + bottom_right_text_gap + size

    def vertical_label_x(side_name, baseline_x, direction):
        """Place labels outside the ruler and return (x, text-anchor)."""
        tip = baseline_x + direction * major_len
        if side_name == "left":
            return min(baseline_x, tip) - text_gap, "end"
        return max(baseline_x, tip) + bottom_right_text_gap, "start"

    # Space reserved outside the object for each enabled ruler. Bottom/right
    # need more room because their labels use the larger clearance.
    base_space = gap + major_len + (
        display_font_size + text_gap + 2.0 if show_labels else 0.0)
    wide_space = gap + major_len + (
        display_font_size + bottom_right_text_gap + 2.0 if show_labels else 0.0)
    left_margin = base_space if sides["left"] else gap
    right_margin = wide_space if sides["right"] else gap
    top_margin = base_space if sides["top"] else gap
    bottom_margin = wide_space if sides["bottom"] else gap
    obj_ox = left_margin
    obj_oy = top_margin
    ruler_w = obj_ox + obj_w + right_margin
    ruler_h = obj_oy + obj_h + bottom_margin

    def new_id(base):
        return unique_id(root, base) if root is not None else base

    gid = new_id("object-ruler-generated")
    # Give every generation a distinct label as well as a distinct id, so
    # Inkscape's Objects panel and XML editor can tell old rulers apart.
    label_suffix = gid[len("object-ruler-generated"):].replace("-", " ")

    g = ET.Element(q("g"), {
        "id": gid,
        "{%s}label" % INKSCAPE_NS: "Object Ruler" + label_suffix,
        "{%s}groupmode" % INKSCAPE_NS: "layer",
    })

    def group(parent, name, inkscape_label):
        return ET.SubElement(parent, q("g"), {
            "id": new_id(name),
            "{%s}label" % INKSCAPE_NS: inkscape_label + label_suffix,
        })

    # Horizontal and vertical rulers live in separate groups so they can be
    # selected, hidden, or styled independently in Inkscape.
    horizontal_group = group(g, "object-ruler-horizontal", "Horizontal Rulers")
    vertical_group = group(g, "object-ruler-vertical", "Vertical Rulers")
    side_groups = {}
    for side_name in ("top", "bottom"):
        if sides[side_name]:
            side_groups[side_name] = group(
                horizontal_group, "object-ruler-" + side_name, side_name.title() + " Ruler")
    for side_name in ("left", "right"):
        if sides[side_name]:
            side_groups[side_name] = group(
                vertical_group, "object-ruler-" + side_name, side_name.title() + " Ruler")

    def add_line(parent, x1l, y1l, x2l, y2l, cls):
        # The combined Line color is written to both fill and stroke. The
        # stroke is the visible part because SVG lines have no interior.
        ET.SubElement(parent, q("line"), {
            "x1": fmt_number(x1l), "y1": fmt_number(y1l),
            "x2": fmt_number(x2l), "y2": fmt_number(y2l),
            "class": cls,
            "stroke": line_border_color,
            "fill": line_fill_color,
            "stroke-width": line_width_s,
            "stroke-linecap": "square",
        })

    def add_text(parent, x, y, text, cls, anchor="middle", rotate=None, size=None):
        size = label_font_size if size is None else size
        attrs = {
            "x": fmt_number(x), "y": fmt_number(y),
            "class": cls,
            "fill": text_color,
            "stroke": text_border_color,
            "stroke-width": text_border_width_s,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
            "paint-order": "stroke fill",
            "style": "font-size:%spx;text-anchor:%s;font-family:sans-serif" % (
                fmt_number(size), anchor),
        }
        if rotate is not None:
            attrs["transform"] = "rotate(%s %s %s)" % tuple(
                fmt_number(v) for v in rotate)
        t = ET.SubElement(parent, q("text"), attrs)
        t.text = text
        return t

    total_x = obj_w / units_per_unit
    total_y = obj_h / units_per_unit
    major_x = max(1e-6, nice_step(total_x, max(1, int(total_x / 3))) * units_per_unit)
    major_y = max(1e-6, nice_step(total_y, max(1, int(total_y / 3))) * units_per_unit)

    # --- horizontal rulers (top / bottom) ---
    for side_name in ("top", "bottom"):
        if not sides[side_name]:
            continue
        parent = side_groups[side_name]
        outward = -1 if side_name == "top" else 1
        direction = outward if tick_direction == "out" else -outward
        baseline_y = obj_oy - gap * 0.5 if side_name == "top" else obj_oy + obj_h + gap * 0.5
        add_line(parent, obj_ox, baseline_y, obj_ox + obj_w, baseline_y,
                 "ruler-baseline ruler-line")

        label_y = horizontal_label_y(side_name, baseline_y, direction, label_font_size)
        total_label_y = horizontal_label_y(side_name, baseline_y, direction, total_font_size)
        for off, value, is_major in axis_ticks(obj_w, major_x):
            x = obj_ox + off
            cls, tick_len = tick_style(off, value, obj_w)
            add_line(parent, x, baseline_y, x, baseline_y + direction * tick_len, cls)
            if (show_labels and is_major and label_mode == "all" and
                    abs(value) > eps and abs(off) > eps and abs(off - obj_w) > eps):
                add_text(parent, x, label_y,
                         fmt_label(value, units_per_unit, label_decimals), "ruler-label")

        if show_labels and show_zero:
            zero_off = {"start": 0.0, "center": obj_w / 2.0, "end": obj_w}[origin]
            add_text(parent, obj_ox + zero_off, label_y, "0", "ruler-label")

        if show_labels:
            total_y_text = total_label_y + (
                -total_font_size * 1.15 if side_name == "top" else total_font_size * 1.15)
            add_text(parent, obj_ox + obj_w / 2.0, total_y_text,
                     "%s %s" % (fmt_label(total_x, units_per_unit, label_decimals), label),
                     "ruler-total", size=total_font_size)

    # --- vertical rulers (left / right) ---
    for side_name in ("left", "right"):
        if not sides[side_name]:
            continue
        parent = side_groups[side_name]
        outward = -1 if side_name == "left" else 1
        direction = outward if tick_direction == "out" else -outward
        baseline_x = obj_ox - gap * 0.5 if side_name == "left" else obj_ox + obj_w + gap * 0.5
        add_line(parent, baseline_x, obj_oy, baseline_x, obj_oy + obj_h,
                 "ruler-baseline ruler-line")

        label_x, label_anchor = vertical_label_x(side_name, baseline_x, direction)
        number_widths = []
        for off, value, is_major in axis_ticks(obj_h, major_y):
            y = obj_oy + off
            cls, tick_len = tick_style(off, value, obj_h)
            add_line(parent, baseline_x, y, baseline_x + direction * tick_len, y, cls)
            if (show_labels and is_major and label_mode == "all" and
                    abs(value) > eps and abs(off) > eps and abs(off - obj_h) > eps):
                value_text = fmt_label(value, units_per_unit, label_decimals)
                number_widths.append(approx_text_width(value_text, label_font_size))
                add_text(parent, label_x, y + label_font_size * 0.35,
                         value_text, "ruler-label", anchor=label_anchor)

        if show_labels and show_zero:
            zero_off = {"start": 0.0, "center": obj_h / 2.0, "end": obj_h}[origin]
            number_widths.append(approx_text_width("0", label_font_size))
            add_text(parent, label_x, obj_oy + zero_off + label_font_size * 0.35,
                     "0", "ruler-label", anchor=label_anchor)

        if show_labels:
            # Place the rotated total beyond the widest number/zero label,
            # with at least vertical_total_pad pixels of clear space.
            max_number_width = max(number_widths) if number_widths else 0.0
            total_offset = (
                max_number_width + vertical_total_pad + total_font_size * 0.5)
            total_x_text = label_x + (
                -total_offset if side_name == "left" else total_offset)
            center_y = obj_oy + obj_h / 2.0
            add_text(parent, total_x_text, center_y,
                     "%s %s" % (fmt_label(total_y, units_per_unit, label_decimals), label),
                     "ruler-total", anchor="middle", size=total_font_size,
                     rotate=(-90 if side_name == "left" else 90, total_x_text, center_y))

    scope = "#" + gid
    style = ET.SubElement(g, q("style"), {"type": "text/css"})
    style.text = """
/* Scoped to %s so previously generated rulers are never restyled. */
%s .ruler-line, %s .ruler-tick {
  stroke:%s;
  stroke-width:%s;
  fill:%s;
  stroke-linecap:square;
}
%s .ruler-label, %s .ruler-total {
  paint-order:stroke fill;
  stroke:%s;
  stroke-width:%s;
  stroke-linecap:round;
  stroke-linejoin:round;
}
%s .ruler-label { fill:%s; font-size:%spx; font-family:sans-serif; }
%s .ruler-total { fill:%s; font-weight:bold; font-size:%spx; font-family:sans-serif; }
""" % (gid, scope, scope, line_border_color, line_width_s, line_fill_color,
       scope, scope, text_border_color, text_border_width_s,
       scope, text_color, fmt_number(label_font_size),
       scope, text_color, fmt_number(total_font_size))
    return g, ruler_w, ruler_h, obj_ox, obj_oy


# ---------------------------------------------------------------------------
# Extension entry point
# ---------------------------------------------------------------------------
def expand_arg_file(args):
    """Inkscape on Windows may pass --arg-file=<path> with one arg per line."""
    expanded = []
    for arg in args:
        if arg.startswith("--arg-file="):
            path = arg[len("--arg-file="):]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    expanded.extend(line.strip() for line in f if line.strip())
                continue
            except OSError:
                pass
        expanded.append(arg)
    return expanded


def parse_extra_args(args):
    """
    Return (options, ids) from Inkscape-style command line arguments.
    Supports: --unit=mm, --unit mm, -i box, --id=box, --param unit mm.
    """
    defaults = dict(DEFAULTS)
    opts = dict(defaults)
    raw_values = {}
    ids = []
    args = expand_arg_file(args)
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--param" and i + 2 < len(args):
            name, raw = args[i + 1], args[i + 2]
            i += 3
        elif arg.startswith("--") and "=" in arg:
            name, raw = arg[2:].split("=", 1)
            i += 1
        elif arg.startswith("-") and "=" in arg:
            name, raw = arg[1:].split("=", 1)
            i += 1
        elif arg.startswith("-") and i + 1 < len(args) and not args[i + 1].startswith("-"):
            name, raw = arg.lstrip("-"), args[i + 1]
            i += 2
        else:
            i += 1
            continue
        key = name.replace("-", "_")
        # Backward-compatible aliases for the old four-color layout.
        if key == "halo_color":
            key = "text_border_color"
        if key in ("line_border_color", "text_halo"):
            continue  # merged into Line color / always-on text border
        if key in ("id", "i", "ids", "selected", "selection"):
            # Inkscape may pass one id, several comma/space separated ids, a
            # JSON-ish list, or a CSS-style "#id" / "url(#id)" reference.
            for part in re.split(r"[\s,;|]+", raw):
                ident = part.strip().strip("\"'[]{}()")
                if ident.startswith("url(#") and ident.endswith(")"):
                    ident = ident[5:-1]
                ident = unquote(ident)
                if ident.startswith("#"):
                    ident = ident[1:]
                if "#" in ident or "=" in ident:  # path#id or [id=id]
                    match = re.search(r"[#=]([\w.\-:]+)", ident)
                    if match:
                        ident = match.group(1)
                ident = ident.strip("\"'[]{}()")
                if ident:
                    ids.append(ident)
        elif key in opts:
            raw_values[key] = raw
            val = opts[key]
            if isinstance(val, bool):
                opts[key] = raw.strip().lower() in ("true", "1", "yes", "on")
            elif isinstance(val, int):
                try: opts[key] = int(raw)
                except ValueError: pass
            elif isinstance(val, float):
                try: opts[key] = float(raw)
                except ValueError: pass
            else:
                opts[key] = raw
    if opts["unit"] not in UNIT_TO_PX:
        opts["unit"] = "mm"
    # Old command lines used --font-size for both text sizes. Do this before
    # presets so a selected preset always has the final word.
    if "font_size" in raw_values:
        if "label_font_size" not in raw_values:
            opts["label_font_size"] = opts["font_size"]
        if "total_font_size" not in raw_values:
            opts["total_font_size"] = opts["font_size"]
    apply_preset(opts, raw_values)
    return opts, ids


def run(input_svg, args):
    opts, ids = parse_extra_args(args)
    root = ET.fromstring(input_svg)

    if not ids:
        # Fall back to every top-level drawing element when run standalone.
        ids = [e.get("id") for e in root if e.get("id") and
               e.tag.split("}")[-1] in
               ("rect", "circle", "ellipse", "path", "polygon", "polyline",
                "line", "text", "g", "use")]
        if not ids:
            raise ValueError("No object selected. Select a shape and run the extension again.")

    bbox = selected_bbox(root, ids)
    if not bbox:
        matched = []
        for ident in ids:
            elem = element_by_id(root, ident)
            if elem is None:
                for candidate in root.iter():
                    if candidate.get("{%s}label" % INKSCAPE_NS) == ident:
                        elem = candidate
                        break
            if elem is not None:
                matched.append("%s <%s>" % (ident, elem.tag.split("}")[-1]))
        hint = ""
        if ids:
            hint = " Ids received: %s. Matching elements: %s." % (
                ", ".join(ids), ", ".join(matched) or "none")
        raise ValueError(
            "Could not determine bounding box of selected object(s)." + hint +
            " Select a shape, group, clone, image, path or text, then try again.")

    g, rw, rh, ox, oy = build_ruler_group(bbox, opts, root)

    # Position the ruler group in document coordinates.
    g.set("transform", "translate(%s %s)" % (
        fmt_number(bbox[0] - ox), fmt_number(bbox[1] - oy)))

    if opts["group_with_object"]:
        # Build a parent map so we can move selected elements out of layers.
        parents = {child: parent for parent in root.iter() for child in parent}
        old_rulers = generated_ruler_roots(root)
        selected = []
        for elem in [root] + list(root.iter()):
            if not isinstance(elem.tag, str):
                continue
            if inside_generated_ruler(elem, old_rulers):
                continue  # old rulers are read-only
            if elem.get("id") in ids or elem.get("{%s}label" % INKSCAPE_NS) in ids:
                selected.append(elem)
        # Only move top-most selected elements (skip ones inside other selected groups).
        top_selected = [e for e in selected
                        if not any(e is not anc and _is_ancestor(anc, e)
                                   for anc in selected)]

        # If every selected object already lives in the same ruler wrapper,
        # add the new ruler there without moving or restyling the old one.
        wrappers = []
        for elem in top_selected:
            cur = parents.get(elem)
            while cur is not None and cur is not root:
                if (cur.get("id", "").startswith("object-ruler-wrapper") or
                        cur.get("{%s}label" % INKSCAPE_NS) == "Measured Object"):
                    wrappers.append(cur)
                    break
                cur = parents.get(cur)
        shared_wrapper = None
        if wrappers and all(w is wrappers[0] for w in wrappers):
            shared_wrapper = wrappers[0]

        if shared_wrapper is not None:
            wrapper = shared_wrapper
            # g was positioned in root coordinates; convert to wrapper space.
            placed = Transform.parse(g.get("transform", ""))
            adjusted = ancestor_transform(root, wrapper).inverse() * placed
            g.set("transform", "matrix(%s)" % ",".join(
                fmt_number(v) for v in adjusted.m))
            wrapper.append(g)
        else:
            wid = unique_id(root, "object-ruler-wrapper")
            wrapper_label_suffix = wid[len("object-ruler-wrapper"):].replace("-", " ")
            wrapper = ET.Element(q("g"), {
                "id": wid,
                "{%s}label" % INKSCAPE_NS: "Measured Object" + wrapper_label_suffix,
            })
            for elem in top_selected:
                parent = parents.get(elem, root)
                # Bake ancestor transforms into the element so it stays in place.
                anc = ancestor_transform(root, elem)
                if any(abs(v - default) > 1e-12 for v, default in
                       zip(anc.m, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))):
                    own = Transform.parse(elem.get("transform", ""))
                    combined = anc * own
                    elem.set("transform",
                             "matrix(%s)" % ",".join(fmt_number(v) for v in combined.m))
                try:
                    parent.remove(elem)
                except ValueError:
                    continue
                wrapper.append(elem)
            wrapper.append(g)
            root.append(wrapper)
    else:
        root.append(g)

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def read_svg_input(args):
    """Return (svg_text, option_args).

    Inkscape executes extensions as:

        python ruler.py [options...] <temporary-input.svg>

    Standalone use also accepts:

        python ruler.py <input.svg> [options...]
        python ruler.py [options...] < input.svg
        python ruler.py [options...] --output=out.svg <input.svg>
    """
    args = expand_arg_file(args)
    input_path = None
    output_path = None
    option_args = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--") and "=" in arg:
            name, raw = arg[2:].split("=", 1)
            if name in ("input", "input-file", "svg", "file") and raw:
                input_path = raw
                i += 1
                continue
            if name in ("output", "out") and raw:
                output_path = raw
                i += 1
                continue
        if not arg.startswith("-") and input_path is None and os.path.isfile(arg):
            input_path = arg
            i += 1
            continue
        option_args.append(arg)
        i += 1

    if input_path:
        with open(input_path, "r", encoding="utf-8") as f:
            return f.read(), option_args, output_path

    data = sys.stdin.read()
    if not data.strip():
        raise ValueError(
            "no SVG input received. Inkscape should pass a temporary SVG file "
            "as the last argument; reinstall ruler.py if it does not."
        )
    return data, option_args, output_path


def main():
    try:
        data, args, output_path = read_svg_input(sys.argv[1:])
        result = run(data, args)
        payload = result.encode("utf-8")
        if output_path:
            with open(output_path, "wb") as f:
                f.write(payload)
        else:
            sys.stdout.buffer.write(payload)
    except Exception as exc:  # report to Inkscape UI
        sys.stderr.write("%s error: %s\n" % (EXTENSION_NAME, exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
