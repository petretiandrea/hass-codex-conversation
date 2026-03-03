#!/usr/bin/env python3
"""Sync manifest.json version from pyproject.toml.

Called by python-semantic-release as build_command after bumping
pyproject.toml. Since psr does `git add -u` before the version commit,
the manifest change is included in the same release commit.
"""

import json
from pathlib import Path
import tomllib

root = Path(__file__).parent.parent

with open(root / "pyproject.toml", "rb") as f:
    version = tomllib.load(f)["project"]["version"]

manifest_path = root / "custom_components" / "codex_conversation" / "manifest.json"
data = json.loads(manifest_path.read_text())
data["version"] = version
manifest_path.write_text(json.dumps(data, indent=2) + "\n")

print(f"Synced manifest.json → {version}")
