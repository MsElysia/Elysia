"""Package only the restricted console runtime from a clean committed tree."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New ZIP outside this checkout")
    args = parser.parse_args()
    target = args.output.absolute()
    if target.exists() or ROOT == target or ROOT in target.parents:
        parser.error("Choose a new output file outside the source checkout")
    if git("status", "--porcelain", "--untracked-files=normal"):
        parser.error("Commit or preserve working changes before packaging")
    commit = git("rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        parser.error("Canonical full source commit required")
    closure = ast.parse((ROOT / "tests/test_canonical_windows_app.py").read_text(encoding="utf-8"))
    files = next(ast.literal_eval(node.value) for node in closure.body
                 if isinstance(node, ast.Assign) and any(
                     isinstance(t, ast.Name) and t.id == "FILES" for t in node.targets))
    files = (*files, "tests/test_canonical_windows_app.py", "tests/test_delivery_runtime.py",
             "WINDOWS_LOCAL_CANDIDATE.md")
    contents = {}
    for name in sorted(set(files)):
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or path.resolve() != path:
            parser.error("Noncanonical source path: " + name)
        # Package committed bytes, not an accidentally changed working file.
        contents[name] = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=ROOT)
        if contents[name] != path.read_bytes():
            parser.error("Source changed during packaging: " + name)
    manifest = {"source_commit": commit, "release_status": "STOP",
                "scope": "restricted console; fictional memory; no model/provider/autonomy",
                "windows_verified": False,
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}}
    contents["SOURCE_MANIFEST.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    # Reopen and verify the actual delivery bytes before reporting completion.
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(contents)
        for name, data in contents.items():
            assert archive.read(name) == data
    print(json.dumps({"file": str(target), "source_commit": commit,
                      "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                      "files": len(contents), "windows_verified": False}, indent=2))


if __name__ == "__main__":
    main()
