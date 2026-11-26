"""Small smoke tests for ruler.py (no Inkscape required)."""
import atexit
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

SVG_NS = "{http://www.w3.org/2000/svg}"
INX_NS = "{http://www.inkscape.org/namespace/inkscape/extension}"
INK_LABEL = "{http://www.inkscape.org/namespaces/inkscape}label"
HERE = Path(__file__).parent
SCRIPT = HERE / "ruler.py"
SAMPLE_SVG = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="200mm" viewBox="0 0 200 200">
  <rect id="box" x="40" y="40" width="75.6" height="189" fill="#88c" stroke="#000"/>
</svg>
'''
with tempfile.NamedTemporaryFile(
    "w", suffix=".svg", delete=False, encoding="utf-8"
) as _sample_file:
    _sample_file.write(SAMPLE_SVG)
    SAMPLE = Path(_sample_file.name)
atexit.register(lambda: SAMPLE.unlink(missing_ok=True))


def load_ruler_module():
    spec = importlib.util.spec_from_file_location("ruler_module", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RULER = load_ruler_module()


def _execute(argv, input_text=None):
    result = subprocess.run(
        argv, input=input_text, capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, result.stderr
    return ET.fromstring(result.stdout)


def run(args, input_first=True):
    argv = [sys.executable, str(SCRIPT)]
    if input_first:
        argv += [str(SAMPLE)] + args
    else:
        argv += args + [str(SAMPLE)]  # Inkscape's argument order
    return _execute(argv)


def run_svg(svg_text, args):
    with tempfile.NamedTemporaryFile(
        "w", suffix=".svg", delete=False, encoding="utf-8"
    ) as f:
        f.write(svg_text)
        path = f.name
    try:
        return _execute([sys.executable, str(SCRIPT), path] + args)
    finally:
        Path(path).unlink(missing_ok=True)


def run_stdin(args):
    return _execute(
        [sys.executable, str(SCRIPT)] + args,
        input_text=SAMPLE.read_text(encoding="utf-8"),
    )


# Inkscape passes every control on every run. These values deliberately differ
# from the INX defaults so tests prove a preset overrides manual GUI edits.
INKSCAPE_STYLE_ARGS = [
    "--minor-divisions=10",
    "--show-top=true", "--show-bottom=false",
    "--show-left=true", "--show-right=false",
    "--origin=start", "--tick-direction=out",
    "--label-mode=all", "--label-decimals=-1", "--show-zero=true",
    "--offset=99", "--major-length=99", "--minor-length=99",
    "--label-font-size=99", "--total-font-size=99",
    "--auto-fit=false", "--line-width=99", "--text-gap=99",
    "--text-color=0xff0000ff", "--text-border-color=0x00ff00ff",
    "--line-color=0x0000ffff", "--group-with-object=true",
]


def inkscape_run(preset, extra=None):
    args = ["--id=box", "--unit=cm", "--preset=" + preset]
    args += INKSCAPE_STYLE_ARGS
    if extra:
        args += extra
    return run(args, input_first=False)


def texts(root, cls=None):
    result = []
    for e in root.iter(SVG_NS + "text"):
        if cls is None or e.get("class") == cls:
            result.append(e.text)
    return result


def text_elements(root, cls=None):
    return [e for e in root.iter(SVG_NS + "text")
            if cls is None or e.get("class") == cls]


def label_font_size(elem):
    return float(elem.get("style", "").split("font-size:")[1].split("px")[0])


def totals(root):
    return texts(root, "ruler-total")


def lines(root):
    return list(root.iter(SVG_NS + "line"))


def css(root):
    node = root.find(".//" + SVG_NS + "style")
    return node.text or ""


def group_ids(root):
    return {g.get("id") for g in root.iter(SVG_NS + "g")}


def group(parent, name):
    return next((g for g in parent.iter(SVG_NS + "g")
                 if g.get("id") == name), None)


def parent_group_id(root, child_id):
    for g in root.iter(SVG_NS + "g"):
        if any(c.get("id") == child_id for c in g):
            return g.get("id")
    return None


def test_cm():
    root = run(["--id=box", "--unit=cm"])
    labels = totals(root)
    assert "7.56 cm" in labels and "18.9 cm" in labels, labels
    print("cm: OK", labels)


def test_mm():
    root = run(["--id=box", "--unit=mm"])
    labels = totals(root)
    assert "75.6 mm" in labels and "189 mm" in labels, labels
    print("mm: OK", labels)


def test_inches():
    root = run(["--id=box", "--unit=in"])
    labels = totals(root)
    assert "2.9764 in" in labels and "7.4409 in" in labels, labels
    print("in: OK", labels)


MM_CURVE_SVG = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="210mm" height="297mm" viewBox="0 0 210 297">
  <g id="wrapper">
    <path id="curve" d="M 0 0 C 20 0 20 20 0 20 Z"/>
    <g id="object-ruler-generated" inkscape:label="Object Ruler">
      <line x1="-100" y1="-100" x2="500" y2="500"/>
    </g>
  </g>
</svg>
'''


def test_physical_document_curve_bbox():
    """mm viewBox documents measure in mm and ignore old ruler geometry."""
    doc = ET.fromstring(MM_CURVE_SVG)
    bbox = RULER.selected_bbox(doc, ["wrapper"])
    assert bbox is not None
    assert abs((bbox[2] - bbox[0]) - 15.0) < 1e-6, bbox
    assert abs((bbox[3] - bbox[1]) - 20.0) < 1e-6, bbox
    assert abs(RULER.svg_user_unit_scale(doc) - (96.0 / 25.4)) < 1e-9

    px_doc = ET.fromstring(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"/>')
    assert RULER.svg_user_unit_scale(px_doc) == 1.0

    root = run_svg(MM_CURVE_SVG, ["--id=wrapper", "--unit=mm"])
    labels = totals(root)
    assert "15 mm" in labels and "20 mm" in labels, labels
    print("physical document curve bbox: OK", labels)


def test_no_labels():
    root = run(["--id=box", "--unit=cm", "--show-labels=false"])
    assert len(list(root.iter(SVG_NS + "text"))) == 0
    print("no labels: OK")


def test_ungrouped():
    root = run(["--id=box", "--unit=cm", "--group-with-object=false"])
    assert "object-ruler-wrapper" not in group_ids(root)
    print("ungrouped: OK")


CLONE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg"
  xmlns:xlink="http://www.w3.org/1999/xlink">
  <defs><rect id="src" width="50" height="30"/></defs>
  <use id="clone" xlink:href="#src" x="10" y="20"/>
</svg>'''

GROUP_CLONE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg"
  xmlns:xlink="http://www.w3.org/1999/xlink">
  <defs><rect id="src2" width="50" height="30"/></defs>
  <g id="sel" transform="translate(5 7)">
    <use id="clone2" xlink:href="#src2" x="10" y="20"/>
  </g>
</svg>'''

IMAGE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg">
  <image id="pic" x="5" y="7" width="40" height="20"/>
</svg>'''

MULTI_SVG = '''<svg xmlns="http://www.w3.org/2000/svg">
  <rect id="a" x="0" y="0" width="20" height="10"/>
  <rect id="b" x="100" y="50" width="30" height="15"/>
</svg>'''


def test_selection_bbox_cases():
    """Clones, groups, images and comma-separated ids must be measurable."""
    args = ["--unit=px", "--show-top=true", "--show-bottom=false",
            "--show-left=true", "--show-right=false"]

    for ident in ("clone", "#clone", "url(#clone)", "clone,missing"):
        root = run_svg(CLONE_SVG, ["--id=" + ident] + args)
        assert "50 px" in totals(root) and "30 px" in totals(root), (
            ident, totals(root))

    root = run_svg(GROUP_CLONE_SVG, ["--id=sel"] + args)
    assert "50 px" in totals(root) and "30 px" in totals(root), totals(root)

    root = run_svg(IMAGE_SVG, ["--id=pic"] + args)
    assert "40 px" in totals(root) and "20 px" in totals(root), totals(root)

    root = run_svg(MULTI_SVG, ["--id=a,b"] + args)
    assert "130 px" in totals(root) and "65 px" in totals(root), totals(root)
    print("selection bbox: OK (clone, group, image, comma ids)")


SYMBOL_SVG = '''<svg xmlns="http://www.w3.org/2000/svg"
  xmlns:xlink="http://www.w3.org/1999/xlink">
  <defs><symbol id="sym" viewBox="0 0 40 25"/></defs>
  <use id="sym_use" xlink:href="#sym" x="10" y="10" width="40" height="25"/>
</svg>'''

FLOW_SVG = '''<svg xmlns="http://www.w3.org/2000/svg">
  <flowRoot id="flow" x="5" y="6" width="60" height="20">
    <flowPara>Hello</flowPara>
  </flowRoot>
</svg>'''

FOREIGN_SVG = '''<svg xmlns="http://www.w3.org/2000/svg">
  <foreignObject id="foreign" x="1" y="2" width="70" height="30"/>
</svg>'''

ARC_SVG = '''<svg xmlns="http://www.w3.org/2000/svg">
  <path id="arc" d="M 0 0 A 30 20 0 0 1 60 0 L 60 40 Z"/>
</svg>'''


def test_extended_bbox_cases():
    """Symbols, flow roots, foreign objects, arcs and odd id forms work."""
    args = ["--unit=px", "--show-top=true", "--show-bottom=false",
            "--show-left=true", "--show-right=false"]

    for svg, ident, expected in (
        (SYMBOL_SVG, "sym_use", ("40 px", "25 px")),
        (FLOW_SVG, "flow", ("60 px", "20 px")),
        (FOREIGN_SVG, "foreign", ("70 px", "30 px")),
        (ARC_SVG, "arc", ("60 px", "40 px")),
    ):
        root = run_svg(svg, ["--id=" + ident] + args)
        labels = totals(root)
        assert all(value in labels for value in expected), (ident, labels)

    for ident in ("path#clone", '["clone"]', "%23clone"):
        root = run_svg(CLONE_SVG, ["--id=" + ident] + args)
        labels = totals(root)
        assert "50 px" in labels and "30 px" in labels, (ident, labels)

    root = run_svg(CLONE_SVG, ["--ids=clone"] + args)
    assert "50 px" in totals(root) and "30 px" in totals(root), totals(root)
    print("extended bbox: OK (symbol, flow, foreignObject, arc, id forms)")


def test_square_caps():
    root = run(["--id=box", "--unit=cm"])
    ls = lines(root)
    assert ls and all(line.get("stroke-linecap") == "square" for line in ls)
    assert "stroke-linecap:square" in css(root)
    print("square caps: OK", len(ls), "lines")


def test_colors():
    root = run([
        "--id=box", "--unit=cm",
        "--line-color=0xff0000ff",
        "--text-color=0x0000ffff",
        "--text-border-color=0x00ff00ff",
    ])
    style = css(root)
    assert "stroke:#ff0000" in style, style       # line border
    assert "fill:#ff0000" in style, style         # line fill
    assert "fill:#0000ff" in style, style         # text fill
    assert "stroke:#00ff00" in style, style       # text border
    ls = lines(root)
    assert ls and all(line.get("stroke") == "#ff0000" for line in ls)
    assert all(line.get("fill") == "#ff0000" for line in ls)
    ts = text_elements(root)
    assert ts and all(text.get("fill") == "#0000ff" for text in ts)
    assert all(text.get("stroke") == "#00ff00" for text in ts)
    print("colors: OK (one line color, text fill + always-on text border)")


def test_same_line_width():
    root = run(["--id=box", "--unit=cm", "--line-width=2.5"])
    widths = {line.get("stroke-width") for line in lines(root)}
    assert widths == {"2.5"}, widths
    assert "stroke-width:2.5" in css(root), css(root)
    print("same line width: OK", widths)


def test_font_sizes():
    root = run([
        "--id=box", "--unit=cm",
        "--label-font-size=9", "--total-font-size=18",
    ])
    style = css(root)
    assert "font-size:9px" in style, style
    assert "font-size:18px" in style, style
    label = text_elements(root, "ruler-label")[0]
    total = text_elements(root, "ruler-total")[0]
    assert "font-size:9px" in label.get("style", "")
    assert "font-size:18px" in total.get("style", "")
    print("label / total font sizes: OK")


def test_text_gap():
    args = ["--id=box", "--unit=cm"]
    small = run(args + ["--text-gap=1"])
    large = run(args + ["--text-gap=10"])

    def label_to_tick_gap(root):
        tick = [line for line in lines(root)
                if "ruler-tick-end" in line.get("class", "")][0]
        label = [e for e in text_elements(root, "ruler-label")
                 if e.text == "0"][0]
        return float(tick.get("y2")) - float(label.get("y"))

    assert abs(label_to_tick_gap(small) - 1) < 1e-6
    assert abs(label_to_tick_gap(large) - 10) < 1e-6
    print("text-to-line gap: OK", label_to_tick_gap(small), label_to_tick_gap(large))


def test_tick_hierarchy():
    root = run(["--id=box", "--unit=mm"])
    classes = [line.get("class", "") for line in lines(root)]
    for kind in ("ruler-tick-end", "ruler-tick-medium",
                 "ruler-tick-small", "ruler-tick-sub"):
        assert any(kind in name for name in classes), (kind, classes[:20])
    print("tick hierarchy: OK")


def test_separated_groups():
    root = run(["--id=box", "--unit=mm",
                "--show-bottom=true", "--show-right=true"])
    ids = group_ids(root)
    expected = {
        "object-ruler-horizontal", "object-ruler-vertical",
        "object-ruler-top", "object-ruler-bottom",
        "object-ruler-left", "object-ruler-right",
    }
    assert expected <= ids, ids
    assert parent_group_id(root, "object-ruler-top") == "object-ruler-horizontal"
    assert parent_group_id(root, "object-ruler-bottom") == "object-ruler-horizontal"
    assert parent_group_id(root, "object-ruler-left") == "object-ruler-vertical"
    assert parent_group_id(root, "object-ruler-right") == "object-ruler-vertical"
    for side in ("top", "bottom", "left", "right"):
        g = group(root, "object-ruler-" + side)
        assert g is not None and list(g.iter(SVG_NS + "line")), side
    print("separated groups: OK")


def test_side_selector():
    root = run([
        "--id=box", "--unit=cm",
        "--show-top=false", "--show-left=false",
        "--show-bottom=true", "--show-right=true",
    ])
    ids = group_ids(root)
    assert "object-ruler-top" not in ids and "object-ruler-left" not in ids
    assert "object-ruler-bottom" in ids and "object-ruler-right" in ids
    assert group(root, "object-ruler-horizontal") is not None
    assert group(root, "object-ruler-vertical") is not None
    print("side selector: OK")


def test_origin_center():
    root = run(["--id=box", "--unit=mm", "--origin=center"])
    labels = texts(root, "ruler-label")
    for expected in ("-10", "0", "10"):
        assert expected in labels, (expected, labels)
    print("center origin: OK", labels[:6])


def test_origin_end():
    root = run(["--id=box", "--unit=mm", "--origin=end"])
    labels = texts(root, "ruler-label")
    assert "-20" in labels and "0" in labels, labels
    print("end origin: OK", labels[:6])


def test_tick_direction():
    args = ["--id=box", "--unit=cm"]
    out_root = run(args)
    in_root = run(args + ["--tick-direction=in"])

    def first_top_tick(root):
        g = group(root, "object-ruler-top")
        return [line for line in g.iter(SVG_NS + "line")
                if "ruler-tick-end" in line.get("class", "")][0]

    out_tick, in_tick = first_top_tick(out_root), first_top_tick(in_root)
    assert float(out_tick.get("y2")) < float(out_tick.get("y1"))
    assert float(in_tick.get("y2")) > float(in_tick.get("y1"))
    print("tick direction: OK")


def test_label_gap_all_sides():
    """Bottom/right labels get extra clearance; top/left keep text_gap."""
    for direction in ("out", "in"):
        root = run([
            "--id=box", "--unit=px", "--tick-direction=" + direction,
            "--show-top=true", "--show-bottom=true",
            "--show-left=true", "--show-right=true",
        ])
        for side in ("top", "bottom", "left", "right"):
            g = group(root, "object-ruler-" + side)
            assert g is not None, (direction, side)
            lines_in_side = list(g.iter(SVG_NS + "line"))
            number_labels = text_elements(g, "ruler-label")
            labels = number_labels + text_elements(g, "ruler-total")
            assert labels, (direction, side)
            assert any(t.text == "0" for t in number_labels), (direction, side)
            assert any(t.text not in (None, "0") for t in number_labels), (direction, side)

            if side in ("top", "bottom"):
                coords = [float(line.get(attr))
                          for line in lines_in_side
                          for attr in ("y1", "y2")]
                edge = min(coords) if side == "top" else max(coords)
            else:
                coords = [float(line.get(attr))
                          for line in lines_in_side
                          for attr in ("x1", "x2")]
                edge = min(coords) if side == "left" else max(coords)

            for label in labels:
                size = label_font_size(label)
                if side == "top":
                    gap = edge - float(label.get("y"))
                elif side == "bottom":
                    # SVG text y is the baseline; the glyph extends upward.
                    gap = (float(label.get("y")) - size) - edge
                elif side == "left":
                    gap = edge - float(label.get("x"))
                else:
                    gap = float(label.get("x")) - edge
                required = 6.0 if side in ("bottom", "right") else 3.0
                assert gap >= required - 1e-6, (
                    direction, side, label.text, gap, edge)
    print("label gap: OK (bottom/right >=6px, top/left >=3px, both tick directions)")


def test_vertical_total_padding():
    """Rotated totals must clear number labels by at least 2 px."""
    for direction in ("out", "in"):
        root = run([
            "--id=box", "--unit=px", "--tick-direction=" + direction,
            "--show-left=true", "--show-right=true",
            "--show-top=false", "--show-bottom=false",
        ])
        for side in ("left", "right"):
            g = group(root, "object-ruler-" + side)
            numbers = text_elements(g, "ruler-label")
            total = text_elements(g, "ruler-total")[0]
            assert numbers, (direction, side)

            center = float(total.get("x"))
            half_total = label_font_size(total) * 0.5
            if side == "right":
                number_edges = [
                    float(t.get("x")) + RULER.approx_text_width(
                        t.text, label_font_size(t))
                    for t in numbers
                ]
                gap = (center - half_total) - max(number_edges)
            else:
                number_edges = [
                    float(t.get("x")) - RULER.approx_text_width(
                        t.text, label_font_size(t))
                    for t in numbers
                ]
                gap = min(number_edges) - (center + half_total)
            assert gap >= 2.0 - 1e-6, (direction, side, gap)
    print("vertical total padding: OK (>=2px beyond number labels)")


def test_label_options():
    root = run(["--id=box", "--unit=mm",
                "--label-mode=origin-total", "--show-zero=false"])
    assert texts(root, "ruler-label") == [], texts(root)
    assert len(totals(root)) == 2

    decimals = run(["--id=box", "--unit=mm", "--label-decimals=2"])
    assert "5.00" in texts(decimals, "ruler-label"), texts(decimals, "ruler-label")
    print("label options: OK")


def test_text_border():
    # The text border color is now always applied; no extra toggle required.
    root = run([
        "--id=box", "--unit=cm",
        "--text-border-color=0xff0000ff",
    ])
    style = css(root)
    assert "paint-order:stroke fill" in style
    assert "stroke:#ff0000" in style
    assert "stroke-width:2" in style
    assert all(e.get("stroke") == "#ff0000" for e in text_elements(root))

    legacy = run([
        "--id=box", "--unit=cm",
        "--halo-color=0x0000ffff",
    ])
    assert all(e.get("stroke") == "#0000ff" for e in text_elements(legacy))
    print("text border: OK (always applied, legacy alias works)")


def test_text_stroke_caps_joins():
    root = run(["--id=box", "--unit=px", "--show-labels=true"])
    labels = text_elements(root, "ruler-label")
    totals = text_elements(root, "ruler-total")
    assert labels and totals
    assert any(t.text == "0" for t in labels)
    assert any(t.text != "0" for t in labels)
    for elem in text_elements(root):
        assert elem.get("stroke-linecap") == "round", elem.attrib
        assert elem.get("stroke-linejoin") == "round", elem.attrib
    style = css(root)
    assert "stroke-linecap:round" in style
    assert "stroke-linejoin:round" in style
    assert all(line.get("stroke-linecap") == "square" for line in lines(root))
    print("text stroke caps/joins: OK (round for zero, numbers and totals)")


def test_presets():
    # Preset key -> (line color, text fill color, text border color).
    expected_colors = {
        "minimal": ("#888888", "#666666", "#f3f4f6"),
        "compact": ("#4b5563", "#374151", "#f9fafb"),
        "technical": ("#111827", "#374151", "#ffffff"),
        "blueprint": ("#ffffff", "#dbeafe", "#003366"),
        "high-contrast": ("#000000", "#ffffff", "#000000"),
        "export": ("#ffffff", "#fef3c7", "#000000"),
        "warm": ("#b45309", "#7c2d12", "#fff7ed"),
    }
    for preset, (line, text_fill, text_border) in expected_colors.items():
        root = inkscape_run(preset)
        style = css(root)
        assert "fill:%s;" % line in style, (preset, style)
        assert "stroke:%s;" % line in style, (preset, style)
        assert ".ruler-label { fill:%s;" % text_fill in style, (preset, style)
        assert "paint-order:stroke fill" in style, (preset, style)
        assert all(l.get("fill") == line and l.get("stroke") == line
                   for l in lines(root)), preset
        assert all(t.get("fill") == text_fill and t.get("stroke") == text_border
                   for t in text_elements(root)), preset
        # The deliberately edited GUI values must be replaced.
        assert "font-size:99px" not in style, (preset, style)
        assert "stroke-width:99" not in style, (preset, style)

    blueprint = inkscape_run("blueprint")
    assert "font-size:11px" in css(blueprint)
    assert "font-size:14px" in css(blueprint)
    assert {l.get("stroke-width") for l in lines(blueprint)} == {"1"}

    # Inkscape optiongroups return values, but accept displayed labels too.
    dark_export = inkscape_run("Dark export")
    assert "font-size:14px" in css(dark_export)
    assert all(t.get("stroke") == "#000000" for t in text_elements(dark_export))

    custom = inkscape_run("custom")
    assert "font-size:99px" in css(custom)
    assert {l.get("stroke") for l in lines(custom)} == {"#0000ff"}
    assert {t.get("stroke") for t in text_elements(custom)} == {"#00ff00"}
    print("presets: OK (all three colors and styles override GUI values)")


def test_generated_preset_inx():
    ruler_module = load_ruler_module()
    ids = set()
    for preset, values in ruler_module.PRESETS.items():
        path = HERE / ("ruler-%s.inx" % preset)
        assert path.is_file(), path
        root = ET.parse(path).getroot()
        assert root.findtext(INX_NS + "name").startswith(
            "Nastarxa Inkscape Ruler Extension - ")
        ext_id = root.findtext(INX_NS + "id")
        assert ext_id and ext_id not in ids, ext_id
        ids.add(ext_id)
        assert ext_id.startswith("nastarixa.inkscape.ruler_"), ext_id
        assert ext_id.endswith("_" + preset.replace("-", "_"))
        assert "fully restart Inkscape" in root.findtext(INX_NS + "description")
        tip = root.findtext(".//" + INX_NS + "menu-tip") or ""
        assert "restart Inkscape after install" in tip, tip

        presets = next(p for p in root.findall(".//" + INX_NS + "param")
                       if p.get("name") == "preset")
        options = presets.findall(INX_NS + "option")
        assert options[0].get("value") == preset
        assert options[0].get("default") == "true"

        params = {p.get("name"): p
                  for p in root.findall(".//" + INX_NS + "param")}
        for name, value in values.items():
            if name == "preset":
                continue
            param = params[name]
            if param.get("type") == "optiongroup":
                assert param.findall(INX_NS + "option")[0].get("value") == str(value)
            elif isinstance(value, float):
                assert param.text == "%g" % value, (preset, name, param.text)
            else:
                assert param.text == str(value), (preset, name, param.text)
    print("generated preset INX files: OK")


def _style_signature(group):
    result = []
    for elem in group.iter():
        tag = elem.tag.split("}")[-1]
        if tag in ("line", "text"):
            result.append((tag, elem.get("class"), elem.get("fill"),
                           elem.get("stroke"), elem.get("style")))
    return sorted(result, key=str)


def test_old_rulers_untouched():
    first = run(["--id=box", "--unit=cm",
                 "--line-color=0x000000ff", "--text-color=0x000000ff",
                 "--text-border-color=0xffffffff"])
    old = next(g for g in first.iter(SVG_NS + "g")
               if g.get("id") == "object-ruler-generated")
    before = _style_signature(old)
    first_svg = ET.tostring(first, encoding="unicode")

    second = run_svg(first_svg, [
        "--id=box", "--unit=cm", "--line-color=0xff0000ff",
        "--text-color=0x0000ffff", "--text-border-color=0x00ff00ff",
    ])
    groups = {g.get("id"): g for g in second.iter(SVG_NS + "g")}
    assert "object-ruler-generated" in groups
    assert "object-ruler-generated-2" in groups, sorted(groups)
    old_id = "object-ruler-generated"
    new_id = "object-ruler-generated-2"
    assert _style_signature(groups[old_id]) == before

    new = _style_signature(groups[new_id])
    assert all(fill == "#ff0000" and stroke == "#ff0000"
               for tag, cls, fill, stroke, style in new if tag == "line"), new
    assert all(fill == "#0000ff" and stroke == "#00ff00"
               for tag, cls, fill, stroke, style in new if tag == "text"), new

    # CSS must be scoped to the new group; otherwise global .ruler-line rules
    # repaint old rulers whose presentation attributes have lower priority.
    new_style = css(groups[new_id])
    selectors = [line.strip() for line in new_style.splitlines()
                 if line.strip().endswith("{")]
    assert selectors and all(("#" + new_id) in s for s in selectors), selectors
    assert all(("#" + old_id + " ") not in s for s in selectors), selectors

    assert groups[old_id].get(INK_LABEL) == "Object Ruler"
    assert groups[new_id].get(INK_LABEL) == "Object Ruler 2"
    assert groups["object-ruler-top-2"].get(INK_LABEL) == "Top Ruler 2"
    print("old rulers untouched: OK (unique ids, labels and scoped CSS)")


TINY_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <rect id="tiny" x="10" y="10" width="20" height="20"/>
</svg>
"""


def test_auto_fit():
    fitted = run_svg(TINY_SVG, ["--id=tiny", "--unit=mm", "--auto-fit=true"])
    plain = run_svg(TINY_SVG, ["--id=tiny", "--unit=mm", "--auto-fit=false"])
    assert "font-size:6px" in css(fitted), css(fitted)
    assert "font-size:12px" in css(plain), css(plain)
    print("auto fit: OK")


def test_inx_definition():
    root = ET.parse(HERE / "ruler.inx").getroot()
    assert root.findtext(INX_NS + "name") == (
        "Nastarxa Inkscape Ruler Extension")
    assert root.findtext(INX_NS + "id") == "nastarixa.inkscape.ruler"
    assert "fully restart Inkscape" in root.findtext(INX_NS + "description")
    tip = root.findtext(".//" + INX_NS + "menu-tip") or ""
    assert "restart Inkscape after install" in tip, tip
    names = {p.get("name") for p in root.findall(".//" + INX_NS + "param")}
    expected = {
        "show_top", "show_bottom", "show_left", "show_right", "origin",
        "tick_direction", "label_mode", "label_decimals",
        "preset", "line_width", "text_gap", "text_color",
        "text_border_color", "line_color",
        "label_font_size", "total_font_size",
    }
    assert expected <= names, names
    assert "line_border_color" not in names
    assert "text_halo" not in names
    labels = {p.get("name"): p.get("gui-text")
              for p in root.findall(".//" + INX_NS + "param")}
    assert labels["text_color"] == "Text fill color"
    assert labels["text_border_color"] == "Text border color"
    assert labels["line_color"] == "Line fill and border color"
    pages = root.findall(".//" + INX_NS + "page")
    appearance = next(p for p in pages if p.get("name") == "appearance")
    color_order = [p.get("name") for p in appearance.findall(INX_NS + "param")
                   if p.get("name") in ("text_color", "text_border_color",
                                        "line_color")]
    assert color_order == ["text_color", "text_border_color", "line_color"], (
        color_order)
    options = {o.get("value") for o in root.findall(".//" + INX_NS + "option")}
    assert {"minimal", "compact", "technical", "blueprint",
            "high-contrast", "export", "warm"} <= options, options
    print("inx definition: OK")


def test_inkscape_argument_order():
    root = run(["--id=box", "--unit=cm"], input_first=False)
    labels = totals(root)
    assert "7.56 cm" in labels and "18.9 cm" in labels, labels
    print("inkscape argument order: OK", labels)


def test_stdin_fallback():
    root = run_stdin(["--id=box", "--unit=cm"])
    labels = totals(root)
    assert "7.56 cm" in labels and "18.9 cm" in labels, labels
    print("stdin fallback: OK", labels)


def test_package_restart_notice():
    metadata = json.loads((HERE / "metadata.json").read_text(encoding="utf-8"))
    assert metadata.get("version") == "1.15"
    summary = metadata.get("summary") or ""
    assert "fully restart Inkscape" in summary, summary
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    assert "fully restart Inkscape" in readme
    print("package restart notice: OK")


def test_install_creates_package_subfolder():
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp) / "missing" / "inkscape" / "extensions"
        parent.mkdir(parents=True)
        (parent / "ruler.inx").write_text("<name>Object Ruler</name>", encoding="utf-8")
        (parent / "ruler.py").write_text("# Object Ruler", encoding="utf-8")
        (parent / "ruler-minimal.inx").write_text(
            "<name>Object Ruler - Minimal</name>", encoding="utf-8")
        (parent / "object-ruler.json").write_text(
            '{"name": "Object Ruler"}', encoding="utf-8")
        legacy = parent / "org.inkscape.effect.object_ruler"
        legacy.mkdir()
        (legacy / "ruler.inx").write_text(
            "<id>org.inkscape.effect.object_ruler</id><name>Object Ruler</name>",
            encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(HERE / "install_managed.py"), str(parent)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 0, proc.stderr

        target = parent / "nastarixa.inkscape.ruler"
        assert target.is_dir()
        assert (target / "ruler.inx").is_file()
        assert (target / "ruler.py").is_file()
        assert (target / "nastarixa.inkscape.ruler.json").is_file()
        assert not legacy.exists()
        for name in ("ruler.inx", "ruler.py", "ruler-minimal.inx",
                     "object-ruler.json"):
            assert not (parent / name).exists(), name
    print("install creates package subfolder: OK")


if __name__ == "__main__":
    test_cm()
    test_mm()
    test_inches()
    test_physical_document_curve_bbox()
    test_no_labels()
    test_ungrouped()
    test_selection_bbox_cases()
    test_extended_bbox_cases()
    test_square_caps()
    test_colors()
    test_same_line_width()
    test_font_sizes()
    test_text_gap()
    test_tick_hierarchy()
    test_separated_groups()
    test_side_selector()
    test_origin_center()
    test_origin_end()
    test_tick_direction()
    test_label_gap_all_sides()
    test_vertical_total_padding()
    test_label_options()
    test_text_border()
    test_text_stroke_caps_joins()
    test_presets()
    test_generated_preset_inx()
    test_old_rulers_untouched()
    test_auto_fit()
    test_inx_definition()
    test_inkscape_argument_order()
    test_stdin_fallback()
    test_package_restart_notice()
    test_install_creates_package_subfolder()
    print("All tests passed.")
