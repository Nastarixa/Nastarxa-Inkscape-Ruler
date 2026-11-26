"""Install Nastarxa Inkscape Ruler Extension as a managed Inkscape extension.

Inkscape 1.4.4's Extension Manager has a bug: choosing a local ZIP writes the
files outside the extensions folder and saves invalid package metadata, so the
install appears to be ignored. This script performs the same installation the
manager *should* do, including the metadata file the manager needs in order to
list and uninstall the extension.

Files are installed in a dedicated subfolder:

    <extensions folder>/nastarixa.inkscape.ruler

Usage:
    python install_managed.py [extensions_folder]
"""
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
PACKAGE_DIR_NAME = "nastarixa.inkscape.ruler"
FILES = (["ruler.inx", "ruler.py", "README.md", "LICENSE.txt"] +
         sorted(p.name for p in HERE.glob("ruler-*.inx")))
METADATA_NAME = "object-ruler.json"
MARKERS = ("Nastarxa Inkscape Ruler Extension", "Object Ruler",
           "org.inkscape.effect.object_ruler")


def base_extensions_dir():
    if os.name == "nt":  # Windows
        appdata = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "inkscape" / "extensions"
    if sys.platform == "darwin":  # macOS
        return (Path.home() / "Library" / "Application Support" /
                "org.inkscape.Inkscape" / "config" / "inkscape" / "extensions")
    return Path.home() / ".config" / "inkscape" / "extensions"  # Linux


def default_install_dir():
    return base_extensions_dir() / PACKAGE_DIR_NAME


def install_dir(value):
    """Treat the argument as the extensions folder unless it is already the target."""
    path = Path(value).expanduser()
    if path.name != PACKAGE_DIR_NAME:
        path = path / PACKAGE_DIR_NAME
    return path


def _contains_marker(path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return any(marker in text for marker in MARKERS)


def _matches_source(path, name):
    try:
        return path.read_bytes() == (HERE / name).read_bytes()
    except OSError:
        return False


def _unlink(path):
    try:
        path.unlink()
    except OSError:
        pass


def remove_old_flat_install(target):
    """Delete older flat installs from the parent extensions folder."""
    parent = target.parent
    for name in ("ruler.inx", "ruler.py", METADATA_NAME):
        path = parent / name
        if path.is_file() and _contains_marker(path):
            _unlink(path)
    for path in parent.glob("ruler-*.inx"):
        if _contains_marker(path):
            _unlink(path)
    # README/LICENSE are generic names, so only remove exact copies of ours.
    for name in ("README.md", "LICENSE.txt"):
        path = parent / name
        if path.is_file() and _matches_source(path, name):
            _unlink(path)


def remove_old_subfolder_install(target):
    """Remove a legacy object-ruler subfolder so the menu is not duplicated."""
    old = target.parent / "object-ruler"
    if not old.is_dir():
        return
    for name in FILES + ["metadata.json", "info.json"]:
        path = old / name
        if path.is_file():
            _unlink(path)
    for path in old.glob("ruler-*.inx"):
        _unlink(path)
    try:
        old.rmdir()
    except OSError:
        pass  # leave unrelated files alone


def remove_stale_generated(target):
    """Drop preset INX files from older versions before copying fresh ones."""
    for path in target.glob("ruler-*.inx"):
        _unlink(path)


def main():
    target = install_dir(sys.argv[1]) if len(sys.argv) > 1 else default_install_dir()

    if not target.is_dir():
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SystemExit(
                "Could not create extensions folder: %s\n%s\n"
                "Pass a writable folder as an argument." % (target, exc)
            )

    remove_old_flat_install(target)
    remove_old_subfolder_install(target)
    remove_stale_generated(target)

    for name in FILES:
        src = HERE / name
        if not src.is_file():
            raise SystemExit("Missing source file: " + str(src))
        shutil.copy2(src, target / name)

    # The Extension Manager reads any *.json file in the extensions tree
    # (except package.json). File paths are relative to the JSON file's folder.
    metadata = json.loads((HERE / "metadata.json").read_text(encoding="utf-8"))
    metadata["files"] = list(FILES)
    (target / METADATA_NAME).write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    print("Installed Nastarxa Inkscape Ruler Extension to:", target)
    for name in FILES + [METADATA_NAME]:
        print("  " + str(target / name))
    print("Restart Inkscape, then use:")
    print("  Extensions -> Ruler Tools -> Nastarxa Inkscape Ruler Extension")
    print("It will also appear in Extensions -> Manage Extensions.")


if __name__ == "__main__":
    main()
