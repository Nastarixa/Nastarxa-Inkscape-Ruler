# Nastarxa Inkscape Ruler Extension

Version 1.11 — tested with Inkscape 1.4.4.

Draw configurable measuring rulers around the bounding box of a selected object.
Rulers can be placed on any combination of the **top**, **bottom**, **left** and
**right** sides. Horizontal and vertical rulers are emitted as separate SVG
groups, so they can be selected, hidden or restyled independently. Output is
plain SVG that stays editable and exports cleanly to PNG or PDF.

## Features

- Units: `mm`, `cm`, `pt`, `pc`, `in`, `px`
- Independent top, bottom, left and right rulers
- Three dialog pages: **Measurement**, **Appearance**, **Object**
- Style presets that visibly set every appearance value, including all colors
- **Line fill and border color** controls both `fill` and `stroke` on ruler lines
- **Text fill color** and always-applied **Text border color**
- Square line caps and one shared **Line width** for every line and tick
- Independent **Label font size** and **Total label font size**
- Bottom/right labels get extra clearance; left/right rotated totals keep a
  2 px gap beyond the widest number label
- New runs create a new ruler only; existing rulers keep their ids, labels,
  geometry and styling
- Bounding boxes work for shapes, groups, paths, text, images, Inkscape clones,
  symbols, flow roots, foreign objects and multiple selected ids

## Install

### Single ZIP via Extension Manager

`Nastarxa Inkscape Ruler.zip` is the only file you need to release or download.

1. Open **Extensions → Manage Extensions**.
2. Choose **Install from file**.
3. Select `Nastarxa Inkscape Ruler.zip`.
4. Restart Inkscape.
5. Use **Extensions → Ruler Tools → Nastarxa Inkscape Ruler Extension**.

The ZIP contains every `.inx` file, the script, README, license and
`metadata.json` at its root. The metadata file list matches those contents, so
the manager can register and later uninstall the package.

### Inkscape 1.4.4 note

Inkscape 1.4.4 can misplace files when a ZIP is selected from an arbitrary
folder. If that happens, copy `Nastarxa Inkscape Ruler.zip` into your extensions folder
first, then install it from there:

```text
%APPDATA%\inkscape\extensions
```

The one-click installer below is a fully reliable alternative.

### One-click installer (Windows)

1. Close **all** Inkscape windows.
2. Double-click `install.bat` (or `install_managed.bat`).
3. Reopen Inkscape.
4. Use **Extensions → Ruler Tools → Nastarxa Inkscape Ruler Extension**.

Files are installed into a dedicated package folder:

```text
%APPDATA%\inkscape\extensions\nastarixa.inkscape.ruler
```

The folder is created automatically. Older flat installs are removed, so the
extension is not registered twice.

Command-line equivalents:

```powershell
python install_managed.py
python install_managed.py "D:\path\to\extensions"
```

The second form installs into `D:\path\to\extensions\nastarixa.inkscape.ruler`.
Passing the exact package folder also works.

### Linux and macOS

Run the installer from the repository folder:

```sh
python install_managed.py
```

Default locations:

- Linux: `~/.config/inkscape/extensions/nastarixa.inkscape.ruler`
- macOS: `~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/nastarixa.inkscape.ruler`

### Troubleshooting

Run `diagnose.bat` (or `python diagnose.py`) to print the expected install
folder, all matching INX files, their ids/submenus and package metadata.

If the menu item is missing:

1. Fully restart Inkscape.
2. In **Extensions → Manage Extensions**, confirm the extension is enabled.
3. Run `install.bat` again.
4. Send the `diagnose.bat` output if it still does not appear.

If you get a bounding-box error, the full message includes **Ids received** and
**Matching elements**. Send that text, or the selected object's XML from
Inkscape's XML editor.

## Usage

1. Draw or select an object, or several objects.
2. Open **Extensions → Ruler Tools → Nastarxa Inkscape Ruler Extension**.
   For a specific look, choose a preset entry such as **Nastarxa Inkscape Ruler
   Extension – Minimal** or **– Blueprint**. Each preset entry opens with its
   Appearance values already loaded.
3. Use the dialog tabs:

   - **Measurement** — unit, enabled sides, zero point, minor ticks, label mode
     and decimals
   - **Appearance** — style preset, colors, object gap, tick lengths, font
     sizes, line width, text gap and tick direction
   - **Object** — group the new ruler with the selected object

4. Click **Apply**. The object and new ruler are grouped and ready to export.

Plain INX dialogs cannot refresh other widgets when **Style preset** changes.
Changing the combo still affects the next ruler, but the visible fields keep
their old values. Use a preset menu entry when you want the whole Appearance
tab visibly refreshed.

## How rulers are drawn

- Enabled sides are grouped as `object-ruler-top`, `object-ruler-bottom`,
  `object-ruler-left` and `object-ruler-right`. Horizontal and vertical rulers
  are also wrapped in `object-ruler-horizontal` and `object-ruler-vertical`.
- Each run gets unique generated ids/labels such as `object-ruler-generated-2`
  and **Object Ruler 2**. These legacy SVG labels are kept deliberately for
  compatibility; only the extension's display name changed.
- CSS is scoped to the new generated id, so old rulers are never restyled.
- Selecting multiple objects measures their combined bounding box.
- **Zero point** can be top/left, center or bottom/right. Center/end origins
  produce negative values before the origin.
- Ticks point **outward** or **inward**. Start/end ticks are long, multiples of
  five units are medium, single units are small and subdivisions are shortest.
- **Auto-shrink for small objects** reduces font sizes, gaps and tick lengths so
  labels stay readable on tiny objects.
- **Label decimals** forces a fixed number of decimals. Use `-1` for automatic
  precision, or **Zero and total only** for a cleaner ruler.

## Development

```powershell
python test_ruler.py
python generate_preset_inx.py
python ruler.py <input.svg> --id=box --unit=cm --output=out.svg
python package.py
```

`--output=...` writes UTF-8/LF bytes directly. Avoid PowerShell `>` redirection:
on Windows it can write UTF-16, which Inkscape cannot read reliably.

Inkscape 1.4 runs the script as:

```text
python ruler.py --id=box --unit=cm <temporary-input.svg>
```

Stdin is supported as a fallback for standalone use. The extension uses only
the Python standard library.

## Repository files

- `ruler.inx` — dialog definition
- `ruler-*.inx` — generated preset menu entries
- `ruler.py` — extension script
- `generate_preset_inx.py` — regenerates preset INX files
- `install.bat`, `install_managed.bat`, `install_managed.py` — installers
- `diagnose.bat`, `diagnose.py` — installation diagnostics
- `Nastarxa Inkscape Ruler.zip` — single release package for Extension Manager
- `package.bat`, `package.py` — rebuild `Nastarxa Inkscape Ruler.zip`
- `metadata.json` — Extension Manager metadata
- `test_ruler.py` — smoke tests
- `CHANGELOG.md` — release history
- `LICENSE.txt` — MIT license

## License

MIT. See [LICENSE.txt](LICENSE.txt).
