# Sanzo Wada Colors

[![Blender](https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmttfntn%2Fsanzo-wada-colors-blender%2Fmain%2Fsanzo_wada_colors%2Fblender_manifest.toml&query=%24.blender_version_min&label=Blender&color=E87D0D&logo=blender&logoColor=white)](https://www.blender.org/download/)
[![Release](https://img.shields.io/github/v/release/mttfntn/sanzo-wada-colors-blender)](https://github.com/mttfntn/sanzo-wada-colors-blender/releases/latest)
[![Tests](https://github.com/mttfntn/sanzo-wada-colors-blender/actions/workflows/ci.yml/badge.svg)](https://github.com/mttfntn/sanzo-wada-colors-blender/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/mttfntn/sanzo-wada-colors-blender)](LICENSE)
[![Language](https://img.shields.io/github/languages/top/mttfntn/sanzo-wada-colors-blender)](sanzo_wada_colors/__init__.py)
[![Color data](https://img.shields.io/badge/color%20data-dblodorn%2Fsanzo--wada-8a5cf6)](https://github.com/dblodorn/sanzo-wada)

A Blender 5.3 add-on that puts the 159 colors and 348 combinations of
**Sanzo Wada's *A Dictionary of Color Combinations*** in the Shader Editor
sidebar (**N › Sanzo Wada**). Turn them into RGB nodes, palette frames, Color
Ramps and Blender palettes, recolor selected nodes, or drag a swatch onto any
color field. Works with **Cycles, EEVEE and Octane**. The color library is a
local JSON file, so nothing is downloaded while you work.

For maintainers: [HANDOVER.md](HANDOVER.md) (people) and [AGENTS.md](AGENTS.md)
(AI assistants).

## Using it

Open a material (or a world) in the Shader Editor and press **N**, then pick
the **Sanzo Wada** tab.

```
Sanzo Wada Colors
159 colors · 348 combinations          [⟳]
[  Auto  | Cycles/EEVEE |  Octane  ]
Nodes for: Cycles / EEVEE
Drag a swatch onto any color field
┌──────────────────────────────────────┐
│ ■ 1  Hermosa Pink           #ffb3f0  │
│ ■ 2  Corinthian Pink        #ffa6d9  │
│ …                         (search ▾) │
└──────────────────────────────────────┘
[■■■■■■■■■■■■ big swatch ■■■■■■■■■■■■]
1 · Hermosa Pink
#ffb3f0 [copy]   R:255 / G:179 / B:240
[+ Add RGB Node] [Apply to Selected Nodes]
Used in 3 combinations: [176] [227] [273]

Combinations
[◀] Combination 176 [▶] [⟳]
[■■■■■■■■|■■■■■■■■|■■■■■■■■]
[Add Palette Nodes] [Add Color Ramp]
[Distribute to Selected] [Create Palette]
```

**Colors panel**

- **List:** every color with its swatch, number, name and hex. The search
  field (▾ under the list) matches number, name or hex.
- **Drag and drop:** drag any swatch (in the list, the big preview or the
  combination strip) onto a color field: a node socket, Base Color in the
  material properties, the world color, a paint color. Blender converts the
  color for the field, so it matches the book's hex. Clicking a swatch opens a
  picker, but the library colors can't be changed.
- **Add RGB Node** adds a node with the color, named after it and with its
  header tinted in it, in the middle of the view.
- **Apply to Selected Nodes** sets the color on the selected nodes (or the
  active one): RGB nodes get it as their value, other nodes in their first
  free color input (for example Principled **Base Color**). Linked, hidden and
  disabled inputs are skipped.
- **Used in … combinations:** click a number to show that combination.

**Combinations panel**

- Step through combinations with ◀ ▶, type a number, or ⟳ for a random one.
  The strip shows its colors; the arrow button next to a name shows that color
  in the list.
- **Add Palette Nodes:** a frame named *Sanzo Wada · Combination N* with one
  RGB node per color.
- **Add Color Ramp:** one stop per color, with **Constant** (hard bands,
  default), **Linear** or **Ease** interpolation: change it right after
  adding, in the Adjust Last Operation panel (F9).
- **Distribute to Selected:** gives the selected nodes the combination's
  colors in order: column by column from the left, top to bottom in each
  column, starting again from the first color when there are more nodes.
- **Create Palette:** a Blender palette *Sanzo Wada NNN* for paint modes
  (rebuilt, not duplicated, if it already exists).

## Cycles, EEVEE and Octane

The switch at the top chooses which nodes are created:

- **Auto** (default): Octane nodes when the scene renders with Octane,
  otherwise Blender's nodes (used by both Cycles and EEVEE).
- **Cycles/EEVEE** or **Octane:** always that one. If Octane is chosen but not
  installed, the panel says *Octane not found* and Blender nodes are made.

With Octane, **Add RGB Node** and **Add Palette Nodes** make Octane *RGB
Color* nodes. **Apply** and **Distribute** work on Octane nodes too: the color
is written in the color space each input expects. **Add Color Ramp** uses
Octane's gradient node only if it exposes an editable ramp; otherwise it adds
a Blender Color Ramp and tells you.

If your OctaneBlender build names its nodes differently, set the names in
Preferences › Add-ons › Sanzo Wada Colors › **Octane** (it also shows whether
Octane's nodes were found).

## Your own color library

Preferences › Add-ons › Sanzo Wada Colors › **Color Library JSON** can point
to another local file in the same format: `{"colors": [...]}` or a plain list,
where each color has `index` and `hex` (or `rgb_array`), and optionally
`name`, `rgb`, `cmyk`, `combinations` (combination numbers) and `use_count`.
Leave it empty to use the bundled library. The panel shows the error if the
file can't be read.

## Install

Requires **Blender 5.3**.

1. Download `sanzo_wada_colors-<version>.zip` from the
   [latest release](https://github.com/mttfntn/sanzo-wada-colors-blender/releases/latest).
2. In Blender: Edit › Preferences › Get Extensions › ▾ (top right) ›
   **Install from Disk...**, pick the zip. It is enabled right away.

Installing a newer zip replaces the old version.

## Uninstall

Preferences › Get Extensions (or Add-ons), find Sanzo Wada Colors, ▾ ›
**Uninstall**. Nodes, ramps and palettes you created stay in your files.

## Known limits

- **Octane** support is written against Octane's node and socket layout but
  was tested with a stand-in node, not with OctaneBlender itself. Octane
  gradient nodes get their stops in linear color, like Blender's Color Ramp.
- **Drag and drop** relies on Blender's own swatch dragging; it is checked
  by hand, not by the automated tests.
- The panels appear in the Shader Editor only (not in Geometry Nodes or the
  Compositor).
- New nodes are placed in the middle of the view, not at the mouse.
- The library is read when the add-on starts and when you press ⟳ or change
  the JSON path: edits to the JSON file need a ⟳.

## Credits

- Colors and combinations: Sanzo Wada, *A Dictionary of Color Combinations*
  (*Haishoku Sōkan*, 1933–34).
- Color data: the [Sanzo Wada project](https://github.com/dblodorn/sanzo-wada)
  by Dain Blodorn ([JSON API](https://sanzo-wada.dmbk.io/assets/colors.json)),
  MIT License. Its notice ships with the add-on as
  `sanzo_wada_colors/colors.LICENSE`.

## Development

See [HANDOVER.md](HANDOVER.md) for the code layout, tests and releases.

## Contributing

Bug reports, ideas and pull requests are welcome: see
[CONTRIBUTING.md](CONTRIBUTING.md). Open an issue with one of the
[forms](https://github.com/mttfntn/sanzo-wada-colors-blender/issues/new/choose); report security problems privately as described
in [SECURITY.md](SECURITY.md).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). © 2026 Matteo Fontana. The bundled
color data is MIT-licensed (see Credits).
