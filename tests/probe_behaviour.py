"""Record the add-on's observable behaviour as JSON, for old/new comparisons.

    python3 tests/run_blender.py tests/probe_behaviour.py -- new.json
    python3 tests/run_blender.py --addon-root OLD_COPY tests/probe_behaviour.py -- old.json
    python3 tests/compare_probes.py old.json new.json

Covers: the parsed library and window-manager list; RGB nodes for all 159
colors (Blender and mocked Octane); palette frames and Color Ramps for all
348 combinations in every interpolation; applying a color to every shader
node type Blender can create; distributing combinations over node layouts;
seeded random combination browsing; palettes; panel draw output for several
selections; custom and broken library files.
"""

import importlib
import json
import os
import random
import sys
import tempfile
import traceback
import types

import addon_utils
import bpy

MOD = os.environ.get("SW_MODULE", "bl_ext.user_default.sanzo_wada_colors")
OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv and len(sys.argv) > sys.argv.index("--") + 1 else "probe.json"
SEED = 1234


def r6(v):
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, (list, tuple)):
        return [r6(x) for x in v]
    return v


class Recorder:
    def __init__(self, log):
        self.__dict__["log"] = log

    def __getattr__(self, name):
        log = self.log

        def call(*args, **kw):
            entry = [name]
            if name == "prop":
                entry += [args[1], r6(list(getattr(args[0], args[1])))
                          if args[1] == "color" else str(getattr(args[0], args[1]))]
            elif name in ("operator", "template_list"):
                entry.append(args[0])
            for k in sorted(kw):
                entry.append(f"{k}={kw[k]}")
            log.append(entry)
            if name == "operator":
                ns = types.SimpleNamespace()
                log.append(["opprops", ns])
                return ns
            return Recorder(log)
        return call

    def __setattr__(self, name, value):
        self.log.append(["set", name, repr(value)])


def draw(cls, ctx):
    log = []
    cls.draw(types.SimpleNamespace(layout=Recorder(log)), ctx)
    return [e if e[0] != "opprops" else ["opprops", sorted(vars(e[1]).items())] for e in log]


def fake_context(tree=None):
    space = types.SimpleNamespace(type="NODE_EDITOR", tree_type="ShaderNodeTree", edit_tree=tree)
    return types.SimpleNamespace(space_data=space, window_manager=bpy.context.window_manager,
                                 scene=bpy.context.scene, preferences=bpy.context.preferences)


class FakeOp:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.reports = []

    def report(self, kind, msg):
        self.reports.append([sorted(kind)[0], msg])


def empty_tree(name):
    mat = bpy.data.materials.new(name)
    tree = mat.node_tree
    for n in list(tree.nodes):
        tree.nodes.remove(n)
    return tree


def node_state(n):
    d = {"type": n.bl_idname, "label": n.label, "custom": n.use_custom_color,
         "header": r6(list(n.color)), "loc": r6(list(getattr(n, "location_absolute", n.location))),
         "parent": n.parent.label if n.parent else None, "select": n.select}
    socks = []
    for s in list(n.inputs) + list(n.outputs):
        if hasattr(s, "default_value"):
            try:
                v = s.default_value
                socks.append([s.identifier, r6(list(v)) if hasattr(v, "__len__") and not isinstance(v, str) else r6(v)])
            except Exception:
                pass
    d["sockets"] = socks
    if hasattr(n, "color_ramp") and n.color_ramp:
        d["ramp"] = [n.color_ramp.interpolation,
                     [[r6(e.position), r6(list(e.color))] for e in n.color_ramp.elements]]
    return d


def register_mock_octane():
    class SWProbeSocket(bpy.types.NodeSocket):
        bl_idname = "SWProbeSocket"
        default_value: bpy.props.FloatVectorProperty(subtype='COLOR_GAMMA', size=3)

        def draw(self, c, l, n, t):
            pass

        def draw_color(self, c, n):
            return (1, 1, 0, 1)

    class SWProbeOctaneRGB(bpy.types.ShaderNode):
        bl_idname = "SWProbeOctaneRGB"
        bl_label = "RGB Color"

        def init(self, ctx):
            self.inputs.new("SWProbeSocket", "Color")
            self.outputs.new("NodeSocketColor", "Out")

    for c in (SWProbeSocket, SWProbeOctaneRGB):
        bpy.utils.register_class(c)


def probe(sw):
    out = {}
    wm = bpy.context.window_manager
    db = sw._DB
    prefs = bpy.context.preferences.addons[MOD].preferences
    out["library"] = {str(c["index"]): {k: r6(list(v)) if isinstance(v, (list, tuple)) else v
                                        for k, v in c.items()} for c in db["colors"]}
    out["combos"] = {str(k): v for k, v in sorted(db["combos"].items())}
    out["wm_items"] = [[it.name, it.idx, it.label, it.hex, r6(list(it.color))] for it in wm.sanzo_colors]
    out["linear"] = {str(c["index"]): r6(list(sw.linear_rgba(c))) for c in db["colors"]}

    # RGB nodes for every color, Blender target
    wm.sanzo_target = 'BLENDER'
    tree = empty_tree("rgb")
    res = {}
    for c in db["colors"]:
        op = FakeOp(color_index=c["index"])
        r = sorted(sw.SANZO_OT_add_rgb_node.execute(op, fake_context(tree)))
        res[str(c["index"])] = [r, op.reports, node_state(tree.nodes.active)]
    out["rgb_nodes"] = res

    # Frames and ramps for every combination
    frames, ramps = {}, {}
    for n in sorted(db["combos"]):
        wm.sanzo_combo = n
        tree = empty_tree("c%d" % n)
        op = FakeOp()
        r = sorted(sw.SANZO_OT_add_combo_nodes.execute(op, fake_context(tree)))
        frames[str(n)] = [r, op.reports, sorted((node_state(x) for x in tree.nodes),
                                                key=lambda d: (d["type"], d["loc"]))]
        for interp in ('CONSTANT', 'LINEAR', 'EASE'):
            op = FakeOp(interpolation=interp)
            r = sorted(sw.SANZO_OT_add_combo_ramp.execute(op, fake_context(tree)))
            ramps[f"{n}/{interp}"] = [r, op.reports, node_state(tree.nodes.active)]
    out["frames"], out["ramps"] = frames, ramps

    # Apply a colour to every shader node type Blender can create
    applied = {}
    idnames = sorted({c.bl_rna.identifier for c in bpy.types.ShaderNode.__subclasses__()}
                     | {t.bl_rna.identifier for t in bpy.types.Node.__subclasses__()})
    cand = [name for name in dir(bpy.types) if name.startswith("ShaderNode")]
    tree = empty_tree("all")
    for idname in sorted(set(cand) | set(i for i in idnames if i.startswith("ShaderNode"))):
        try:
            node = tree.nodes.new(idname)
        except Exception:
            continue
        before = node_state(node)
        ok = sw.set_node_color(node, db["by_index"][(len(applied) % 159) + 1])
        applied[idname] = [ok, before["sockets"] != node_state(node)["sockets"], node_state(node)["sockets"]]
    out["apply_all_types"] = applied

    # Apply operator: selection / active fallback
    tree = bpy.data.materials.new("ap").node_tree
    for n in tree.nodes:
        n.select = False
    op = FakeOp(color_index=9)
    r = sorted(sw.SANZO_OT_apply_color.execute(op, fake_context(tree)))
    out["apply_op_active"] = [r, op.reports, [node_state(n) for n in sorted(tree.nodes, key=lambda n: n.bl_idname)]]

    # Distribute: random layouts
    rng = random.Random(SEED)
    dist = []
    for trial in range(40):
        tree = empty_tree("d%d" % trial)
        k = rng.randint(1, 7)
        for i in range(k):
            t = rng.choice(["ShaderNodeRGB", "ShaderNodeBsdfDiffuse", "ShaderNodeEmission",
                            "ShaderNodeMix", "ShaderNodeMath"])
            nd = tree.nodes.new(t)
            nd.location = (rng.choice([0, 30, 200, 400, 410]), rng.choice([0, -100, -300, 50]))
            nd.select = rng.random() < 0.8
        wm.sanzo_combo = rng.randint(1, 348)
        op = FakeOp()
        r = sorted(sw.SANZO_OT_apply_combo.execute(op, fake_context(tree)))
        dist.append([wm.sanzo_combo, r, op.reports,
                     [node_state(n) for n in sorted(tree.nodes, key=lambda n: (n.bl_idname, tuple(n.location)))]])
    out["distribute"] = dist

    # Combination browsing (random mode uses the global random module)
    random.seed(SEED)
    seq = []
    for step in range(200):
        mode = rng.choice(['SET', 'PREV', 'NEXT', 'RANDOM'])
        combo = rng.randint(-5, 360)
        try:
            r = sorted(sw.SANZO_OT_set_combo.execute(FakeOp(combo=combo, mode=mode), bpy.context))
        except Exception as ex:
            r = ["EXC", type(ex).__name__]
        seq.append([mode, combo, r, wm.sanzo_combo])
    out["browse"] = seq

    # Palettes
    pals = {}
    for n in (1, 50, 348, 999):
        wm.sanzo_combo = n
        op = FakeOp()
        r = sorted(sw.SANZO_OT_make_palette.execute(op, bpy.context))
        p = bpy.data.palettes.get("Sanzo Wada %03d" % n)
        pals[str(n)] = [r, op.reports, [r6(list(c.color)) for c in p.colors] if p else None]
    out["palettes"] = pals

    # Copy hex / select colour
    hexes = []
    for i in (0, 1, 80, 159, 160):
        op = FakeOp(color_index=i)
        hexes.append([i, sorted(sw.SANZO_OT_copy_hex.execute(op, bpy.context)), op.reports])
        sw.SANZO_OT_select_color.execute(FakeOp(color_index=i), bpy.context)
        hexes.append(["active", wm.sanzo_active])
    out["copy_select"] = hexes

    # Panels
    panels = {}
    tree = bpy.data.materials.new("pn").node_tree
    for active in (0, 5, 77, 158):
        for combo in (1, 99, 348, 500):
            wm.sanzo_active, wm.sanzo_combo = active, combo
            for tgt in ('AUTO', 'BLENDER', 'OCTANE'):
                wm.sanzo_target = tgt
                for t in (tree, None):
                    key = f"{active}/{combo}/{tgt}/{'tree' if t else 'none'}"
                    panels[key] = [draw(sw.SANZO_PT_colors, fake_context(t)),
                                   draw(sw.SANZO_PT_combinations, fake_context(t))]
    out["panels"] = panels
    rows = []
    for it in list(wm.sanzo_colors)[::10]:
        log = []
        sw.SANZO_UL_colors.draw_item(None, bpy.context, Recorder(log), wm, it, 0, wm, "sanzo_active", 0)
        rows.append(log)
    out["list_rows"] = rows

    # Octane (mocked)
    register_mock_octane()
    prefs.octane_rgb_node = "SWProbeOctaneRGB"
    wm.sanzo_target = 'OCTANE'
    oct_ = {}
    tree = empty_tree("oct")
    for c in db["colors"][::7]:
        sw.SANZO_OT_add_rgb_node.execute(FakeOp(color_index=c["index"]), fake_context(tree))
        oct_[str(c["index"])] = node_state(tree.nodes.active)
    for n in (1, 2, 300):
        wm.sanzo_combo = n
        t2 = empty_tree("of%d" % n)
        sw.SANZO_OT_add_combo_nodes.execute(FakeOp(), fake_context(t2))
        op = FakeOp(interpolation='LINEAR')
        sw.SANZO_OT_add_combo_ramp.execute(op, fake_context(t2))
        oct_["frame%d" % n] = [op.reports, sorted((node_state(x) for x in t2.nodes),
                                                  key=lambda d: (d["type"], d["loc"]))]
    out["octane"] = oct_
    prefs.octane_rgb_node = "OctaneRGBColor"
    wm.sanzo_target = 'AUTO'

    # Custom and broken libraries
    tmp = tempfile.mkdtemp(prefix="sw_probe_")
    libs = {
        "list": [{"index": 3, "name": "C", "rgb_array": [1, 2, 3], "combinations": [5]},
                 {"index": 1, "name": "A", "hex": "#ABCDEF", "combinations": [5, 1]}],
        "dict": {"colors": [{"index": 1, "hex": "#000000"}]},
        "broken": "{nope",
        "missing_key": [{"name": "no index"}],
    }
    custom = {}
    for name, data in libs.items():
        p = os.path.join(tmp, name + ".json")
        with open(p, "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        prefs.json_path = p
        custom[name] = [db["error"] != "", [[c["index"], c["name"], c["hex"], r6(list(c["srgb"])),
                                             c["combinations"], c["use_count"]] for c in db["colors"]],
                        {str(k): v for k, v in db["combos"].items()}, len(wm.sanzo_colors)]
    prefs.json_path = ""
    out["custom_libraries"] = custom
    out["restored"] = [len(db["colors"]), db["path"] == sw.BUNDLED_JSON]
    return out


def main():
    try:
        addon_utils.enable(MOD, default_set=True)
        sw = importlib.import_module(MOD)
        if bpy.app.timers.is_registered(sw._deferred_init):
            bpy.app.timers.unregister(sw._deferred_init)
        sw._deferred_init()
        data = probe(sw)
        code = 0
    except Exception:
        data = {"crash": traceback.format_exc()}
        code = 1
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=0, sort_keys=True)
    print("probe written:", OUT, "crash" if code else "ok")
    sys.stdout.flush()
    os._exit(code)


main()
