import io
import os
from pathlib import Path

import pytest

pytest.importorskip("cv2")
from PIL import Image

from mirid_identity.face import (MAX_IMAGE_BYTES, ImageInputError, compare_appearance,
                                 compare_images, decode_image)
from mirid_identity.models import model_status


def encoded(image, format="PNG", **kwargs):
    output = io.BytesIO()
    image.save(output, format=format, **kwargs)
    return output.getvalue()


@pytest.mark.parametrize("data", [b"", b"not an image", "path/to/image.jpg", b"x" * (MAX_IMAGE_BYTES + 1)])
def test_invalid_input_is_rejected(data):
    with pytest.raises(ImageInputError):
        decode_image(data)


def test_small_image_is_rejected():
    with pytest.raises(ImageInputError, match="at least 112"):
        decode_image(encoded(Image.new("RGB", (111, 112))))


def test_pixel_limit_is_checked_before_full_decode():
    with pytest.raises(ImageInputError, match="16 megapixel"):
        decode_image(encoded(Image.new("1", (4001, 4000))))


def test_unexpected_formats_are_rejected():
    with pytest.raises(ImageInputError, match="JPEG, PNG or WebP"):
        decode_image(encoded(Image.new("RGB", (112, 112)), format="TIFF"))


def test_transparency_is_flattened_and_large_input_bounded():
    pixels, info = decode_image(encoded(Image.new("RGBA", (2560, 1280), (0, 0, 0, 0))))
    assert tuple(pixels.shape) == (640, 1280, 3)
    assert int(pixels.min()) == 255
    assert info["width"] == 2560


def test_multi_reference_limit_is_enforced_before_inference():
    for references in [[], [b"x"] * 6]:
        with pytest.raises(ImageInputError):
            compare_appearance(references, b"x")


def local_models():
    path = Path(os.environ.get("MIRID_IDENTITY_TEST_MODELS", str(Path(__file__).parents[1] / "models")))
    if not model_status(path)["ready"]:
        pytest.skip("Pinned model weights are not installed; no test downloads models.")
    return path


def test_real_detector_rejects_blank_image():
    blank = encoded(Image.new("RGB", (512, 512), (125, 125, 125)))
    result = compare_images(blank, blank, model_dir=local_models())
    assert result["status"] == "inconclusive"
    assert result["reference"]["quality"]["reasons"] == ["no_face"]
    assert result["cosine_similarity"] is None
    assert result["identity_verified"] is False


def test_real_models_on_explicit_upstream_fixture():
    """An optional public-domain sample verifies inference, not accuracy.

    Set MIRID_IDENTITY_TEST_IMAGE to an explicitly obtained, licensed fixture.
    The repository never downloads or stores someone's personal face photos.
    """
    fixture = os.environ.get("MIRID_IDENTITY_TEST_IMAGE")
    if not fixture:
        pytest.skip("No explicit licensed smoke-test image supplied.")
    data = Path(fixture).read_bytes()
    result = compare_images(data, data, model_dir=local_models())
    assert result["status"] == "compared", result
    assert result["cosine_similarity"] > 0.999
    assert result["threshold"] is None
    assert result["identity_verified"] is False
    assert result["liveness"] == "not_assessed"
    assert result["document_authenticity"] == "not_assessed"
    assert "embedding" not in result

    image = Image.open(io.BytesIO(data)).convert("RGB")
    duplicate = Image.new("RGB", (image.width * 2, image.height))
    duplicate.paste(image, (0, 0))
    duplicate.paste(image, (image.width, 0))
    crowded = compare_images(data, encoded(duplicate), model_dir=local_models())
    assert crowded["status"] == "inconclusive", crowded
    assert crowded["probe"]["quality"]["reasons"] == ["multiple_faces"]
