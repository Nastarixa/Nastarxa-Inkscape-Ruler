"""Check where Nastarxa Inkscape Ruler Extension is installed and why it may not appear in the menu.

Usage:
    python diagnose.py [extensions_folder]
"""
import json
import os
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"i": "http://www.inkscape.org/namespace/inkscape/extension"}
PACKAGE_DIR_NAME = "nastarixa.inkscape.ruler"


def default_extensions_dir():
    if os.name == "nt":
        appdata = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "inkscape" / "extensions"
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" /
                "org.inkscape.Inkscape" / "config" / "inkscape" / "extensions")
    return Path.home() / ".config" / "inkscape" / "extensions"


def main():
    target = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else default_extensions_dir()
    expected = target if target.name == PACKAGE_DIR_NAME else target / PACKAGE_DIR_NAME
    print("Extensions folder:", target)
    print("Expected install folder:", expected)
    print("Expected folder exists:", expected.is_dir())
    if not target.is_dir():
        return

    inx_files = sorted(set(target.rglob("ruler.inx")) |
                       set(target.rglob("ruler-*.inx")))
    print("\nNastarxa Inkscape Ruler INX files found:", len(inx_files))
    for inx in inx_files:
        print("  ", inx)
        try:
            root = ET.parse(inx).getroot()
        except ET.ParseError as exc:
            print("    INVALID XML:", exc)
            continue
        name = root.findtext("i:name", namespaces=NS)
        ident = root.findtext("i:id", namespaces=NS)
        node = root.find("i:effect/i:effects-menu/i:submenu", NS)
        submenu = node.get("name") if node is not None else None
        command = root.findtext("i:script/i:command", namespaces=NS)
        print("    name:", name, "| id:", ident, "| submenu:", submenu)
        print("    script:", command,
              "| found:", bool(command and (inx.parent / command).is_file()))

    print("\nPackage metadata files mentioning object ruler:")
    for path in sorted(target.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "ruler" in json.dumps(data).lower():
            print("  ", path, "->", data.get("name"), "| files:", data.get("files"))

    print("\nIf the INX files were found but the menu is missing:")
    print("  1. Close ALL Inkscape windows and reopen Inkscape (a full restart).")
    print("  2. In Extensions -> Manage Extensions, check the extension is enabled.")
    print("  3. Look for the top-level submenu 'Ruler Tools' in the Extensions menu.")
    print("  4. If still missing, run: python install_managed.py")


if __name__ == "__main__":
    main()
