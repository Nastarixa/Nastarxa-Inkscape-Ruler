"""Generate one INX menu entry per style preset.

Plain INX dialogs cannot refresh other widgets when an optiongroup changes.
Each generated menu entry therefore opens with all Appearance values already
set to that preset, which is the practical equivalent of a refresh button.
"""
import copy
import importlib.util
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).parent
EXTENSION_NAME = "Nastarxa Inkscape Ruler Extension"
NS = "http://www.inkscape.org/namespace/inkscape/extension"
INK = "{%s}" % NS
ET.register_namespace("", NS)


def q(tag):
    return INK + tag


def load_presets():
    spec = importlib.util.spec_from_file_location("ruler_defaults", HERE / "ruler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PRESETS


def inx_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "%g" % value
    return str(value)


def choose_option(param, value):
    """Put the desired option first so Inkscape 1.4 selects it by default."""
    options = param.findall(q("option"))
    wanted = str(value)
    chosen = next((o for o in options if o.get("value") == wanted), None)
    if chosen is None:
        return
    for option in options:
        option.attrib.pop("default", None)
    param.remove(chosen)
    param.insert(0, chosen)
    chosen.set("default", "true")


def generate():
    base = ET.parse(HERE / "ruler.inx").getroot()
    presets = load_presets()
    # ruler.py registers the SVG namespace as the default; restore INX here.
    ET.register_namespace("", NS)

    preset_param = next(p for p in base.iter(q("param"))
                        if p.get("name") == "preset")
    labels = {o.get("value"): (o.text or o.get("value"))
              for o in preset_param.findall(q("option"))}

    written = []
    for key, values in presets.items():
        root = copy.deepcopy(base)
        label = labels.get(key, key.replace("-", " ").title())

        root.find(q("name")).text = EXTENSION_NAME + " - " + label
        root.find(q("id")).text = (
            "org.inkscape.effect.object_ruler_" + key.replace("-", "_"))
        root.find(q("description")).text = (
            "Draw measuring rulers using the %s style." % label)
        tip = root.find(".//" + q("menu-tip"))
        if tip is not None:
            tip.text = "Draw rulers using the %s preset" % label

        for param in root.iter(q("param")):
            name = param.get("name")
            if name == "preset":
                choose_option(param, key)
            elif name in values:
                if param.get("type") == "optiongroup":
                    choose_option(param, values[name])
                else:
                    param.text = inx_value(values[name])

        if hasattr(ET, "indent"):
            ET.indent(root, space="  ")
        output = HERE / ("ruler-%s.inx" % key)
        output.write_bytes(
            ('<?xml version="1.0" encoding="UTF-8"?>\n' +
             ET.tostring(root, encoding="unicode")).encode("utf-8")
        )
        written.append(output.name)

    print("Generated:", ", ".join(written))


if __name__ == "__main__":
    generate()
