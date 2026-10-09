import hashlib
import io
from pathlib import Path

import pytest

from mirid_identity import models


@pytest.fixture
def tiny_manifest(monkeypatch):
    body = b"a checked public model fixture"
    manifest = {"models": [{"id": "fixture", "role": "detector", "filename": "fixture.onnx",
                            "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                            "license": "MIT", "url": "https://example.invalid/fixture.onnx"}]}
    monkeypatch.setattr(models, "manifest", lambda: manifest)
    monkeypatch.setattr(models.shutil, "which", lambda _: None)
    return body


def test_manifest_has_pinned_revision_and_separate_licences():
    manifest = models.manifest()
    assert len(manifest["source_revision"]) == 40
    assert {entry["license"] for entry in manifest["models"]} == {"MIT", "Apache-2.0"}
    for entry in manifest["models"]:
        assert manifest["source_revision"] in entry["url"]
        assert len(entry["sha256"]) == 64
        assert models.files("mirid_identity").joinpath(entry["license_file"]).is_file()


def test_missing_models_do_not_download(tmp_path, monkeypatch, tiny_manifest):
    def forbidden(*args, **kwargs):
        raise AssertionError("Implicit network call")
    monkeypatch.setattr(models.urllib.request, "urlopen", forbidden)
    assert models.model_status(tmp_path)["models"][0]["state"] == "missing"
    with pytest.raises(models.ModelError, match="not ready"):
        models.verified_paths(tmp_path)


def test_tampering_is_detected_even_when_size_is_same(tmp_path, tiny_manifest):
    target = tmp_path / "fixture.onnx"
    target.write_bytes(tiny_manifest)
    assert models.verified_paths(tmp_path)["detector"] == target
    target.write_bytes(b"x" + tiny_manifest[1:])
    assert models.model_status(tmp_path)["models"][0]["state"] == "checksum_mismatch"
    with pytest.raises(models.ModelError):
        models.verified_paths(tmp_path)


class Response(io.BytesIO):
    def geturl(self):
        return "https://example.invalid/fixture.onnx"


def test_download_is_verified_before_publish(tmp_path, monkeypatch, tiny_manifest):
    monkeypatch.setattr(models.urllib.request, "urlopen", lambda *a, **k: Response(tiny_manifest))
    assert models.download_models(tmp_path)["ready"]
    assert (tmp_path / "fixture.onnx").read_bytes() == tiny_manifest
    assert not list(tmp_path.glob(".model-*"))


@pytest.mark.parametrize("payload", [b"too short", b"x" * 1000])
def test_failed_download_is_not_published(tmp_path, monkeypatch, tiny_manifest, payload):
    target = tmp_path / "fixture.onnx"
    original = b"old invalid model"
    target.write_bytes(original)
    monkeypatch.setattr(models.urllib.request, "urlopen", lambda *a, **k: Response(payload))
    with pytest.raises(models.ModelError):
        models.download_models(tmp_path)
    assert target.read_bytes() == original
    assert not list(tmp_path.glob(".model-*"))


def test_ready_models_are_not_redownloaded(tmp_path, monkeypatch, tiny_manifest):
    (tmp_path / "fixture.onnx").write_bytes(tiny_manifest)
    def forbidden(*args, **kwargs):
        raise AssertionError("Unnecessary network call")
    monkeypatch.setattr(models.urllib.request, "urlopen", forbidden)
    assert models.download_models(tmp_path)["ready"]
