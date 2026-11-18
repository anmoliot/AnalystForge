"""Validate mirrors of the authoritative root project version before a release."""

import ast
import json
import os
import tomllib
from pathlib import Path


def main() -> None:
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    manifests = list(Path("packages").glob("*/pyproject.toml")) + list(
        Path("apps").glob("*/pyproject.toml")
    )
    for path in manifests:
        assert tomllib.loads(path.read_text())["project"]["version"] == version, str(path)
    assert json.loads(Path("apps/web/package.json").read_text())["version"] == version
    for path in Path("apps").glob("*/src/analystforge/*/__init__.py"):
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets
            ):
                assert ast.literal_eval(node.value) == version, str(path)
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if tag.startswith("v"):
        assert tag == "v" + version, "Release tag must match root pyproject.toml"
    print(version)


if __name__ == "__main__":
    main()
