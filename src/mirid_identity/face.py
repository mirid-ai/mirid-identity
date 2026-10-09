"""Local 1:1 face comparison. No identity decision, storage or network calls.

The capture-quality limits below are conservative engineering heuristics, not
validated biometric operating points. No demographic attributes are inferred.
"""

from __future__ import annotations

import io
import math
import threading
import warnings
from functools import lru_cache
from pathlib import Path

from .models import ModelError, default_model_dir, manifest, verified_paths

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_SIDE = 8192
DETECTION_MAX_SIDE = 1280
MIN_IMAGE_SIDE = 112
MIN_FACE_SIDE = 80
MAX_REFERENCES = 5


class ImageInputError(ValueError):
    """The input is not a supported, bounded still image."""


class FaceRuntimeError(RuntimeError):
    """Face inference failed without exposing the image or embedding."""


def _dependencies():
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:
        raise FaceRuntimeError("Face dependencies are missing. Install mirid-identity[face].") from exc
    return cv2, np, Image, ImageOps, UnidentifiedImageError


def decode_image(data: bytes):
    """Decode supported image bytes in memory, bounding dimensions first.

    No URLs or filesystem paths are accepted. Metadata is not returned.
    Returns an OpenCV BGR array and non-identifying dimension information.
    """
    if not isinstance(data, bytes) or not data:
        raise ImageInputError("An image must contain non-empty bytes.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageInputError("The image exceeds the 12 MiB file limit.")
    cv2, np, Image, ImageOps, UnidentifiedImageError = _dependencies()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ImageInputError("Use a JPEG, PNG or WebP still image.")
                if getattr(source, "n_frames", 1) != 1:
                    raise ImageInputError("Animated or multi-frame images are not supported.")
                width, height = source.size
                if (width * height > MAX_IMAGE_PIXELS or max(width, height) > MAX_IMAGE_SIDE):
                    raise ImageInputError("The image exceeds the 16 megapixel or 8192 pixel side limit.")
                if min(width, height) < MIN_IMAGE_SIDE:
                    raise ImageInputError("The image must be at least 112 pixels on each side.")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                # Alpha is flattened onto white, matching the visible image.
                if oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info:
                    rgba = oriented.convert("RGBA")
                    background = Image.new("RGBA", rgba.size, "white")
                    rgb = Image.alpha_composite(background, rgba).convert("RGB")
                else:
                    rgb = oriented.convert("RGB")
                width, height = rgb.size
                array = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
    except ImageInputError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageInputError("The image is invalid, incomplete or unsafe to decode.") from exc
    scale = min(1.0, DETECTION_MAX_SIDE / max(width, height))
    if scale < 1.0:
        array = cv2.resize(array, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    return array, {"width": width, "height": height,
                   "analysis_width": int(array.shape[1]), "analysis_height": int(array.shape[0])}


def _quality(image, face, cv2, np) -> dict:
    height, width = image.shape[:2]
    x, y, box_width, box_height = (float(value) for value in face[:4])
    x0, y0 = max(0, math.floor(x)), max(0, math.floor(y))
    x1, y1 = min(width, math.ceil(x + box_width)), min(height, math.ceil(y + box_height))
    reasons = []
    if min(box_width, box_height) < MIN_FACE_SIDE:
        reasons.append("face_too_small")
    if x < 0 or y < 0 or x + box_width > width or y + box_height > height:
        reasons.append("face_at_image_edge")
    crop = image[y0:y1, x0:x1]
    if not crop.size:
        return {"passed": False, "reasons": ["invalid_face_crop"], "heuristic": True}
    grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(grey))
    blur_variance = float(cv2.Laplacian(grey, cv2.CV_64F).var())
    clipping = float(np.mean((grey < 5) | (grey > 250)))
    # Detection order: right eye, left eye, nose, right mouth, left mouth.
    eye_a, eye_b = face[4:6], face[6:8]
    eye_distance = float(np.linalg.norm(eye_a - eye_b))
    eye_roll = math.degrees(math.atan2(float(eye_b[1] - eye_a[1]), float(eye_b[0] - eye_a[0])))
    eye_roll = ((eye_roll + 90) % 180) - 90
    if blur_variance < 35:
        reasons.append("face_blurred_or_low_detail")
    if brightness < 35 or brightness > 225 or clipping > 0.55:
        reasons.append("face_exposure_poor")
    if eye_distance < 25:
        reasons.append("eyes_too_close_in_image")
    if abs(eye_roll) > 25:
        reasons.append("head_tilt_too_large")
    return {"passed": not reasons, "reasons": reasons, "heuristic": True,
            "face_width": round(box_width, 1), "face_height": round(box_height, 1),
            "brightness": round(brightness, 2), "blur_variance": round(blur_variance, 2),
            "clipped_fraction": round(clipping, 4), "eye_distance": round(eye_distance, 2),
            "head_roll_degrees": round(eye_roll, 2)}


class FaceComparator:
    """A CPU model pair with a lock because OpenCV detector state is mutable."""

    def __init__(self, model_dir: str | Path | None = None):
        self.cv2, self.np, *_ = _dependencies()
        paths = verified_paths(model_dir)
        try:
            self.detector = self.cv2.FaceDetectorYN.create(
                str(paths["detector"]), "", (320, 320), 0.8, 0.3, 5000,
                self.cv2.dnn.DNN_BACKEND_OPENCV, self.cv2.dnn.DNN_TARGET_CPU)
            self.recognizer = self.cv2.FaceRecognizerSF.create(
                str(paths["recognizer"]), "", self.cv2.dnn.DNN_BACKEND_OPENCV,
                self.cv2.dnn.DNN_TARGET_CPU)
        except self.cv2.error as exc:
            raise FaceRuntimeError("OpenCV could not initialise the verified face models.") from exc
        self.lock = threading.Lock()

    def _extract(self, data: bytes):
        image, info = decode_image(data)
        self.detector.setInputSize((image.shape[1], image.shape[0]))
        _, faces = self.detector.detect(image)
        count = 0 if faces is None else len(faces)
        info["face_count"] = count
        if count != 1:
            info["quality"] = {"passed": False, "heuristic": True,
                               "reasons": ["no_face" if count == 0 else "multiple_faces"]}
            return None, info
        if not self.np.isfinite(faces[0]).all():
            raise FaceRuntimeError("The face detector returned non-finite coordinates.")
        info["quality"] = _quality(image, faces[0], self.cv2, self.np)
        if not info["quality"]["passed"]:
            return None, info
        aligned = self.recognizer.alignCrop(image, faces[0])
        feature = self.recognizer.feature(aligned)
        if not self.np.isfinite(feature).all() or float(self.np.linalg.norm(feature)) == 0:
            raise FaceRuntimeError("The face model returned an invalid embedding.")
        return feature, info

    def compare(self, reference: bytes, probe: bytes) -> dict:
        """Compare only the supplied pair; never search a collection of people."""
        metadata = manifest()
        recognizer = next(item for item in metadata["models"] if item["role"] == "recognizer")
        report = {"schema_version": 1, "status": "inconclusive", "experimental": True,
                  "metric": "cosine_similarity", "cosine_similarity": None,
                  "model_id": recognizer["id"], "model_sha256": recognizer["sha256"],
                  "detector_id": "opencv-yunet-2023mar", "quality_passed": False,
                  "threshold": None, "identity_verified": False,
                  "liveness": "not_assessed", "document_authenticity": "not_assessed",
                  "limitations": ["Similarity is not an identity probability.",
                                  "No operating threshold has been calibrated for this deployment.",
                                  "A face comparison does not verify a document or establish live presence."]}
        try:
            with self.lock:
                reference_feature, report["reference"] = self._extract(reference)
                probe_feature, report["probe"] = self._extract(probe)
                if reference_feature is None or probe_feature is None:
                    return report
                score = float(self.recognizer.match(reference_feature, probe_feature, self.cv2.FaceRecognizerSF_FR_COSINE))
                if not math.isfinite(score):
                    raise FaceRuntimeError("The face model returned a non-finite similarity score.")
                report.update(status="compared", quality_passed=True,
                              cosine_similarity=round(max(-1.0, min(1.0, score)), 7))
                return report
        except self.cv2.error as exc:
            raise FaceRuntimeError("OpenCV could not analyse this image pair.") from exc


@lru_cache(maxsize=2)
def _comparator(directory: str) -> FaceComparator:
    return FaceComparator(directory)


def compare_images(reference: bytes, probe: bytes, *, model_dir: str | Path | None = None) -> dict:
    """Compare image bytes locally. Model downloads must be requested separately."""
    directory = Path(model_dir) if model_dir is not None else default_model_dir()
    return _comparator(str(directory.expanduser().resolve())).compare(reference, probe)


def compare_appearance(references: list[bytes], probe: bytes, *, model_dir: str | Path | None = None) -> dict:
    """Explore appearance variation across 1-5 consented photos of one person.

    This does not enrol identities, search a gallery or turn the best score into
    a verification decision. Each supplied reference is reported separately.
    """
    if not isinstance(references, list) or not 1 <= len(references) <= MAX_REFERENCES:
        raise ImageInputError("Supply between one and five reference images of the same consenting person.")
    results = [compare_images(reference, probe, model_dir=model_dir) for reference in references]
    scores = [item["cosine_similarity"] for item in results if item["status"] == "compared"]
    return {"schema_version": 1, "mode": "appearance_comparison", "experimental": True,
            "identity_verified": False, "comparisons": results,
            "score_spread": None if not scores else round(max(scores) - min(scores), 7),
            "note": "Score variation across supplied photographs is not a measured error rate or identity decision."}
