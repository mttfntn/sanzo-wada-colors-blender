# SPDX-License-Identifier: GPL-3.0-or-later
"""Sanzo Wada Colors — browse the 159 colors and 348 combinations of
Sanzo Wada's "A Dictionary of Color Combinations" from the Shader Editor
sidebar, and turn them into RGB nodes, Color Ramps, palettes and node colors.

Data is read from a local JSON file (bundled colors.json by default); nothing
is fetched from the network.

How the pieces fit together:
- load_library() parses the JSON into the module-level _DB (colors, lookups,
  combinations). reload_library() wraps it, keeping any error for the UI.
- sync_window_managers() mirrors _DB into WindowManager.sanzo_colors, the
  collection the UI list shows. WindowManager properties are not saved in
  .blend files, so it is refilled after every file load (_on_load_post) and
  once after registration (_deferred_init timer, since bpy.data is restricted
  inside register()).
- The node helpers (make_rgb_node, make_combo_frame, make_color_ramp,
  set_node_color) build or recolor nodes in a shader node tree. use_octane()
  decides whether to create Octane nodes or Blender's (Cycles/EEVEE) nodes.
- Operators call those helpers on the Shader Editor's edit tree; the two
  sidebar panels (N > Sanzo Wada) only read data and draw.
"""

import json
import os
import random

import bpy
from bpy.app.handlers import persistent
from bpy.props import (
    CollectionProperty,
    EnumProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)

BUNDLED_JSON = os.path.join(os.path.dirname(__file__), "colors.json")

# In-memory library, filled by load_library().
_DB = {
    "path": "",
    "error": "",
    "colors": [],       # list of color dicts (sorted by index)
    "by_index": {},     # color index -> color dict
    "position": {},     # color index -> position in "colors" (and in WindowManager.sanzo_colors)
    "combos": {},       # combination number -> [color index, ...]
}


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _srgb_to_linear(c):
    """sRGB transfer function, one channel (0..1) to linear."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _hex_to_srgb(hex_str):
    """'#rrggbb' (the '#' is optional) to an sRGB tuple of three floats 0..1."""
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def linear_rgba(color):
    """Scene-linear RGBA for node socket values."""
    return tuple(_srgb_to_linear(c) for c in color["srgb"]) + (1.0,)


# ---------------------------------------------------------------------------
# Library loading
# ---------------------------------------------------------------------------

def _prefs():
    """The add-on preferences, or None when the add-on is not enabled."""
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def library_path():
    """The custom JSON chosen in the preferences, else the bundled colors.json."""
    prefs = _prefs()
    if prefs and prefs.json_path:
        return bpy.path.abspath(prefs.json_path)
    return BUNDLED_JSON


def load_library(path=None):
    """Parse a color library JSON into _DB. Raises on a missing or invalid file.

    Accepts {"colors": [...]} or a bare list. Each color needs "index" and
    either "hex" or "rgb_array"; "name", "rgb", "cmyk", "combinations" and
    "use_count" are optional. Combinations are rebuilt from the colors'
    "combinations" lists (color indices in ascending order).
    """
    path = path or library_path()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = data["colors"] if isinstance(data, dict) else data

    colors = []
    for item in raw:
        if "hex" in item:
            srgb = _hex_to_srgb(item["hex"])
        else:
            srgb = tuple(v / 255.0 for v in item["rgb_array"])
        hex_str = item.get("hex") or "#%02x%02x%02x" % tuple(round(v * 255) for v in srgb)
        colors.append({
            "index": int(item["index"]),
            "name": item.get("name", "Color %d" % item["index"]),
            "hex": hex_str.lower(),
            "srgb": srgb,
            "rgb": item.get("rgb", ""),
            "cmyk": item.get("cmyk", ""),
            "combinations": sorted(int(c) for c in item.get("combinations", [])),
            "use_count": int(item.get("use_count", len(item.get("combinations", [])))),
        })
    colors.sort(key=lambda c: c["index"])

    combos = {}
    for c in colors:
        for n in c["combinations"]:
            combos.setdefault(n, []).append(c["index"])

    _DB.update(path=path, error="", colors=colors,
               by_index={c["index"]: c for c in colors},
               position={c["index"]: i for i, c in enumerate(colors)}, combos=combos)


def sync_window_managers():
    """Mirror the library into each WindowManager's collection (for the UI list).

    Items are added in _DB["colors"] order, so _DB["position"] also gives an
    item's position in the collection.
    """
    for wm in bpy.data.window_managers:
        coll = wm.sanzo_colors
        coll.clear()
        for c in _DB["colors"]:
            item = coll.add()
            item.idx = c["index"]
            item.label = c["name"]
            item.hex = c["hex"]
            # name is what the built-in UI list filter searches
            item.name = "%03d %s %s" % (c["index"], c["name"], c["hex"])
        if wm.sanzo_active >= len(coll):
            wm.sanzo_active = 0


def reload_library():
    """(Re)load the library from library_path() and refresh the UI list.

    On failure the library is emptied and the message is kept in _DB["error"],
    which the panels and preferences show.
    """
    try:
        load_library()
    except Exception as ex:  # keep the UI alive and report the problem
        _DB["error"] = str(ex)
        _DB.update(colors=[], by_index={}, position={}, combos={})
    sync_window_managers()


def active_color(context):
    """The color dict selected in the UI list, or None."""
    wm = context.window_manager
    if 0 <= wm.sanzo_active < len(wm.sanzo_colors):
        return _DB["by_index"].get(wm.sanzo_colors[wm.sanzo_active].idx)
    return None


def combo_colors(n):
    """Color dicts of combination n (empty list if it does not exist)."""
    return [_DB["by_index"][i] for i in _DB["combos"].get(n, [])]


# ---------------------------------------------------------------------------
# Node helpers
# ---------------------------------------------------------------------------

def _edit_tree(context):
    """The shader node tree open in the context's Shader Editor, else None."""
    space = context.space_data
    if space and space.type == 'NODE_EDITOR' and space.tree_type == 'ShaderNodeTree':
        return space.edit_tree
    return None


def _set_location(node, loc):
    # Absolute, so it is right also for nodes inside a frame.
    node.location_absolute = loc


def _view_center(tree):
    """Where new nodes go: the middle of the editor's current view."""
    vc = tree.view_center
    return (vc[0], vc[1])


def _deselect_all(tree):
    for n in tree.nodes:
        n.select = False


# --- Render-engine awareness ------------------------------------------------
#
# Cycles and EEVEE share Blender's own shader nodes. Octane (OctaneBlender)
# adds its own nodes and Python-defined sockets. Rather than hard-coding
# Octane's socket classes, colors are written by inspecting each socket's RNA:
# its "default_value" size and subtype (COLOR = linear, COLOR_GAMMA = sRGB).

def _pref(name, default):
    """A preference value, or `default` when the add-on is not enabled."""
    prefs = _prefs()
    return getattr(prefs, name, default) if prefs else default


def octane_available():
    """True when Octane's RGB node type (name set in the preferences) exists."""
    idname = _pref("octane_rgb_node", "OctaneRGBColor")
    # C-defined types are attributes of bpy.types; Python-registered node
    # classes (how OctaneBlender defines its nodes) are found by bl_idname.
    return hasattr(bpy.types, idname) or bpy.types.Node.bl_rna_get_subclass_py(idname) is not None


def octane_requested(context):
    """True when the user asked for Octane nodes (Octane target, or Auto with
    the scene rendering in Octane), whether or not Octane is installed."""
    target = context.window_manager.sanzo_target
    if target == 'AUTO':
        return context.scene.render.engine == 'octane'
    return target == 'OCTANE'


def use_octane(context):
    """True when new nodes should be Octane nodes: requested and available."""
    return octane_requested(context) and octane_available()


def _color_value(prop_rna, color):
    """Value for a color RNA property, matching its color space and size."""
    if prop_rna.subtype == 'COLOR_GAMMA':
        rgb = color["srgb"]
    else:
        rgb = tuple(_srgb_to_linear(c) for c in color["srgb"])
    return tuple(rgb) + (1.0,) * (prop_rna.array_length - 3)


def _is_color_prop(prop_rna):
    """True for a 3- or 4-float property with a COLOR or COLOR_GAMMA subtype."""
    return (prop_rna is not None and prop_rna.type == 'FLOAT'
            and prop_rna.subtype in {'COLOR', 'COLOR_GAMMA'}
            and prop_rna.array_length in (3, 4))


def _write_socket(sock, color):
    """Set a socket's value if it is a color; returns whether it was set."""
    prop = sock.bl_rna.properties.get("default_value")
    if not _is_color_prop(prop):
        return False
    sock.default_value = _color_value(prop, color)
    return True


def _write_node_prop(node, color):
    """Fallback for nodes that store their color as a node property.

    Sets the first writable color property, skipping Node.color (the header
    tint). Returns whether one was found.
    """
    for prop in node.bl_rna.properties:
        if _is_color_prop(prop) and not prop.is_readonly and prop.identifier != "color":
            setattr(node, prop.identifier, _color_value(prop, color))
            return True
    return False


def _new_octane_node(tree, pref_name, default):
    """Create the Octane node named in preference `pref_name`; None if that type does not exist."""
    idname = _pref(pref_name, default)
    try:
        return tree.nodes.new(idname)
    except RuntimeError:  # unknown node type
        return None


def make_rgb_node(tree, color, loc, parent=None, octane=False):
    """Add a node holding `color`, labelled with its name and tinted with it.

    Octane's RGB node when `octane` is true (and the type exists), otherwise
    Blender's RGB node. Selected, at `loc`, optionally inside frame `parent`.
    """
    node = _new_octane_node(tree, "octane_rgb_node", "OctaneRGBColor") if octane else None
    if node is not None:
        if not (set_node_color(node, color)):
            print("Sanzo Wada: could not find a color field on", node.bl_idname)
    else:
        node = tree.nodes.new("ShaderNodeRGB")
        node.outputs[0].default_value = linear_rgba(color)
    node.label = color["name"]
    node.use_custom_color = True
    node.color = color["srgb"]
    if parent is not None:
        node.parent = parent
    _set_location(node, loc)
    node.select = True
    return node


def set_node_color(node, color):
    """Put a color into a node: RGB node output, first free color input,
    or a color property on the node itself (some Octane nodes).

    Inputs that are linked, hidden or disabled are skipped. Returns whether
    anything was set.
    """
    if node.bl_idname == "ShaderNodeRGB":
        return _write_socket(node.outputs[0], color)
    for sock in node.inputs:
        if sock.is_linked or sock.hide or not sock.enabled:
            continue
        # CUSTOM = Python-defined sockets, such as Octane's
        if (sock.type == 'RGBA' or sock.type == 'CUSTOM') and _write_socket(sock, color):
            return True
    return _write_node_prop(node, color)


def make_combo_frame(tree, n, origin, octane=False):
    """Add a frame holding one RGB node per color of combination n, in a row."""
    colors = combo_colors(n)
    frame = tree.nodes.new("NodeFrame")
    frame.label = "Sanzo Wada · Combination %d" % n
    frame.label_size = 16
    _set_location(frame, origin)
    for i, c in enumerate(colors):
        make_rgb_node(tree, c, (origin[0] + i * 200.0, origin[1]), parent=frame, octane=octane)
    return frame


def make_color_ramp(tree, n, loc, interpolation='CONSTANT', octane=False):
    """Add a color ramp with one stop per color of combination n.

    CONSTANT spreads the stops as equal bands (0, 1/n, 2/n...); LINEAR and
    EASE put the first stop at 0 and the last at 1. With `octane`, Octane's
    gradient node is used if it exposes a `color_ramp`, otherwise Blender's
    Color Ramp. Returns (node, used_octane).
    """
    colors = combo_colors(n)
    node = None
    if octane:
        node = _new_octane_node(tree, "octane_gradient_node", "OctaneGradientMap")
        if node is not None and getattr(node, "color_ramp", None) is None:
            tree.nodes.remove(node)  # this Octane version keeps its ramp elsewhere
            node = None
    used_octane = node is not None
    if node is None:
        node = tree.nodes.new("ShaderNodeValToRGB")
    node.label = "Sanzo Wada %d" % n
    ramp = node.color_ramp
    ramp.interpolation = interpolation
    count = len(colors)
    while len(ramp.elements) > count:
        ramp.elements.remove(ramp.elements[-1])
    for i, c in enumerate(colors):
        if interpolation == 'CONSTANT':
            pos = i / count
        else:
            pos = i / (count - 1) if count > 1 else 0.0
        if i < len(ramp.elements):
            el = ramp.elements[i]
            el.position = pos
        else:
            el = ramp.elements.new(pos)
        el.color = linear_rgba(c)
    _set_location(node, loc)
    node.select = True
    return node, used_octane


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

def _get_item_color(self):
    """Getter of SANZO_PG_color.color: the library's sRGB value for this item."""
    c = _DB["by_index"].get(self.idx)
    return c["srgb"] if c else (0.0, 0.0, 0.0)


def _set_item_color(self, value):
    # Ignore edits: the library is fixed. Having a setter keeps the swatch an
    # active (non-greyed) button, which is what makes it draggable.
    pass


# One row of the UI list (WindowManager.sanzo_colors). `name` (inherited) is
# "NNN Name #hex", which the list's built-in search filters on.
class SANZO_PG_color(bpy.types.PropertyGroup):
    idx: IntProperty()       # color index in the book (1..159)
    label: StringProperty()  # color name
    hex: StringProperty()
    # sRGB swatch. Drag it onto any color field (node sockets, Base Color,
    # world color, paint color...) - Blender converts to linear where needed.
    color: FloatVectorProperty(subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0,
                               get=_get_item_color, set=_set_item_color)


class SANZO_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    json_path: StringProperty(
        name="Color Library JSON",
        description="Local JSON file with the color library. Leave empty to use the bundled copy",
        subtype='FILE_PATH',
        update=lambda self, ctx: reload_library(),
    )
    octane_rgb_node: StringProperty(
        name="Octane RGB node",
        description="bl_idname of Octane's RGB color node (change only if your OctaneBlender uses another name)",
        default="OctaneRGBColor",
    )
    octane_gradient_node: StringProperty(
        name="Octane gradient node",
        description="bl_idname of Octane's gradient node (used for Color Ramp when it exposes a color ramp)",
        default="OctaneGradientMap",
    )

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "json_path")
        box = col.box()
        box.label(text="Octane", icon='SHADING_RENDERED')
        box.prop(self, "octane_rgb_node")
        box.prop(self, "octane_gradient_node")
        box.label(text="Octane nodes found: %s" % ("yes" if octane_available() else "no"))
        col.label(text="In use: " + (_DB["path"] or "(none)"))
        if _DB["error"]:
            col.label(text="Error: " + _DB["error"], icon='ERROR')
        else:
            col.label(text="%d colors, %d combinations" % (len(_DB["colors"]), len(_DB["combos"])))


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

# Mixin for operators that edit the open shader node tree (not registered).
# Comments, not docstrings, on operator/panel classes: Blender shows class
# docstrings as tooltips.
class _TreeOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _edit_tree(context) is not None


class SANZO_OT_reload(bpy.types.Operator):
    bl_idname = "sanzo.reload"
    bl_label = "Reload Library"
    bl_description = "Reload the local color library JSON"

    def execute(self, context):
        reload_library()
        if _DB["error"]:
            self.report({'ERROR'}, _DB["error"])
            return {'CANCELLED'}
        self.report({'INFO'}, "Loaded %d colors" % len(_DB["colors"]))
        return {'FINISHED'}


class SANZO_OT_select_color(bpy.types.Operator):
    bl_idname = "sanzo.select_color"
    bl_label = "Select Color"
    bl_description = "Show this color in the library list"
    bl_options = {'INTERNAL'}

    color_index: IntProperty()

    def execute(self, context):
        wm = context.window_manager
        for i, item in enumerate(wm.sanzo_colors):
            if item.idx == self.color_index:
                wm.sanzo_active = i
                break
        return {'FINISHED'}


class SANZO_OT_set_combo(bpy.types.Operator):
    bl_idname = "sanzo.set_combo"
    bl_label = "Show Combination"
    bl_description = "Show this combination"
    bl_options = {'INTERNAL'}

    combo: IntProperty()
    mode: EnumProperty(items=[('SET', "Set", ""), ('PREV', "Previous", ""),
                              ('NEXT', "Next", ""), ('RANDOM', "Random", "")],
                       default='SET')

    def execute(self, context):
        wm = context.window_manager
        keys = sorted(_DB["combos"])
        if not keys:
            return {'CANCELLED'}
        cur = wm.sanzo_combo
        if self.mode == 'SET':
            wm.sanzo_combo = self.combo
        elif self.mode == 'PREV':
            wm.sanzo_combo = max((k for k in keys if k < cur), default=keys[-1])
        elif self.mode == 'NEXT':
            wm.sanzo_combo = min((k for k in keys if k > cur), default=keys[0])
        else:
            wm.sanzo_combo = random.choice(keys)
        return {'FINISHED'}


class SANZO_OT_copy_hex(bpy.types.Operator):
    bl_idname = "sanzo.copy_hex"
    bl_label = "Copy Hex"
    bl_description = "Copy the hex code to the clipboard"
    bl_options = {'INTERNAL'}

    color_index: IntProperty()

    def execute(self, context):
        c = _DB["by_index"].get(self.color_index)
        if not c:
            return {'CANCELLED'}
        context.window_manager.clipboard = c["hex"]
        self.report({'INFO'}, "Copied %s" % c["hex"])
        return {'FINISHED'}


class SANZO_OT_add_rgb_node(_TreeOp, bpy.types.Operator):
    bl_idname = "sanzo.add_rgb_node"
    bl_label = "Add RGB Node"
    bl_description = "Add an RGB node with this color to the node tree"

    color_index: IntProperty()

    def execute(self, context):
        tree = _edit_tree(context)
        c = _DB["by_index"].get(self.color_index)
        if not c:
            return {'CANCELLED'}
        _deselect_all(tree)
        tree.nodes.active = make_rgb_node(tree, c, _view_center(tree), octane=use_octane(context))
        return {'FINISHED'}


class SANZO_OT_apply_color(_TreeOp, bpy.types.Operator):
    bl_idname = "sanzo.apply_color"
    bl_label = "Apply to Selected Nodes"
    bl_description = ("Set this color on the selected nodes (RGB nodes, or the first "
                      "unconnected color input, e.g. Base Color)")

    color_index: IntProperty()

    def execute(self, context):
        tree = _edit_tree(context)
        c = _DB["by_index"].get(self.color_index)
        nodes = [n for n in tree.nodes if n.select] or ([tree.nodes.active] if tree.nodes.active else [])
        done = sum(set_node_color(n, c) for n in nodes) if c else 0
        if not done:
            self.report({'WARNING'}, "No selected node has a free color input")
            return {'CANCELLED'}
        self.report({'INFO'}, "Applied %s to %d node(s)" % (c["name"], done))
        return {'FINISHED'}


class SANZO_OT_add_combo_nodes(_TreeOp, bpy.types.Operator):
    bl_idname = "sanzo.add_combo_nodes"
    bl_label = "Add Palette Nodes"
    bl_description = "Add a frame with one RGB node per color of the combination"

    def execute(self, context):
        tree = _edit_tree(context)
        n = context.window_manager.sanzo_combo
        if n not in _DB["combos"]:
            return {'CANCELLED'}
        _deselect_all(tree)
        make_combo_frame(tree, n, _view_center(tree), octane=use_octane(context))
        return {'FINISHED'}


class SANZO_OT_add_combo_ramp(_TreeOp, bpy.types.Operator):
    bl_idname = "sanzo.add_combo_ramp"
    bl_label = "Add Color Ramp"
    bl_description = "Add a Color Ramp node built from the combination"

    interpolation: EnumProperty(
        name="Interpolation",
        items=[('CONSTANT', "Constant", "Hard color bands"),
               ('LINEAR', "Linear", "Smooth gradient"),
               ('EASE', "Ease", "Eased gradient")],
        default='CONSTANT')

    def execute(self, context):
        tree = _edit_tree(context)
        n = context.window_manager.sanzo_combo
        if n not in _DB["combos"]:
            return {'CANCELLED'}
        _deselect_all(tree)
        octane = use_octane(context)
        node, used_octane = make_color_ramp(tree, n, _view_center(tree), self.interpolation, octane)
        tree.nodes.active = node
        if octane and not used_octane:
            self.report({'WARNING'}, "Octane gradient node has no editable ramp; added a Blender Color Ramp")
        return {'FINISHED'}


class SANZO_OT_apply_combo(_TreeOp, bpy.types.Operator):
    bl_idname = "sanzo.apply_combo"
    bl_label = "Distribute to Selected"
    bl_description = ("Assign the combination's colors, in order, to the selected nodes "
                      "(column by column from the left, top to bottom in each column; "
                      "starts again from the first color if there are more nodes)")

    def execute(self, context):
        tree = _edit_tree(context)
        colors = combo_colors(context.window_manager.sanzo_combo)
        # Columns are 50 units wide, so slightly misaligned nodes count as one column.
        nodes = sorted((n for n in tree.nodes if n.select and n.bl_idname != "NodeFrame"),
                       key=lambda n: (round(n.location[0] / 50), -n.location[1]))
        if not colors or not nodes:
            self.report({'WARNING'}, "Select some nodes first")
            return {'CANCELLED'}
        done = 0
        for i, node in enumerate(nodes):
            done += set_node_color(node, colors[i % len(colors)])
        self.report({'INFO'}, "Colored %d node(s)" % done)
        return {'FINISHED'}


class SANZO_OT_make_palette(bpy.types.Operator):
    bl_idname = "sanzo.make_palette"
    bl_label = "Create Palette"
    bl_description = "Create a Blender Palette (usable in paint modes) from the combination"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        n = context.window_manager.sanzo_combo
        colors = combo_colors(n)
        if not colors:
            return {'CANCELLED'}
        name = "Sanzo Wada %03d" % n
        pal = bpy.data.palettes.get(name) or bpy.data.palettes.new(name)
        while pal.colors:
            pal.colors.remove(pal.colors[0])
        for c in colors:
            pal.colors.new().color = c["srgb"]
        self.report({'INFO'}, "Palette '%s' ready" % name)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class SANZO_UL_colors(bpy.types.UIList):
    bl_idname = "SANZO_UL_colors"

    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        sw = row.row()
        sw.ui_units_x = 1.6
        sw.prop(item, "color", text="")
        row.label(text="%d  %s" % (item.idx, item.label))
        sub = row.row()
        sub.alignment = 'RIGHT'
        sub.label(text=item.hex)


# Mixin for the sidebar panels (not registered): Shader Editor only.
class _SanzoPanel:
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Sanzo Wada"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.tree_type == 'ShaderNodeTree'


def _no_tree_hint(layout, context):
    if _edit_tree(context) is None:
        layout.label(text="Open a material/world to add nodes", icon='INFO')


class SANZO_PT_colors(_SanzoPanel, bpy.types.Panel):
    bl_idname = "SANZO_PT_colors"
    bl_label = "Sanzo Wada Colors"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        row = layout.row()
        row.label(text="%d colors · %d combinations" % (len(_DB["colors"]), len(_DB["combos"])))
        row.operator("sanzo.reload", text="", icon='FILE_REFRESH')

        row = layout.row(align=True)
        row.prop(wm, "sanzo_target", expand=True)
        if use_octane(context):
            layout.label(text="Nodes for: Octane", icon='SHADING_RENDERED')
        elif octane_requested(context):
            layout.label(text="Octane not found: using Cycles / EEVEE nodes", icon='ERROR')
        else:
            layout.label(text="Nodes for: Cycles / EEVEE", icon='SHADING_RENDERED')
        layout.label(text="Drag a swatch onto any color field", icon='INFO')
        if _DB["error"]:
            layout.label(text=_DB["error"], icon='ERROR')
            return

        layout.template_list("SANZO_UL_colors", "", wm, "sanzo_colors", wm, "sanzo_active", rows=8)

        c = active_color(context)
        if not c:
            return
        item = wm.sanzo_colors[wm.sanzo_active]

        box = layout.box()
        sw = box.row()
        sw.scale_y = 2.0
        sw.prop(item, "color", text="")
        col = box.column(align=True)
        col.label(text="%d · %s" % (c["index"], c["name"]))
        r = col.row(align=True)
        r.label(text=c["hex"])
        r.operator("sanzo.copy_hex", text="", icon='COPYDOWN').color_index = c["index"]
        if c["rgb"]:
            col.label(text=c["rgb"])
        if c["cmyk"]:
            col.label(text=c["cmyk"])

        col = box.column(align=True)
        _no_tree_hint(col, context)
        col.operator("sanzo.add_rgb_node", icon='ADD').color_index = c["index"]
        col.operator("sanzo.apply_color", icon='BRUSH_DATA').color_index = c["index"]

        if c["combinations"]:
            box.label(text="Used in %d combinations:" % len(c["combinations"]))
            grid = box.grid_flow(row_major=True, columns=6, even_columns=True, align=True)
            for n in c["combinations"]:
                op = grid.operator("sanzo.set_combo", text=str(n),
                                   depress=(n == wm.sanzo_combo))
                op.combo = n
                op.mode = 'SET'


class SANZO_PT_combinations(_SanzoPanel, bpy.types.Panel):
    bl_idname = "SANZO_PT_combinations"
    bl_label = "Combinations"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        if not _DB["combos"]:
            layout.label(text="No library loaded", icon='ERROR')
            return

        row = layout.row(align=True)
        op = row.operator("sanzo.set_combo", text="", icon='TRIA_LEFT')
        op.mode = 'PREV'
        row.prop(wm, "sanzo_combo", text="Combination")
        op = row.operator("sanzo.set_combo", text="", icon='TRIA_RIGHT')
        op.mode = 'NEXT'
        op = row.operator("sanzo.set_combo", text="", icon='FILE_REFRESH')
        op.mode = 'RANDOM'

        ids = _DB["combos"].get(wm.sanzo_combo)
        if not ids:
            layout.label(text="No combination with this number", icon='INFO')
            return

        # Swatches are the list's own items (draggable). _DB["position"] finds
        # them without scanning the whole collection on every redraw.
        coll = wm.sanzo_colors
        strip = layout.row(align=True)
        strip.scale_y = 2.5
        for i in ids:
            p = _DB["position"].get(i)
            if p is not None and p < len(coll) and coll[p].idx == i:
                strip.prop(coll[p], "color", text="")

        col = layout.column(align=True)
        for i in ids:
            c = _DB["by_index"][i]
            r = col.row(align=True)
            r.operator("sanzo.select_color", text="", icon='RESTRICT_SELECT_OFF').color_index = i
            r.label(text="%d  %s" % (i, c["name"]))
            r.label(text=c["hex"])

        col = layout.column(align=True)
        _no_tree_hint(col, context)
        col.operator("sanzo.add_combo_nodes", icon='NODE')
        col.operator("sanzo.add_combo_ramp", icon='NODE_TEXTURE')
        col.operator("sanzo.apply_combo", icon='BRUSH_DATA')
        col.operator("sanzo.make_palette", icon='COLOR')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    SANZO_PG_color,
    SANZO_AddonPreferences,
    SANZO_OT_reload,
    SANZO_OT_select_color,
    SANZO_OT_set_combo,
    SANZO_OT_copy_hex,
    SANZO_OT_add_rgb_node,
    SANZO_OT_apply_color,
    SANZO_OT_add_combo_nodes,
    SANZO_OT_add_combo_ramp,
    SANZO_OT_apply_combo,
    SANZO_OT_make_palette,
    SANZO_UL_colors,
    SANZO_PT_colors,
    SANZO_PT_combinations,
)


@persistent
def _on_load_post(*_args):
    """After a file load: refill the UI list (WindowManager data is not saved)."""
    sync_window_managers()


def _deferred_init():
    """First load of the library, run by a timer right after register()."""
    reload_library()
    return None  # run once


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.sanzo_colors = CollectionProperty(type=SANZO_PG_color)
    wm.sanzo_active = IntProperty(name="Active Color", default=0)
    wm.sanzo_target = EnumProperty(
        name="Node Target",
        description="Which renderer's nodes to create",
        items=[('AUTO', "Auto", "Octane nodes when the scene renders with Octane, otherwise Blender nodes"),
               ('BLENDER', "Cycles/EEVEE", "Blender's own shader nodes"),
               ('OCTANE', "Octane", "Octane nodes (Blender nodes when Octane is not installed)")],
        default='AUTO')
    wm.sanzo_combo = IntProperty(name="Combination", default=1, min=1, max=999,
                                 description="Combination number from the book")
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)
    # bpy.data is restricted during registration; populate right after.
    bpy.app.timers.register(_deferred_init, first_interval=0.0)


def unregister():
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    if bpy.app.timers.is_registered(_deferred_init):
        bpy.app.timers.unregister(_deferred_init)
    wm = bpy.types.WindowManager
    del wm.sanzo_combo
    del wm.sanzo_target
    del wm.sanzo_active
    del wm.sanzo_colors
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
