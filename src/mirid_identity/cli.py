"""Small command-line interface; image bytes are not written or printed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .face import MAX_IMAGE_BYTES, FaceRuntimeError, ImageInputError, compare_appearance, compare_images
from .models import ModelError, download_models, model_status


def _read_image(path: str) -> bytes:
    with Path(path).open("rb") as stream:
        content = stream.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise ImageInputError("An input image exceeds the 12 MiB file limit.")
    return content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local experimental face comparison. No accredited identity decision.")
    commands = parser.add_subparsers(dest="command", required=True)
    models = commands.add_parser("models", help="Inspect or explicitly download pinned public model weights")
    models.add_argument("action", choices=["status", "download"])
    models.add_argument("--model-dir", default=None)
    compare = commands.add_parser("compare", help="Compare two photographs supplied with consent")
    compare.add_argument("reference")
    compare.add_argument("probe")
    compare.add_argument("--model-dir", default=None)
    appearance = commands.add_parser("appearance", help="Compare appearance across supplied photos of one consenting person")
    appearance.add_argument("probe")
    appearance.add_argument("references", nargs="+")
    appearance.add_argument("--model-dir", default=None)
    args = parser.parse_args(argv)
    try:
        if args.command == "models":
            result = (download_models if args.action == "download" else model_status)(args.model_dir)
        elif args.command == "compare":
            result = compare_images(_read_image(args.reference), _read_image(args.probe), model_dir=args.model_dir)
        else:
            if len(args.references) > 5:
                raise ImageInputError("Supply at most five reference images.")
            result = compare_appearance([_read_image(path) for path in args.references],
                                        _read_image(args.probe), model_dir=args.model_dir)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ImageInputError, FaceRuntimeError, ModelError, OSError) as exc:
        # Do not expose local input paths or any image content in error output.
        message = "An input file could not be read." if isinstance(exc, OSError) else str(exc)
        print(json.dumps({"error": type(exc).__name__, "message": message}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
