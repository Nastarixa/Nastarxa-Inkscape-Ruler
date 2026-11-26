# Changelog

## 1.15

- Fixed total labels in documents whose viewBox maps user units to physical
  units. A `210mm` page with `viewBox="0 0 210 297"` now reports one user unit
  as one millimetre instead of treating it as a CSS pixel.
- Fixed path bounding boxes: Bezier control handles are no longer counted as
  geometry. Curve extrema and elliptical arc extrema are measured instead, so
  `test.svg` now reports `19.299 x 66.764 mm`.
- Default labels now show three decimal places for millimetre-level detail.

## 1.14

- Package details now state that Inkscape must be fully restarted after
  installing. The note appears in the Extension Manager summary, INX
  descriptions, menu tips and README.
- Clarified that closing all Inkscape windows and reopening is required before
  the new menu entries become available.

## 1.13

- Extension INX id, preset ids and package metadata id are now
  `nastarixa.inkscape.ruler`, so Extension Manager creates the same folder name
  as the batch installers.
- Installers also remove legacy `org.inkscape.effect.object_ruler` folders.

## 1.12

- Label strokes now use round caps and round joins for zero labels, number
  labels and total labels. Ruler lines still use square caps.

## 1.11

- `Nastarxa Inkscape Ruler.zip` is now the single release package for Extension Manager.
- Fixed `metadata.json` so its file list matches the flat ZIP layout.
- Added a packaging check that fails if metadata and ZIP contents diverge.

## 1.10

- Expanded bounding-box detection to symbols, flow roots, foreign objects,
  arc paths and more Inkscape id formats.
- Bounding-box errors now report the ids and matching elements received.
- Removed bundled sample SVGs and the prebuilt ZIP; `package.py` builds the ZIP
  on demand and tests generate their own input.

## 1.9

- Renamed the extension to **Nastarxa Inkscape Ruler Extension**.
- Fixed bounding-box detection for Inkscape clones (`<use>`), images, groups
  containing them, and comma-separated selected ids.
- Reduced left/right rotated total-label padding to 2 px.
- Normalized source files to UTF-8 with LF line endings.
- Installers now create `%APPDATA%\inkscape\extensions` when it is missing.
- Managed install now uses the `nastarixa.inkscape.ruler` subfolder and removes
  older flat installs so menu entries do not duplicate.

## 1.8

- Reduced left/right total-label padding from 4 px.
- Rebuilt preset menu entries and package metadata.

## 1.7

- Added 8 px clearance for left/right total labels beyond number labels.
- Added a regression test for rotated total-label placement.

## 1.6

- Added extra clearance for bottom/right zero and number labels.
- Preserved configured text gap on top/left rulers.

## 1.5

- Generated rulers now receive unique ids and labels per run.
- CSS is scoped per generation so previous rulers are never restyled.
- Added preset menu entries as a refresh equivalent for plain INX dialogs.

## 1.0

- Initial Inkscape 1.x ruler extension with mm/cm/pt/pc/in/px units,
  four-side selection, presets, colors and grouping.
