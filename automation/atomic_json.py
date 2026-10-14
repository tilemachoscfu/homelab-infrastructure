"""Publish private JSON snapshots without exposing partially written files."""

import json
import os
from pathlib import Path
import tempfile


def write_json(path, value, *, indent=None):
    path = Path(path)
    # Same-directory staging keeps replace atomic on the destination filesystem.
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=indent)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
