## What this changes

<!-- What does the pull request do, and why? Link the issue it fixes, e.g. "Fixes #12". -->

## How it was tested

- [ ] Test suite passes in an isolated Blender 5.3, both load modes (`python3 tests/run_blender.py` and `--legacy`, each ends with `0 failed`)
- [ ] For a bug fix: a new check in `tests/test_sanzo.py` that fails without the fix
- [ ] Behaviour compared with the previous version (`tests/probe_behaviour.py` + `tests/compare_probes.py`), every difference explained
- [ ] Tried by hand in Blender if it changes the panel (and with Octane, if it touches Octane code)

## Checklist

- [ ] Comments match the code (operator and panel docstrings are tooltips: use `#` comments there)
- [ ] Draw code only reads data
- [ ] README updated if users will notice the change
