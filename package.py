"""Build an Extension-Manager-ready ZIP for Nastarxa Inkscape Ruler Extension.

The ZIP contains the .inx and .py files at the root (no enclosing folder),
which is the layout Inkscape's Extension Manager expects.
"""
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

HERE = Path(__file__).parent
OUT = HERE / "Nastarxa Inkscape Ruler.zip"

FILES = [
    "ruler.inx",
    "ruler.py",
    "README.md",
    "LICENSE.txt",
    "metadata.json",
] + sorted(p.name for p in HERE.glob("ruler-*.inx"))


def main():
    missing = [name for name in FILES if not (HERE / name).is_file()]
    if missing:
        raise SystemExit("Missing files: " + ", ".join(missing))

    metadata = json.loads((HERE / "metadata.json").read_text(encoding="utf-8"))
    listed = [name for name in FILES if name != "metadata.json"]
    if metadata.get("files") != listed:
        raise SystemExit(
            "metadata.json files list does not match the ZIP contents.\n"
            "Expected: " + ", ".join(listed)
        )

    with ZipFile(OUT, "w", ZIP_DEFLATED) as zf:
        for name in FILES:
            zf.write(HERE / name, arcname=name)

    print("Created", OUT)
    with ZipFile(OUT) as zf:
        for info in zf.infolist():
            print("  %-16s %6d bytes" % (info.filename, info.file_size))


if __name__ == "__main__":
    main()
