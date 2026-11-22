"""Build the installable extension zip: dist/sanzo_wada_colors-<version>.zip

Usage (any Python 3.9+, repo root):
    python3 tools/build_package.py --blender /Applications/Blender.app/Contents/MacOS/Blender

It copies sanzo_wada_colors/ plus the repo LICENSE into dist/stage/, removes
caches, validates the manifest and builds the zip with Blender's own
"extension build" command. Blender runs with --factory-startup and a scratch
user profile inside dist/, so your real Blender settings are never touched.
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    ap.add_argument("--output-dir", default=os.path.join(ROOT, "dist"))
    args = ap.parse_args()
    blender = find_blender(args.blender)

    out = os.path.abspath(args.output_dir)
    stage = os.path.join(out, "stage", PKG)
    shutil.rmtree(os.path.join(out, "stage"), ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, PKG), stage,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(os.path.join(ROOT, "LICENSE"), os.path.join(stage, "LICENSE"))

    profile = os.path.join(out, "profile")
    env = dict(os.environ)
    env.update({
        "BLENDER_USER_RESOURCES": profile,
        "BLENDER_USER_CONFIG": os.path.join(profile, "config"),
        "BLENDER_USER_SCRIPTS": os.path.join(profile, "scripts"),
        "BLENDER_USER_EXTENSIONS": os.path.join(profile, "extensions"),
    })
    base = [blender, "--factory-startup", "--command", "extension"]
    subprocess.run(base + ["validate", stage], check=True, env=env)
    subprocess.run(base + ["build", "--source-dir", stage, "--output-dir", out], check=True, env=env)
    zips = sorted(f for f in os.listdir(out) if f.endswith(".zip"))
    print("built:", ", ".join(os.path.join(out, z) for z in zips))


if __name__ == "__main__":
    sys.exit(main())
