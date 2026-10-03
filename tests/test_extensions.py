import json
from pathlib import Path

import pytest

from mathlab.extensions import ExtensionRegistry


@pytest.mark.asyncio
async def test_hot_extension(tmp_path: Path):
    root = tmp_path / ".mathlab" / "extensions"
    root.mkdir(parents=True)
    (root / "double.py").write_text(
        "import json,sys\nx=json.load(sys.stdin)\nprint(json.dumps({'value':2*x['value']}))\n"
    )
    (root / "manifest.json").write_text(json.dumps({"tools": {"double": {"description": "double", "entrypoint": "double.py"}}}))
    reg = ExtensionRegistry(tmp_path)
    result = await reg.run("double", {"value": 7})
    assert result["ok"]
    assert result["result"]["value"] == 14
