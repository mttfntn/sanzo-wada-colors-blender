"""Run a test script inside an isolated, headless Blender.

Usage (repo root):
    python3 tests/run_blender.py                                  # runs tests/test_sanzo.py
    python3 tests/run_blender.py tests/probe_behaviour.py -- out.json
    python3 tests/run_blender.py --addon-root PATH ...            # test another copy of the add-on
    python3 tests/run_blender.py --legacy                         # load as a legacy add-on instead

Isolation: Blender runs with --background --factory-startup and every
BLENDER_USER_* folder pointing at a fresh temporary profile. The add-on is
copied into that profile's extension repository (user_default), so it loads
exactly like an installed extension (module bl_ext.user_default.sanzo_wada_colors),
while your real profile, installed add-ons and open Blender sessions are never
touched. The profile is deleted afterwards. With --legacy the package goes into
scripts/addons instead (module sanzo_wada_colors), which checks that the
add-on also works when loaded the old way (different __package__).

The Blender executable is taken from --blender, the BLENDER environment
variable, the default macOS / Windows install path, or `blender` on PATH.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PKG = "sanzo_wada_colors"
DEFAULTS = (
    "/Applications/Blender.app/Contents/MacOS/Blender",
    r"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe",
)


def find_blender(explicit):
    for cand in (explicit, os.environ.get("BLENDER"), *DEFAULTS, shutil.which("blender")):
        if cand and os.path.isfile(cand):
            return cand
    sys.exit("Blender not found: pass --blender PATH or set BLENDER")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender")
    ap.add_argument("--addon-root", default=REPO, help="folder that contains the sanzo_wada_colors package")
    ap.add_argument("--legacy", action="store_true", help="install as a legacy add-on (scripts/addons)")
    ap.add_argument("script", nargs="?", default=os.path.join(HERE, "test_sanzo.py"))
    ap.add_argument("script_args", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    blender = find_blender(a.blender)
    profile = tempfile.mkdtemp(prefix="sw_profile_")
    dest = (os.path.join(profile, "scripts", "addons", PKG) if a.legacy
            else os.path.join(profile, "extensions", "user_default", PKG))
    shutil.copytree(os.path.join(a.addon_root, PKG), dest,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    env = dict(
        os.environ,
        BLENDER_USER_RESOURCES=profile,
        BLENDER_USER_CONFIG=os.path.join(profile, "config"),
        BLENDER_USER_SCRIPTS=os.path.join(profile, "scripts"),
        BLENDER_USER_EXTENSIONS=os.path.join(profile, "extensions"),
        SW_PROFILE=profile,
        SW_MODULE=PKG if a.legacy else "bl_ext.user_default." + PKG,
    )
    extra = [x for x in a.script_args if x != "--"]
    cmd = [blender, "--background", "--factory-startup", "--python-exit-code", "1",
           "--python", os.path.abspath(a.script), "--", *extra]
    try:
        return subprocess.call(cmd, env=env)
    finally:
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
