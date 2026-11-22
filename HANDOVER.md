# Handover: Sanzo Wada Colors

## What it is

A Blender 5.3 extension that shows the 159 colors and 348 combinations of
Sanzo Wada's *A Dictionary of Color Combinations* in the Shader Editor sidebar
(N › Sanzo Wada). From there users add RGB nodes, palette frames, Color Ramps
and Blender palettes, recolor selected nodes, and drag swatches onto any color
field. It can create Blender nodes (Cycles/EEVEE) or Octane nodes.

It is not a fork: there is no upstream code. The color data (`colors.json`)
comes from the MIT-licensed [Sanzo Wada project](https://github.com/dblodorn/sanzo-wada)
by Dain Blodorn, downloaded once from <https://sanzo-wada.dmbk.io/assets/colors.json>
and bundled; the add-on never goes online. Author: Matteo Fontana.
Repository: <https://github.com/mttfntn/sanzo-wada-colors-blender> (public).

## What you need

- **Blender 5.3**, the only supported version (manifest `blender_version_min`
  5.3.0, `blender_version_max` 5.4.0, which is exclusive). The code relies on
  `Node.location_absolute`, `NodeTree.view_center` and `NodeSocket.enabled`
  without fallbacks.
- **Python 3.11+** (for `tomllib`) to run `tests/run_blender.py`,
  `tests/compare_probes.py` and `tools/build_package.py`. The add-on itself
  only uses Blender's Python.
- `gh` (GitHub CLI) only for release work.
- Optional, for development only: the Blender MCP (`.mcp.json`, git-ignored)
  lets an AI assistant drive a Blender on port 9876. It is not part of the
  add-on.

## How the code is organized

| File | What it holds |
|---|---|
| `sanzo_wada_colors/__init__.py` | The whole add-on (one module, sections in this order): library loading (`load_library`, `reload_library`, `_DB`), the UI-list mirror (`sync_window_managers`), node helpers (`make_rgb_node`, `make_combo_frame`, `make_color_ramp`, `set_node_color`), renderer choice (`octane_available`, `octane_requested`, `use_octane`), properties (`SANZO_PG_color`, `SANZO_AddonPreferences`), 10 operators, the UI list and 2 panels, registration (`_on_load_post`, `_deferred_init`). |
| `sanzo_wada_colors/colors.json` | The color library (159 colors). |
| `sanzo_wada_colors/colors.LICENSE` | MIT notice for `colors.json`. Must ship with it. |
| `sanzo_wada_colors/blender_manifest.toml` | Extension manifest (id, version, supported Blender, license, permissions). |
| `tests/run_blender.py` | Starts headless Blender with a throwaway profile containing the add-on, and runs a script in it. |
| `tests/test_sanzo.py` | The test suite (177 checks). |
| `tests/probe_behaviour.py`, `tests/compare_probes.py` | Old/new behaviour comparison. |
| `tests/check_installed_package.py` | Checks a built zip after installing it in a scratch profile. |
| `tools/build_package.py` | Builds `dist/sanzo_wada_colors-<version>.zip` (adds LICENSE). |
| `.github/workflows/ci.yml` | Tests, build, install check; on a `v*` tag also the release. |

## How the main feature works

1. **Library.** `load_library()` reads `library_path()` (the preference
   `json_path`, else the bundled file) into the module-level `_DB`:
   `colors` (dicts sorted by index, with `srgb` floats), `by_index`,
   `position` (index → position in `colors`) and `combos` (combination number
   → color indices, ascending). Combinations are rebuilt from each color's
   `combinations` list. `reload_library()` catches any error, empties the
   library and keeps the message in `_DB["error"]` for the panels.
2. **The UI list.** A `UIList` needs an RNA collection, so
   `sync_window_managers()` mirrors `_DB` into `WindowManager.sanzo_colors`
   (`SANZO_PG_color`: `idx`, `label`, `hex`, and `name` = "NNN Name #hex",
   which the list's built-in search filters). WindowManager properties are not
   saved in .blend files (tested), so the list is refilled after every file
   load (`_on_load_post`) and once after registration (`_deferred_init`, a
   timer, because `bpy.data` is restricted inside `register()`).
3. **Swatches and drag and drop.** `SANZO_PG_color.color` is a
   `COLOR_GAMMA` property with a getter (the library's sRGB value) and a setter
   that ignores writes. The setter matters: a read-only property is drawn as a
   disabled button, and disabled buttons can't be dragged. Blender converts
   sRGB to linear when a swatch is dropped on a linear color field.
4. **Colors in nodes.** Blender's node colors are scene-linear, so
   `linear_rgba()` converts with the sRGB transfer function (matches Blender's
   own conversion to 1e-3). `set_node_color()` writes an RGB node's output,
   else the first free (unlinked, visible, enabled) color input, else a color
   property on the node. `_write_socket` / `_color_value` read the target's
   RNA subtype: `COLOR` gets linear values, `COLOR_GAMMA` gets sRGB, and the
   array length (3 or 4) is respected. That is what lets Octane's Python
   sockets work without hard-coding them.
5. **Renderer choice.** `octane_requested()` = target Octane, or Auto with the
   scene engine `'octane'`. `use_octane()` = requested **and**
   `octane_available()` (the node type named in the preferences exists, as a
   C type or a Python-registered node). The panel shows which nodes will be
   made, and says *Octane not found* when it was requested but is missing.
6. **Operators** run on `space_data.edit_tree` (poll: Shader Editor with a
   tree). New nodes go to `tree.view_center`, placed with
   `location_absolute` so nodes inside frames are right.

## How to make a change

1. Read the relevant section of `__init__.py` and its tests.
2. Change the code. For operators, panels and lists, put the tooltip in
   `bl_description` and internal notes in `#` comments (class docstrings
   become tooltips).
3. Add or update checks in `tests/test_sanzo.py`. A bug fix needs a check
   that fails without it.
4. Run both test modes, and the old/new comparison if behaviour could change
   (next section).
5. Update the README if users will notice the change.

## How to run the tests

From the repo root (macOS shown; elsewhere pass `--blender PATH` or set `BLENDER`):

```
python3 tests/run_blender.py              # loaded as an extension
python3 tests/run_blender.py --legacy     # loaded as a legacy add-on
```

Each ends with `177 checks, 0 failed` and exits 1 on any failure. Blender runs
with `--background --factory-startup` and every `BLENDER_USER_*` folder inside
a temporary profile, so your real profile and open sessions are never touched.
There is no window in background mode, so operators are run through their
`execute()` with a fake Shader Editor context, panels are drawn into a fake
layout that validates every property and operator name, and Octane is
replaced by a mock node with a Python `COLOR_GAMMA` socket.

**Old/new comparison:**

```
git worktree add /tmp/sw_old HEAD                     # or any older commit
python3 tests/run_blender.py --addon-root /tmp/sw_old tests/probe_behaviour.py -- old.json
python3 tests/run_blender.py tests/probe_behaviour.py -- new.json
python3 tests/compare_probes.py old.json new.json     # "0 difference(s)" when nothing changed
```

The probe is seeded, so two runs of the same code give 0 differences (checked:
97,835 recorded values). It covers every color, every combination in every
ramp mode, applying a color to all 105 Blender shader node types, distribute
layouts, browsing, palettes, panel output and custom/broken library files.

**Built package:**

```
python3 tools/build_package.py
export BLENDER_USER_RESOURCES=/tmp/swp BLENDER_USER_CONFIG=/tmp/swp/config BLENDER_USER_SCRIPTS=/tmp/swp/scripts BLENDER_USER_EXTENSIONS=/tmp/swp/extensions
blender -b --factory-startup --command extension install-file --repo user_default --enable dist/sanzo_wada_colors-*.zip
blender -b --python-exit-code 1 --python tests/check_installed_package.py    # "PROBLEMS: none"
```

CI runs all of this except the comparison, on Linux with Blender 5.3.0.

## How to make a release

1. Bump `version` in `sanzo_wada_colors/blender_manifest.toml`. The README
   badges are live (shields.io and GitHub), so never hard-code a version in
   them. The download-size badge reads `.github/release-size.json` on `main`; after each release CI updates it with a bot commit on `main`, so pull before your next change.
2. Run the tests, commit, push to `main` and wait for green CI.
3. Create an **annotated** tag; its message becomes the release notes:
   `git tag -a v1.2.3 -m "Sanzo Wada Colors 1.2.3" -m "- what changed"`, then
   `git push origin v1.2.3`.
4. CI checks that the tag matches the manifest version, then tests, builds and
   publishes the GitHub release with the zip attached.
5. Install the new zip in your Blender (README › Install).

## Bringing in updates from the original project

There is no upstream code. To refresh the **color data**:

1. Download <https://sanzo-wada.dmbk.io/assets/colors.json> into a new empty
   folder (it is generated by `apps/sanzo-wada-beta` in dblodorn/sanzo-wada).
2. Check it parses with the same fields (`index`, `name`, `hex`,
   `rgb_array`, `cmyk`, `rgb`, `combinations`, `use_count`).
3. Replace `sanzo_wada_colors/colors.json`, run the tests (counts are asserted:
   update them on purpose if the data grew) and the probe comparison; every
   difference should be data.
4. Keep `colors.LICENSE` in step with the upstream LICENSE.

Note: the upstream repository's older `apps/sanzo-wada-alpha/assets/colors.json`
has only 157 colors; the bundled file (from the JSON API) has 159.

## Things to know

- **WindowManager data is runtime only.** That is on purpose: nothing about
  the library ends up in users' .blend files. It is why `_on_load_post` exists.
- **Read-only swatches can't be dragged.** Keep the no-op setter on
  `SANZO_PG_color.color`.
- **Linear vs sRGB.** Node sockets (`COLOR`) want linear; swatches,
  `Node.color` (header tint) and palettes are sRGB. `_color_value` picks from
  the target's subtype; don't write `srgb` values into sockets directly.
- **Octane is untested against the real plugin.** The defaults are the node
  ids `OctaneRGBColor` and `OctaneGradientMap`, editable in the preferences.
  If an Octane user reports a problem, ask for the node's `bl_idname` and its
  color socket's `bl_rna.properties["default_value"]` subtype.
- **`_DB["position"]`** is valid for the WindowManager collection because
  `sync_window_managers` adds items in `_DB["colors"]` order; the
  Combinations panel still checks `coll[p].idx == i` before using it.
- **Draw cost:** Colors panel ≈0.012 ms, Combinations panel ≈0.012 ms per
  draw (headless, measured with a no-op layout).
- **The id `sanzo_wada_colors` must never change.** Installed copies would
  stop upgrading in place.

## Known limits

- Octane: tested with a mock only (see above). Gradient stops are written as
  linear colors.
- Drag and drop is Blender's own; it is verified by hand, not by the tests.
- Panels only in the Shader Editor. New nodes go to the view center, not the
  mouse.
- A library JSON with a missing `index` reports a bare `'index'` error.
- If two colors in a custom library share an `index`, lookups use the last one.
