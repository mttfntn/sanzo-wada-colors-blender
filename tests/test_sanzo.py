"""Headless test suite for Sanzo Wada Colors.

Run from the repo root (never inside your open Blender session):
    python3 tests/run_blender.py            # loaded as an extension
    python3 tests/run_blender.py --legacy   # loaded as a legacy add-on
run_blender.py starts Blender with --factory-startup and a throwaway profile
that already contains the add-on. Prints "N checks, M failed" and exits 1 on
any failure.

Background Blender has no window, so operators are run by calling their
execute() with a stand-in `self` and a fake Shader Editor context, and panels
are drawn into a fake layout that checks every property and operator name
against the real API. An "Octane" node is mocked with a Python socket to run
the Octane code paths, since Octane itself is not installed here.
"""

import importlib
import json
import os
import sys
import tempfile
import traceback
import types

import addon_utils
import bpy
from mathutils import Color

MOD = os.environ.get("SW_MODULE", "bl_ext.user_default.sanzo_wada_colors")
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)) if (detail and not cond) else ""))


def close(a, b, eps=1e-4):
    return len(a) == len(b) and all(abs(x - y) <= eps for x, y in zip(a, b))


# ----------------------------------------------------------------- helpers

class FakeLayout:
    """Accepts every UILayout call, records it, and validates prop/operator names."""

    def __init__(self, log):
        self.__dict__["log"] = log

    def __getattr__(self, name):
        log = self.log

        def call(*args, **kw):
            if name == "prop":
                data, prop = args[0], args[1]
                if prop not in data.bl_rna.properties:
                    log.append(("BAD-prop", prop))
                log.append(("prop", prop, kw.get("text")))
                if prop == "color":
                    log.append(("swatch", data.idx))
            elif name == "operator":
                mod, op = args[0].split(".")
                try:
                    getattr(getattr(bpy.ops, mod), op).get_rna_type()
                except Exception:
                    log.append(("BAD-op", args[0]))
                log.append(("op", args[0], kw.get("text", "")))
                return types.SimpleNamespace()
            elif name == "label":
                log.append(("label", kw.get("text", args[0] if args else "")))
            elif name == "template_list":
                log.append(("list", args[0], args[2], args[3], args[5]))
            elif name not in bpy.types.UILayout.bl_rna.functions:
                log.append(("BAD-call", name))
            return FakeLayout(log)
        return call

    def __setattr__(self, name, value):
        if name not in bpy.types.UILayout.bl_rna.properties:
            self.log.append(("BAD-attr", name))


def draw(cls, context):
    log = []
    cls.draw(types.SimpleNamespace(layout=FakeLayout(log)), context)
    return log


def fake_context(tree=None, space_type="NODE_EDITOR", tree_type="ShaderNodeTree", scene=None):
    space = types.SimpleNamespace(type=space_type, tree_type=tree_type, edit_tree=tree)
    return types.SimpleNamespace(space_data=space, window_manager=bpy.context.window_manager,
                                 scene=scene or bpy.context.scene, preferences=bpy.context.preferences)


class FakeOp:
    """Stand-in `self` for Operator.execute(self, context)."""

    def __init__(self, **props):
        self.__dict__.update(props)
        self.reports = []

    def report(self, kind, msg):
        self.reports.append((sorted(kind)[0], msg))


def new_tree(name="T"):
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    return mat.node_tree


def register_mock_octane():
    """A node shaped like Octane's RGB Color: a Python socket with an sRGB (COLOR_GAMMA) value."""
    class SWTestOctaneSocket(bpy.types.NodeSocket):
        bl_idname = "SWTestOctaneSocket"
        default_value: bpy.props.FloatVectorProperty(subtype='COLOR_GAMMA', size=3)

        def draw(self, context, layout, node, text):
            pass

        def draw_color(self, context, node):
            return (1.0, 1.0, 0.0, 1.0)

    class SWTestOctaneRGB(bpy.types.ShaderNode):
        bl_idname = "SWTestOctaneRGB"
        bl_label = "RGB Color"

        def init(self, context):
            self.inputs.new("SWTestOctaneSocket", "Color")
            self.outputs.new("NodeSocketColor", "Out")

    class SWTestOctanePropNode(bpy.types.ShaderNode):
        # color kept as a node property instead of a socket
        bl_idname = "SWTestOctanePropNode"
        bl_label = "Prop Color"
        a_color: bpy.props.FloatVectorProperty(subtype='COLOR', size=4)

    for c in (SWTestOctaneSocket, SWTestOctaneRGB, SWTestOctanePropNode):
        bpy.utils.register_class(c)


# ----------------------------------------------------------------- tests

EXPECTED_CLASSES = (
    "SANZO_OT_reload", "SANZO_OT_select_color", "SANZO_OT_set_combo", "SANZO_OT_copy_hex",
    "SANZO_OT_add_rgb_node", "SANZO_OT_apply_color", "SANZO_OT_add_combo_nodes",
    "SANZO_OT_add_combo_ramp", "SANZO_OT_apply_combo", "SANZO_OT_make_palette",
    "SANZO_UL_colors", "SANZO_PT_colors", "SANZO_PT_combinations",
)


def test_registration(sw):
    for name in EXPECTED_CLASSES:
        check("registered " + name, hasattr(bpy.types, name))
    for prop in ("sanzo_colors", "sanzo_active", "sanzo_combo", "sanzo_target"):
        check("WindowManager." + prop, prop in bpy.types.WindowManager.bl_rna.properties)
    check("load_post handler", any(getattr(h, "__name__", "") == "_on_load_post"
                                   for h in bpy.app.handlers.load_post))
    check("start-up timer pending", bpy.app.timers.is_registered(sw._deferred_init))
    check("prefs registered", bpy.context.preferences.addons[MOD].preferences is not None)
    check("bundled json path", os.path.isfile(sw.BUNDLED_JSON))
    # Run the deferred start-up (background Blender has no event loop for timers).
    bpy.app.timers.unregister(sw._deferred_init)
    sw._deferred_init()


def test_library(sw):
    db = sw._DB
    wm = bpy.context.window_manager
    check("no load error", db["error"] == "", db["error"])
    check("159 colors", len(db["colors"]) == 159, len(db["colors"]))
    check("348 combinations", len(db["combos"]) == 348, len(db["combos"]))
    check("combinations numbered 1..348", sorted(db["combos"]) == list(range(1, 349)))
    check("colors sorted by index", [c["index"] for c in db["colors"]] == list(range(1, 160)))
    check("every combination has 2-4 colors",
          all(2 <= len(v) <= 4 for v in db["combos"].values()),
          sorted({len(v) for v in db["combos"].values()}))
    check("combos sorted by color index", all(v == sorted(v) for v in db["combos"].values()))
    c1 = db["by_index"][1]
    check("color 1 name", c1["name"] == "Hermosa Pink", c1["name"])
    check("color 1 hex", c1["hex"] == "#ffb3f0")
    check("color 1 srgb", close(c1["srgb"], (1.0, 179 / 255, 240 / 255)))
    check("color 1 rgb/cmyk strings", c1["rgb"].startswith("R:255") and c1["cmyk"].startswith("C:0"))
    check("use_count matches combinations",
          all(c["use_count"] == len(c["combinations"]) for c in db["colors"]))
    raw = json.load(open(sw.BUNDLED_JSON, encoding="utf-8"))["colors"]
    check("hex agrees with rgb_array in source",
          all("#%02x%02x%02x" % tuple(r["rgb_array"]) == r["hex"].lower() for r in raw))
    check("combination 1 colors", db["combos"][1] == [i for i, c in db["by_index"].items() if 1 in c["combinations"]])
    # window-manager mirror
    check("wm collection mirrors library", len(wm.sanzo_colors) == 159)
    it = wm.sanzo_colors[0]
    check("item name searchable", it.name == "001 Hermosa Pink #ffb3f0", it.name)
    check("item fields", it.idx == 1 and it.label == "Hermosa Pink" and it.hex == "#ffb3f0")


def test_color_math(sw):
    # Compare with Blender's own sRGB -> scene linear conversion.
    worst = 0.0
    for c in sw._DB["colors"]:
        mine = sw.linear_rgba(c)
        ref = Color(c["srgb"]).from_srgb_to_scene_linear()
        worst = max(worst, max(abs(a - b) for a, b in zip(mine[:3], ref)))
        if mine[3] != 1.0:
            worst = 9
    check("linear_rgba matches Blender colour management", worst < 1e-3, worst)
    check("hex parse", close(sw._hex_to_srgb("#ff8000"), (1.0, 128 / 255, 0.0)))
    check("hex parse without #", close(sw._hex_to_srgb("0080ff"), (0.0, 128 / 255, 1.0)))


def test_swatch_property(sw):
    wm = bpy.context.window_manager
    it = wm.sanzo_colors[0]
    prop = type(it).bl_rna.properties["color"]
    check("swatch is sRGB (COLOR_GAMMA)", prop.subtype == 'COLOR_GAMMA')
    check("swatch is editable (draggable button)", not prop.is_readonly)
    before = tuple(it.color)
    it.color = (0.0, 0.0, 0.0)
    check("swatch edits are ignored", close(tuple(it.color), before))
    check("swatch value", close(before, sw._DB["by_index"][1]["srgb"]))


def test_poll_and_context(sw):
    tree = new_tree("poll")
    check("panel poll in shader editor", sw.SANZO_PT_colors.poll(fake_context(tree)))
    check("panel hidden in geometry nodes",
          not sw.SANZO_PT_colors.poll(fake_context(tree, tree_type="GeometryNodeTree")))
    check("tree op poll needs a tree", not sw.SANZO_OT_add_rgb_node.poll(fake_context(None)))
    check("tree op poll ok", sw.SANZO_OT_add_rgb_node.poll(fake_context(tree)))
    check("tree op poll not in 3D view",
          not sw.SANZO_OT_add_rgb_node.poll(fake_context(tree, space_type="VIEW_3D")))
    check("real context: tree ops disabled (no node editor)", not bpy.ops.sanzo.add_combo_nodes.poll())


def test_blender_nodes(sw):
    wm = bpy.context.window_manager
    wm.sanzo_target = 'BLENDER'
    tree = new_tree("nodes")
    ctx = fake_context(tree)
    db = sw._DB
    n0 = len(tree.nodes)

    op = FakeOp(color_index=2)
    check("add rgb node: FINISHED", sw.SANZO_OT_add_rgb_node.execute(op, ctx) == {'FINISHED'})
    node = tree.nodes.active
    check("rgb node type", node.bl_idname == "ShaderNodeRGB")
    check("rgb node label", node.label == "Corinthian Pink")
    check("rgb node linear value", close(tuple(node.outputs[0].default_value), sw.linear_rgba(db["by_index"][2])))
    check("rgb node header colour = sRGB", node.use_custom_color and close(tuple(node.color), db["by_index"][2]["srgb"]))
    check("only new node selected", [n for n in tree.nodes if n.select] == [node])
    check("bad color index cancels", sw.SANZO_OT_add_rgb_node.execute(FakeOp(color_index=9999), ctx) == {'CANCELLED'})

    wm.sanzo_combo = 5
    ids = db["combos"][5]
    check("add combo frame", sw.SANZO_OT_add_combo_nodes.execute(FakeOp(), ctx) == {'FINISHED'})
    frame = next(n for n in tree.nodes if n.bl_idname == "NodeFrame")
    kids = sorted((n for n in tree.nodes if n.parent == frame), key=lambda n: n.location_absolute[0])
    check("frame label", frame.label == "Sanzo Wada · Combination 5", frame.label)
    check("frame children = combination", [k.label for k in kids] == [db["by_index"][i]["name"] for i in ids])
    xs = [round(k.location_absolute[0]) for k in kids]
    check("frame children spaced left to right", all(b > a for a, b in zip(xs, xs[1:])), xs)

    wm.sanzo_combo = 999
    check("missing combo cancels nodes", sw.SANZO_OT_add_combo_nodes.execute(FakeOp(), ctx) == {'CANCELLED'})
    check("missing combo cancels ramp",
          sw.SANZO_OT_add_combo_ramp.execute(FakeOp(interpolation='LINEAR'), ctx) == {'CANCELLED'})

    for combo in (1, 200, 348):
        wm.sanzo_combo = combo
        ids = db["combos"][combo]
        for interp in ('CONSTANT', 'LINEAR', 'EASE'):
            op = FakeOp(interpolation=interp)
            res = sw.SANZO_OT_add_combo_ramp.execute(op, ctx)
            ramp = tree.nodes.active
            els = ramp.color_ramp.elements
            n = len(ids)
            want = [i / n for i in range(n)] if interp == 'CONSTANT' else [i / (n - 1) for i in range(n)]
            ok = (res == {'FINISHED'} and ramp.bl_idname == "ShaderNodeValToRGB"
                  and ramp.color_ramp.interpolation == interp and len(els) == n
                  and close([e.position for e in els], want)
                  and all(close(tuple(e.color), sw.linear_rgba(db["by_index"][i])) for e, i in zip(els, ids)))
            check(f"ramp combo {combo} {interp}", ok, [(e.position, tuple(e.color)) for e in els])
            check(f"ramp combo {combo} {interp}: no warning", op.reports == [], op.reports)
    check("nodes were added", len(tree.nodes) > n0)


def test_apply(sw):
    wm = bpy.context.window_manager
    db = sw._DB
    tree = new_tree("apply")
    ctx = fake_context(tree)
    bsdf = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in tree.nodes if n.type == "OUTPUT_MATERIAL")
    for n in tree.nodes:
        n.select = False
    bsdf.select = True
    op = FakeOp(color_index=3)
    check("apply to principled: FINISHED", sw.SANZO_OT_apply_color.execute(op, ctx) == {'FINISHED'})
    check("principled base colour set", close(tuple(bsdf.inputs["Base Color"].default_value),
                                             sw.linear_rgba(db["by_index"][3])))
    # linked base colour -> next free colour input
    rgb = tree.nodes.new("ShaderNodeRGB")
    tree.links.new(rgb.outputs[0], bsdf.inputs["Base Color"])
    rgb.select = False
    before = tuple(bsdf.inputs["Base Color"].default_value)
    sw.SANZO_OT_apply_color.execute(FakeOp(color_index=4), ctx)
    check("linked input skipped", close(tuple(bsdf.inputs["Base Color"].default_value), before))
    used = [s.name for s in bsdf.inputs if s.type == 'RGBA'
            and close(tuple(s.default_value), sw.linear_rgba(db["by_index"][4]))]
    check("next free colour input used", len(used) == 1, used)

    # node without colour inputs
    for n in tree.nodes:
        n.select = False
    out.select = True
    tree.nodes.active = out
    op = FakeOp(color_index=3)
    check("no colour input: CANCELLED", sw.SANZO_OT_apply_color.execute(op, ctx) == {'CANCELLED'})
    check("no colour input: warning", op.reports and op.reports[0][0] == 'WARNING', op.reports)

    # nothing selected -> active node
    for n in tree.nodes:
        n.select = False
    tree.nodes.active = rgb
    sw.SANZO_OT_apply_color.execute(FakeOp(color_index=5), ctx)
    check("no selection uses active node", close(tuple(rgb.outputs[0].default_value),
                                                 sw.linear_rgba(db["by_index"][5])))

    # distribute combination over selected nodes, left to right / top to bottom, cycling
    t2 = new_tree("dist")
    for n in list(t2.nodes):
        t2.nodes.remove(n)
    nodes = []
    for i, (x, y) in enumerate([(400, 0), (0, 0), (0, -300), (800, 0), (1200, 0)]):
        n = t2.nodes.new("ShaderNodeRGB")
        n.location = (x, y)
        n.select = True
        nodes.append(n)
    wm.sanzo_combo = 7
    ids = db["combos"][7]
    check("distribute: FINISHED", sw.SANZO_OT_apply_combo.execute(FakeOp(), fake_context(t2)) == {'FINISHED'})
    order = [nodes[1], nodes[2], nodes[0], nodes[3], nodes[4]]
    got = [tuple(n.outputs[0].default_value) for n in order]
    want = [sw.linear_rgba(db["by_index"][ids[i % len(ids)]]) for i in range(5)]
    check("distribute order and cycling", all(close(a, b) for a, b in zip(got, want)))
    for n in t2.nodes:
        n.select = False
    op = FakeOp()
    check("distribute with nothing selected cancels",
          sw.SANZO_OT_apply_combo.execute(op, fake_context(t2)) == {'CANCELLED'} and op.reports)


def test_octane(sw):
    wm = bpy.context.window_manager
    prefs = bpy.context.preferences.addons[MOD].preferences
    db = sw._DB
    c = db["by_index"][1]
    check("octane not detected by default", not sw.octane_available())
    scene = bpy.context.scene
    wm.sanzo_target = 'AUTO'
    check("auto + cycles -> blender nodes", not sw.use_octane(fake_context(scene=scene)))
    wm.sanzo_target = 'BLENDER'
    check("forced blender", not sw.use_octane(fake_context()))
    wm.sanzo_target = 'OCTANE'
    check("forced octane is requested", sw.octane_requested(fake_context()))

    # Octane chosen but not installed: Blender nodes are made, and the panel says so.
    tree = new_tree("oct0")
    check("octane requested", sw.octane_requested(fake_context()))
    check("octane requested but missing -> not used", not sw.use_octane(fake_context()))
    sw.SANZO_OT_add_rgb_node.execute(FakeOp(color_index=1), fake_context(tree))
    check("octane missing -> ShaderNodeRGB fallback", tree.nodes.active.bl_idname == "ShaderNodeRGB")
    wm.sanzo_combo = 1
    op = FakeOp(interpolation='LINEAR')
    sw.SANZO_OT_add_combo_ramp.execute(op, fake_context(tree))
    check("octane missing -> Blender ramp, no Octane warning",
          tree.nodes.active.bl_idname == "ShaderNodeValToRGB" and op.reports == [], op.reports)
    labels = [e[1] for e in draw(sw.SANZO_PT_colors, fake_context(tree)) if e[0] == "label"]
    check("panel says Octane is missing", "Octane not found: using Cycles / EEVEE nodes" in labels, labels[:4])
    check("panel does not claim Octane", "Nodes for: Octane" not in labels)
    wm.sanzo_target = 'BLENDER'
    labels = [e[1] for e in draw(sw.SANZO_PT_colors, fake_context(tree)) if e[0] == "label"]
    check("panel: blender target label", "Nodes for: Cycles / EEVEE" in labels, labels[:4])
    wm.sanzo_target = 'OCTANE'

    register_mock_octane()
    prefs.octane_rgb_node = "SWTestOctaneRGB"
    check("python-registered octane node detected", sw.octane_available())
    labels = [e[1] for e in draw(sw.SANZO_PT_colors, fake_context(tree)) if e[0] == "label"]
    check("panel: octane label", "Nodes for: Octane" in labels, labels[:4])
    op = FakeOp(interpolation='LINEAR')
    sw.SANZO_OT_add_combo_ramp.execute(op, fake_context(tree))
    check("octane without gradient node -> Blender ramp + warning",
          tree.nodes.active.bl_idname == "ShaderNodeValToRGB" and op.reports and op.reports[0][0] == 'WARNING',
          op.reports)
    prefs.octane_rgb_node = ""
    check("empty octane id -> not available", not sw.octane_available())
    prefs.octane_rgb_node = "SWTestOctaneRGB"
    wm.sanzo_target = 'AUTO'
    check("auto + non-octane engine -> blender", not sw.use_octane(fake_context()))
    wm.sanzo_target = 'OCTANE'
    tree = new_tree("oct1")
    sw.SANZO_OT_add_rgb_node.execute(FakeOp(color_index=1), fake_context(tree))
    node = tree.nodes.active
    check("octane rgb node created", node.bl_idname == "SWTestOctaneRGB", node.bl_idname)
    check("octane sRGB socket gets sRGB value", close(tuple(node.inputs[0].default_value), c["srgb"]),
          tuple(node.inputs[0].default_value))
    check("octane node label", node.label == c["name"])
    sw.SANZO_OT_add_combo_nodes.execute(FakeOp(), fake_context(tree))
    frame = next(n for n in tree.nodes if n.bl_idname == "NodeFrame")
    kids = [n.bl_idname for n in tree.nodes if n.parent == frame]
    check("octane palette frame", kids == ["SWTestOctaneRGB"] * len(db["combos"][1]), kids)

    p = tree.nodes.new("SWTestOctanePropNode")
    check("colour stored as node property", sw.set_node_color(p, c)
          and close(tuple(p.a_color), sw.linear_rgba(c)), tuple(p.a_color))
    check("node header colour untouched by prop fallback", not p.use_custom_color)
    prefs.octane_rgb_node = "DoesNotExist"
    check("bad octane id -> not available", not sw.octane_available())
    prefs.octane_rgb_node = "OctaneRGBColor"
    wm.sanzo_target = 'AUTO'


def test_misc_operators(sw):
    wm = bpy.context.window_manager
    db = sw._DB
    keys = sorted(db["combos"])
    wm.sanzo_combo = 1
    sw.SANZO_OT_set_combo.execute(FakeOp(combo=0, mode='PREV'), bpy.context)
    check("prev wraps to last", wm.sanzo_combo == keys[-1], wm.sanzo_combo)
    sw.SANZO_OT_set_combo.execute(FakeOp(combo=0, mode='NEXT'), bpy.context)
    check("next wraps to first", wm.sanzo_combo == keys[0], wm.sanzo_combo)
    sw.SANZO_OT_set_combo.execute(FakeOp(combo=0, mode='NEXT'), bpy.context)
    check("next", wm.sanzo_combo == 2)
    sw.SANZO_OT_set_combo.execute(FakeOp(combo=42, mode='SET'), bpy.context)
    check("set", wm.sanzo_combo == 42)
    seen = set()
    for _ in range(30):
        sw.SANZO_OT_set_combo.execute(FakeOp(combo=0, mode='RANDOM'), bpy.context)
        seen.add(wm.sanzo_combo)
    check("random stays in range and varies", seen <= set(keys) and len(seen) > 5, seen)

    sw.SANZO_OT_select_color.execute(FakeOp(color_index=100), bpy.context)
    check("select color", wm.sanzo_colors[wm.sanzo_active].idx == 100)
    check("active_color", sw.active_color(bpy.context)["index"] == 100)

    op = FakeOp(color_index=7)
    sw.SANZO_OT_copy_hex.execute(op, bpy.context)
    check("copy hex report", op.reports and db["by_index"][7]["hex"] in op.reports[0][1], op.reports)
    check("copy hex bad index cancels", sw.SANZO_OT_copy_hex.execute(FakeOp(color_index=0), bpy.context) == {'CANCELLED'})

    wm.sanzo_combo = 12
    sw.SANZO_OT_make_palette.execute(FakeOp(), bpy.context)
    pal = bpy.data.palettes.get("Sanzo Wada 012")
    want = [db["by_index"][i]["srgb"] for i in db["combos"][12]]
    check("palette created", pal is not None and len(pal.colors) == len(want))
    check("palette colours", pal and all(close(tuple(a.color), b) for a, b in zip(pal.colors, want)))
    pal.colors.new()
    sw.SANZO_OT_make_palette.execute(FakeOp(), bpy.context)
    check("palette rebuilt, not duplicated", len(pal.colors) == len(want)
          and len([p for p in bpy.data.palettes if p.name.startswith("Sanzo Wada 012")]) == 1)
    wm.sanzo_combo = 999
    check("palette for missing combo cancels", sw.SANZO_OT_make_palette.execute(FakeOp(), bpy.context) == {'CANCELLED'})
    wm.sanzo_combo = 1


def test_drawing(sw):
    wm = bpy.context.window_manager
    tree = new_tree("draw")
    wm.sanzo_active = 0
    log = draw(sw.SANZO_PT_colors, fake_context(tree))
    bad = [e for e in log if e[0].startswith("BAD")]
    check("colors panel: valid API calls", not bad, bad)
    check("colors panel: list", ("list", "SANZO_UL_colors", wm, "sanzo_colors", "sanzo_active") in
          [e for e in log if e[0] == "list"])
    labels = [e[1] for e in log if e[0] == "label"]
    check("colors panel: counts label", "159 colors · 348 combinations" in labels, labels[:3])
    check("colors panel: details", "1 · Hermosa Pink" in labels and "#ffb3f0" in labels)
    ops = [e[1] for e in log if e[0] == "op"]
    combos_of_1 = sw._DB["by_index"][1]["combinations"]
    check("colors panel: one button per combination", ops.count("sanzo.set_combo") == len(combos_of_1))
    check("colors panel: node buttons", "sanzo.add_rgb_node" in ops and "sanzo.apply_color" in ops)
    check("colors panel: no tree hint absent with tree",
          "Open a material/world to add nodes" not in labels)
    log = draw(sw.SANZO_PT_colors, fake_context(None))
    check("colors panel: hint without tree",
          "Open a material/world to add nodes" in [e[1] for e in log if e[0] == "label"])

    wm.sanzo_combo = 3
    log = draw(sw.SANZO_PT_combinations, fake_context(tree))
    bad = [e for e in log if e[0].startswith("BAD")]
    check("combos panel: valid API calls", not bad, bad)
    swatches = [e for e in log if e[0] == "prop" and e[1] == "color"]
    check("combos panel: one swatch per color", len(swatches) == len(sw._DB["combos"][3]))
    # the swatches must be the list items of exactly those colors, in order
    got = [e[1] for e in log if e[0] == "swatch"]
    check("combos panel: swatches are the combination's colors", got == sw._DB["combos"][3], got)
    ops = [e[1] for e in log if e[0] == "op"]
    for o in ("sanzo.add_combo_nodes", "sanzo.add_combo_ramp", "sanzo.apply_combo", "sanzo.make_palette"):
        check("combos panel: " + o, o in ops)
    wm.sanzo_combo = 999
    log = draw(sw.SANZO_PT_combinations, fake_context(tree))
    check("combos panel: unknown number message",
          "No combination with this number" in [e[1] for e in log if e[0] == "label"])
    wm.sanzo_combo = 1

    lay_log = []
    sw.SANZO_UL_colors.draw_item(None, bpy.context, FakeLayout(lay_log), wm, wm.sanzo_colors[0],
                                 0, wm, "sanzo_active", 0)
    labels = [e[1] for e in lay_log if e[0] == "label"]
    check("list row", "1  Hermosa Pink" in labels and "#ffb3f0" in labels, labels)
    check("list row swatch", ("prop", "color", "") in lay_log)
    bad = [e for e in lay_log if e[0].startswith("BAD")]
    check("list row: valid API calls", not bad, bad)

    prefs = bpy.context.preferences.addons[MOD].preferences
    log = []

    class PrefSelf:  # the real preferences, with a fake layout
        layout = FakeLayout(log)

        def __getattr__(self, name):
            return getattr(prefs, name)

    sw.SANZO_AddonPreferences.draw(PrefSelf(), bpy.context)
    labels = [e[1] for e in log if e[0] == "label"]
    check("prefs draw", "159 colors, 348 combinations" in labels, labels)


def test_custom_library(sw):
    wm = bpy.context.window_manager
    prefs = bpy.context.preferences.addons[MOD].preferences
    tmp = tempfile.mkdtemp(prefix="sw_json_")
    # list form, rgb_array only (no hex), missing use_count
    lib = [
        {"index": 2, "name": "Blue", "rgb_array": [0, 0, 255], "combinations": [1, 2]},
        {"index": 1, "name": "Red", "hex": "#FF0000", "combinations": [2, 1]},
        {"index": 3, "name": "Grey", "rgb_array": [128, 128, 128]},
    ]
    p = os.path.join(tmp, "lib.json")
    json.dump(lib, open(p, "w"))
    prefs.json_path = p  # update callback reloads
    db = sw._DB
    check("custom lib loaded", db["path"] == p and len(db["colors"]) == 3 and db["error"] == "", db["error"])
    check("custom lib sorted", [c["index"] for c in db["colors"]] == [1, 2, 3])
    check("custom lib hex from rgb", db["by_index"][2]["hex"] == "#0000ff")
    check("custom lib hex lowercased", db["by_index"][1]["hex"] == "#ff0000")
    check("custom lib combos", db["combos"] == {1: [1, 2], 2: [1, 2]}, db["combos"])
    check("custom lib use_count default", db["by_index"][1]["use_count"] == 2 and db["by_index"][3]["use_count"] == 0)
    check("wm mirror follows", len(wm.sanzo_colors) == 3)
    wm.sanzo_active = 2

    bad = os.path.join(tmp, "bad.json")
    open(bad, "w").write("{not json")
    prefs.json_path = bad
    check("bad json -> error kept", db["error"] != "" and db["colors"] == [] and db["combos"] == {}, db["error"])
    check("bad json -> wm emptied", len(wm.sanzo_colors) == 0)
    log = draw(sw.SANZO_PT_colors, fake_context(new_tree("err")))
    check("panel shows error", any(e[0] == "label" and e[1] == db["error"] for e in log))
    log = draw(sw.SANZO_PT_combinations, fake_context(None))
    check("combos panel without library", "No library loaded" in [e[1] for e in log if e[0] == "label"])
    op = FakeOp()
    check("reload with bad file cancels", sw.SANZO_OT_reload.execute(op, bpy.context) == {'CANCELLED'}
          and op.reports[0][0] == 'ERROR', op.reports)

    prefs.json_path = ""
    check("back to bundled", db["path"] == sw.BUNDLED_JSON and len(db["colors"]) == 159)
    check("active index clamped after shrink/grow", 0 <= wm.sanzo_active < len(wm.sanzo_colors))
    op = FakeOp()
    check("reload ok", sw.SANZO_OT_reload.execute(op, bpy.context) == {'FINISHED'} and "159" in op.reports[0][1])


def test_load_post(sw):
    wm = bpy.context.window_manager
    wm.sanzo_colors.clear()
    sw._on_load_post()
    check("load_post refills wm list", len(wm.sanzo_colors) == 159)
    # End to end: the list is not saved in the .blend, and is back after opening it.
    path = os.path.join(os.environ.get("SW_PROFILE", tempfile.gettempdir()), "sw_test.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    check("list not written into .blend", b"Hermosa Pink" not in open(path, "rb").read())
    bpy.ops.wm.open_mainfile(filepath=path)
    check("list refilled after opening a file", len(bpy.context.window_manager.sanzo_colors) == 159,
          len(bpy.context.window_manager.sanzo_colors))
    check("swatches still work after load",
          close(tuple(bpy.context.window_manager.sanzo_colors[0].color), sw._DB["by_index"][1]["srgb"]))


def test_reenable():
    for cycle in (1, 2):
        addon_utils.disable(MOD, default_set=True)
        check(f"disable {cycle}: handler removed",
              not any(getattr(h, "__name__", "") == "_on_load_post" for h in bpy.app.handlers.load_post))
        check(f"disable {cycle}: wm props removed",
              "sanzo_colors" not in bpy.types.WindowManager.bl_rna.properties)
        check(f"disable {cycle}: classes removed", not hasattr(bpy.types, "SANZO_PT_colors"))
        addon_utils.enable(MOD, default_set=True)
        n = sum(1 for h in bpy.app.handlers.load_post if getattr(h, "__name__", "") == "_on_load_post")
        check(f"enable {cycle}: single handler", n == 1, n)
    sw = sys.modules[MOD]
    bpy.app.timers.unregister(sw._deferred_init)
    sw._deferred_init()
    check("re-enabled library works", len(bpy.context.window_manager.sanzo_colors) == 159)


def main():
    try:
        addon_utils.enable(MOD, default_set=True)
        sw = importlib.import_module(MOD)
    except Exception:
        check("enable add-on", False, traceback.format_exc())
        sw = None
    if sw:
        for fn in (test_registration, test_library, test_color_math, test_swatch_property,
                   test_poll_and_context, test_blender_nodes, test_apply, test_octane,
                   test_misc_operators, test_drawing, test_custom_library, test_load_post):
            try:
                fn(sw)
            except Exception:
                check(fn.__name__ + " crashed", False, traceback.format_exc())
        try:
            test_reenable()
        except Exception:
            check("test_reenable crashed", False, traceback.format_exc())
    failed = [r for r in RESULTS if not r[1]]
    print("\n%d checks, %d failed" % (len(RESULTS), len(failed)))
    for name, _, detail in failed:
        print("FAILED:", name, detail)
    sys.stdout.flush()
    os._exit(1 if failed else 0)


main()
