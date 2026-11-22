# AGENTS.md: Sanzo Wada Colors

Blender 5.3 extension. Shader Editor sidebar (N › Sanzo Wada) with the 159 colors and 348
combinations of Sanzo Wada's *A Dictionary of Color Combinations* from a bundled local JSON:
RGB nodes, palette frames, Color Ramps, palettes, recoloring selected nodes, draggable swatches,
Blender (Cycles/EEVEE) or Octane nodes. Humans: see HANDOVER.md.

## Commands (repo root; macOS Blender is found automatically, else `--blender PATH` / `BLENDER=`)

```
python3 tests/run_blender.py                       # 177 checks, must end "0 failed" (extension load)
python3 tests/run_blender.py --legacy              # same suite, legacy add-on load
python3 tests/run_blender.py --addon-root OLD tests/probe_behaviour.py -- old.json
python3 tests/run_blender.py tests/probe_behaviour.py -- new.json
python3 tests/compare_probes.py old.json new.json  # 0 differences unless behaviour changed on purpose
python3 tools/build_package.py                     # -> dist/sanzo_wada_colors-<ver>.zip (+ LICENSE)
# scratch-profile install check:
export BLENDER_USER_RESOURCES=<tmp> BLENDER_USER_CONFIG=<tmp>/config BLENDER_USER_SCRIPTS=<tmp>/scripts BLENDER_USER_EXTENSIONS=<tmp>/extensions
blender -b --factory-startup --command extension install-file --repo user_default --enable dist/sanzo_wada_colors-*.zip
blender -b --python-exit-code 1 --python tests/check_installed_package.py   # "PROBLEMS: none"
```

## Architecture (all in `sanzo_wada_colors/__init__.py`)

- `_DB`: `path`, `error`, `colors` (sorted dicts: index, name, hex, srgb, rgb, cmyk, combinations,
  use_count), `by_index`, `position` (index -> position in colors / in the WM collection), `combos`.
- `load_library(path)` parses (dict `{"colors": [...]}` or list; `hex` or `rgb_array`) and raises;
  `reload_library()` catches, stores `_DB["error"]`, empties the library, then `sync_window_managers()`.
- `WindowManager.sanzo_colors` (`SANZO_PG_color`: idx, label, hex, name = "NNN Name #hex" for the
  list search; `color` = COLOR_GAMMA getter + no-op setter), `sanzo_active`, `sanzo_combo`
  (1..999), `sanzo_target` (AUTO | BLENDER | OCTANE).
- Prefs `SANZO_AddonPreferences` (`bl_idname = __package__`): `json_path` (update -> reload),
  `octane_rgb_node` ("OctaneRGBColor"), `octane_gradient_node` ("OctaneGradientMap").
- Nodes: `make_rgb_node`, `make_combo_frame`, `make_color_ramp` -> (node, used_octane),
  `set_node_color` (RGB output | first free RGBA/CUSTOM input | `_write_node_prop`). Values via
  `_color_value(prop_rna, color)`: COLOR -> linear, COLOR_GAMMA -> sRGB, length 3/4.
- Renderer: `octane_requested(ctx)` (OCTANE, or AUTO + engine 'octane'); `use_octane` = requested and
  `octane_available()` (`hasattr(bpy.types, id)` or `Node.bl_rna_get_subclass_py(id)`).
- Operators (`sanzo.*`): reload, select_color, set_combo (SET/PREV/NEXT/RANDOM, wraps), copy_hex,
  add_rgb_node, apply_color, add_combo_nodes, add_combo_ramp (interpolation), apply_combo
  (sort: 50-unit columns from the left, then top to bottom; cycles), make_palette ("Sanzo Wada NNN").
  `_TreeOp` mixin: poll = Shader Editor with an edit tree; REGISTER + UNDO.
- UI: `SANZO_UL_colors`, `SANZO_PT_colors`, `SANZO_PT_combinations` (`_SanzoPanel`: NODE_EDITOR, UI,
  category "Sanzo Wada", poll tree_type == ShaderNodeTree).
- Start-up: `register()` adds a `load_post` handler `_on_load_post` (refill list) and a timer
  `_deferred_init` (first load). Data flow: JSON -> `_DB` -> WM collection -> UIList/panels;
  operators read `_DB` and write nodes in `space_data.edit_tree`.

## Rules

- Never run anything in the user's open Blender or real profile (that includes the Blender MCP on
  port 9876). Use `tests/run_blender.py` (factory startup, temporary `BLENDER_USER_*`) and a scratch
  profile for install checks.
- Supported: Blender 5.3 only (manifest min 5.3.0, max 5.4.0). CI downloads exactly `BLENDER_VERSION`
  in `ci.yml`. No fallbacks for older APIs.
- Operator, panel and UIList docstrings become tooltips: use `bl_description` + `#` comments. Module
  and function docstrings are fine.
- Draw code only reads data.
- Bug fix -> add a check in `tests/test_sanzo.py` that fails without it. Behaviour change -> run the
  probe comparison and explain every difference.
- Never change the extension id `sanzo_wada_colors`. `colors.LICENSE` (MIT, Dain Blodorn) must ship
  next to `colors.json`.
- The add-on must stay offline (manifest has no `network` permission).

## Pitfalls found in this project

- A property with only a getter is read-only and is drawn as a disabled button that can't be dragged.
  The no-op setter on `SANZO_PG_color.color` is what makes swatches draggable.
- WindowManager properties are not saved in .blend files (tested: saved file has no color names), so
  the list must be refilled on `load_post`.
- `bpy.data` is restricted inside `register()`: first load runs from a timer. Background Blender never
  runs timers; tests call `_deferred_init()` themselves after unregistering the timer.
- `bl_rna_get_subclass_py(None)` raises TypeError; any string (also "") returns None or the class.
  `tree.nodes.new(unknown)` raises RuntimeError.
- Python-registered node classes are not attributes of `bpy.types` under their bl_idname; use
  `bpy.types.Node.bl_rna_get_subclass_py`.
- Background mode turns `report({'ERROR'})` into `RuntimeError` when run through `bpy.ops`; tests call
  `execute()` directly with a fake `self` instead.
- `template_list(listtype, list_id, dataptr, propname, active_dataptr, active_propname)`: mind the
  argument order when asserting on it.
- A safety hook in the agent environment refuses `rm -rf` with variables or globs: use explicit paths.

## How changes were verified (wrap-up, 2026-11-22)

- Baseline (1.0.0, commit 34dc312, before the cleanup) on the first suite: 165/165 in both load modes.
- Bug reproduced: Octane forced but not installed -> panel said "Nodes for: Octane" while Blender
  nodes were made, and Add Color Ramp warned about Octane's gradient node. Fixed (`octane_requested`).
- After: 177/177 in both load modes. Old code on the final suite: 158 checks, 1 failed (test_octane
  crashes: `octane_requested` does not exist there).
- Probe old vs new: 97,835 values, 64 differences, all the panel label (text + icon) in the 32 probed
  states with target Octane and no Octane. New vs new and old vs old: 0 differences.
- Combinations panel draw: 0.0376 -> 0.0122 ms (no per-draw dict over the 159 items), 3 runs each.
- AST scan: no unused functions, classes or imports, no duplicates, no constant conditions, no
  commented-out code; 15 classes registered (+2 mixins, not registered by design). Removed 4 version
  fallbacks dead on 5.3 (location_absolute, view_center, NodeSocket.enabled, try/except around
  bl_rna_get_subclass_py), `.DS_Store` and an old build zip.
- Built zip installed in a scratch profile: `check_installed_package.py` reported "PROBLEMS: none".

## Release checklist

1. Bump `version` in `sanzo_wada_colors/blender_manifest.toml`. README badges are live: never
   hard-code versions. Don't delete the `badges` branch (CI force-pushes `release-size.json`).
2. Run both test modes. Commit and push `main`. Wait for green CI.
3. `git tag -a vX.Y.Z -m "Sanzo Wada Colors X.Y.Z" -m "<notes>"`, then `git push origin vX.Y.Z`. CI
   checks tag == manifest version, tests, builds and publishes the release with the zip. The notes come
   from the tag message.

## Git

- Remote: `origin` https://github.com/mttfntn/sanzo-wada-colors-blender.git (public, not a fork).
- Branch: `main`. Tags: `vX.Y.Z` (annotated). `badges` branch: CI-owned.
- Ignored: `__pycache__/`, `*.pyc`, `dist/`, `*.zip`, `.DS_Store`, `.mcp.json`, `.claude/`.
- Not shipped in the zip: everything outside `sanzo_wada_colors/` (docs, tests, tools); LICENSE is added
  by the build script.
- Community files: `.github/ISSUE_TEMPLATE/` (forms, blank issues off), `.github/pull_request_template.md`,
  `CONTRIBUTING.md`, `SECURITY.md`. Keep their test command and check count in step with the suite.
