"""Check the built extension after installing it into a SCRATCH profile.

With BLENDER_USER_* pointing at a scratch profile:
    blender -b --factory-startup --command extension install-file --repo user_default --enable dist/sanzo_wada_colors-X.Y.Z.zip
    blender -b --python-exit-code 1 --python tests/check_installed_package.py
(no --factory-startup on the second call: it must load the scratch preferences
that the install just saved). Exits 1 if the installed extension is missing,
disabled or broken.
"""
import os
import sys
import tomllib

import bpy

MOD = "bl_ext.user_default.sanzo_wada_colors"
problems = []
addon = bpy.context.preferences.addons.get(MOD)
if addon is None:
    problems.append("extension not enabled: " + MOD)
else:
    sw = sys.modules[MOD]
    pkg_dir = os.path.dirname(sw.__file__)
    for name in ("json_path", "octane_rgb_node", "octane_gradient_node"):
        if name not in addon.preferences.bl_rna.properties:
            problems.append("missing preference " + name)
    for cls in ("SANZO_PT_colors", "SANZO_PT_combinations", "SANZO_UL_colors",
                "SANZO_OT_add_rgb_node", "SANZO_OT_add_combo_nodes", "SANZO_OT_add_combo_ramp"):
        if not hasattr(bpy.types, cls):
            problems.append("class not registered: " + cls)
    if not any(getattr(h, "__name__", "") == "_on_load_post" for h in bpy.app.handlers.load_post):
        problems.append("load_post handler missing")
    # One real use: the start-up load, then a palette frame in a material.
    if bpy.app.timers.is_registered(sw._deferred_init):
        bpy.app.timers.unregister(sw._deferred_init)
    sw._deferred_init()
    wm = bpy.context.window_manager
    if sw._DB["error"] or len(sw._DB["colors"]) != 159 or len(sw._DB["combos"]) != 348:
        problems.append(f"library not loaded: {sw._DB['error']!r} {len(sw._DB['colors'])}")
    if len(wm.sanzo_colors) != 159:
        problems.append("UI list not filled")
    tree = bpy.data.materials.new("check").node_tree
    frame = sw.make_combo_frame(tree, 1, (0.0, 0.0))
    if len([n for n in tree.nodes if n.parent == frame]) != len(sw._DB["combos"][1]):
        problems.append("palette frame not built")
    for name in ("LICENSE", "colors.LICENSE", "colors.json"):
        if not os.path.isfile(os.path.join(pkg_dir, name)):
            problems.append(name + " missing from installed package")
    with open(os.path.join(pkg_dir, "blender_manifest.toml"), "rb") as f:
        manifest = tomllib.load(f)
    print("installed at", pkg_dir, "version", manifest["version"])

print("PROBLEMS:", problems or "none")
sys.stdout.flush()
os._exit(1 if problems else 0)
