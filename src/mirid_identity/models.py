"""Pinned face-model assets. Inference never downloads assets implicitly."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from importlib.resources import files
from pathlib import Path


class ModelError(RuntimeError):
    """A required model is absent, invalid or could not be obtained."""


def manifest() -> dict:
    return json.loads(files("mirid_identity").joinpath("model-manifest.json").read_text())


def default_model_dir() -> Path:
    configured = os.environ.get("MIRID_IDENTITY_MODEL_DIR")
    if configured:
        return Path(configured).expanduser()
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return cache / "mirid-identity" / "models"


def _check(path: Path, model: dict) -> str:
    if not path.is_file():
        return "missing"
    if path.stat().st_size != model["bytes"]:
        return "size_mismatch"
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "ready" if digest.hexdigest() == model["sha256"] else "checksum_mismatch"


def model_status(model_dir: str | Path | None = None) -> dict:
    """Read local files only; return readiness with no biometric information."""
    directory = Path(model_dir) if model_dir is not None else default_model_dir()
    models = []
    for model in manifest()["models"]:
        try:
            state = _check(directory / model["filename"], model)
        except OSError:
            state = "unreadable"
        models.append({"id": model["id"], "role": model["role"], "state": state,
                       "sha256": model["sha256"], "license": model["license"]})
    return {"ready": all(model["state"] == "ready" for model in models),
            "model_dir": str(directory), "models": models}


def verified_paths(model_dir: str | Path | None = None) -> dict[str, Path]:
    directory = Path(model_dir) if model_dir is not None else default_model_dir()
    state = model_status(directory)
    if not state["ready"]:
        failures = ", ".join(f'{item["id"]}: {item["state"]}' for item in state["models"]
                             if item["state"] != "ready")
        raise ModelError(f"Face models are not ready ({failures}). Run mirid-identity models download.")
    return {item["role"]: directory / item["filename"] for item in manifest()["models"]}


def download_models(model_dir: str | Path | None = None) -> dict:
    """Explicit model download; atomically publish only verified pinned bytes.

    Temporary files contain public model weights only, never face images.
    Existing valid models are not fetched again. Partial downloads are removed.
    """
    directory = Path(model_dir) if model_dir is not None else default_model_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for model in manifest()["models"]:
        destination = directory / model["filename"]
        if _check(destination, model) == "ready":
            continue
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".model-", delete=False) as output:
                temporary = Path(output.name)
            # curl handles a wider range of proxy and HTTP/2 environments.
            # No shell is involved; URLs and sizes come only from our manifest.
            curl = shutil.which("curl")
            if curl:
                subprocess.run([curl, "--fail", "--silent", "--show-error", "--location",
                                "--proto", "=https", "--proto-redir", "=https",
                                "--connect-timeout", "20", "--max-time", "180", "--retry", "2",
                                "--max-filesize", str(model["bytes"]), "--output", str(temporary),
                                model["url"]], check=True, capture_output=True, timeout=570)
            else:
                request = urllib.request.Request(model["url"], headers={"User-Agent": "Mirid-Identity/0.1", "Accept-Encoding": "identity"})
                with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
                    if not response.geturl().startswith("https://"):
                        raise ModelError("The model server redirected away from HTTPS.")
                    received = 0
                    while chunk := response.read(1024 * 1024):
                        received += len(chunk)
                        if received > model["bytes"]:
                            raise ModelError(f'Model download exceeded its pinned size: {model["id"]}')
                        output.write(chunk)
            state = _check(temporary, model)
            if state != "ready":
                received_size = temporary.stat().st_size
                raise ModelError(f'Model verification failed: {model["id"]} ({state}; '
                                 f'received {received_size} of {model["bytes"]} bytes)')
            temporary.replace(destination)
        except ModelError:
            raise
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise ModelError(f'Could not download {model["id"]}: {exc.__class__.__name__}') from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return model_status(directory)
