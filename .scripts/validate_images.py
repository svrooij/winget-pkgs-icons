#!/usr/bin/env python3
"""Validate winget package icon images.

Each PNG must be:
- A valid PNG file
- Exactly 1024x1024 pixels
- Located at a path that follows the naming convention:
  {first_letter_of_publisher}/{publisher}/{app_parts...}.png

  Example: Microsoft.Teams -> m/microsoft/teams.png
           Mozilla.Firefox.az -> m/mozilla/firefox/az.png

Each SVG must be:
- A valid XML file with an <svg> root element
- Located at the same path as its companion PNG but with a .svg extension:
  {first_letter_of_publisher}/{publisher}/{app_parts...}.svg

When run inside GitHub Actions (GITHUB_ACTIONS=true) each failure also emits a
workflow annotation so the faulty file is highlighted inline in the PR diff.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is not installed. Run: pip install Pillow")
    sys.exit(1)

REQUIRED_SIZE = (1024, 1024)
VALID_COMPONENT = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
IN_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


def annotate_error(path: str, message: str) -> None:
    """Emit a GitHub Actions error annotation for *path* when running in CI."""
    if IN_GITHUB_ACTIONS:
        # Percent signs, carriage returns, and newlines must be URL-encoded
        # inside the message to avoid being mis-parsed as workflow command
        # parameters.
        safe_msg = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error file={path}::{safe_msg}", flush=True)


def validate_path_components(path: str, expected_suffix: str) -> tuple[bool, str]:
    """Return (ok, message) after checking the path follows the naming convention.

    *expected_suffix* must be ``'.png'`` or ``'.svg'``.
    """
    p = Path(path)
    parts = p.parts

    if p.suffix.lower() != expected_suffix:
        return False, f"file extension must be {expected_suffix}, got '{p.suffix}'"

    # Need at least: {letter}/{publisher}/{app}.{ext}
    if len(parts) < 3:
        return (
            False,
            f"path must have at least 3 components, "
            f"e.g. 'm/microsoft/teams{expected_suffix}'",
        )

    first_dir = parts[0]
    publisher = parts[1]
    filename_stem = p.stem  # without extension

    if len(first_dir) != 1 or not first_dir.isalpha():
        return False, f"first directory must be a single letter, got '{first_dir}'"

    if not VALID_COMPONENT.match(publisher):
        return (
            False,
            f"publisher directory '{publisher}' must be lowercase alphanumeric (hyphens allowed)",
        )

    if first_dir != publisher[0]:
        return (
            False,
            f"first directory '{first_dir}' must match the first letter "
            f"of the publisher '{publisher}' (expected '{publisher[0]}')",
        )

    # Validate intermediate directories (if any)
    for part in parts[2:-1]:
        if not VALID_COMPONENT.match(part):
            return (
                False,
                f"path component '{part}' must be lowercase alphanumeric (hyphens allowed)",
            )

    if not VALID_COMPONENT.match(filename_stem):
        return (
            False,
            f"filename '{filename_stem}' must be lowercase alphanumeric (hyphens allowed)",
        )

    return True, "path is valid"


def validate_png(path: str) -> bool:
    """Validate a single PNG file. Returns True if valid."""
    ok = True
    print(f"Validating PNG: {path}")

    path_ok, path_msg = validate_path_components(path, ".png")
    if not path_ok:
        print(f"  PATH ERROR: {path_msg}")
        annotate_error(path, f"Path error: {path_msg}")
        ok = False

    try:
        with Image.open(path) as img:
            if img.format != "PNG":
                msg = f"expected PNG format, got {img.format}"
                print(f"  FORMAT ERROR: {msg}")
                annotate_error(path, f"Format error: {msg}")
                ok = False

            if img.size != REQUIRED_SIZE:
                msg = f"expected 1024x1024, got {img.size[0]}x{img.size[1]}"
                print(f"  SIZE ERROR: {msg}")
                annotate_error(path, f"Size error: {msg}")
                ok = False
    except FileNotFoundError:
        msg = "file not found"
        print(f"  FILE ERROR: {msg}")
        annotate_error(path, f"File error: {msg}")
        ok = False
    except Exception as e:
        msg = f"could not open image: {e}"
        print(f"  READ ERROR: {msg}")
        annotate_error(path, f"Read error: {msg}")
        ok = False

    if ok:
        print("  OK")

    return ok


def validate_svg(path: str) -> bool:
    """Validate a single SVG file. Returns True if valid."""
    ok = True
    print(f"Validating SVG: {path}")

    path_ok, path_msg = validate_path_components(path, ".svg")
    if not path_ok:
        print(f"  PATH ERROR: {path_msg}")
        annotate_error(path, f"Path error: {path_msg}")
        ok = False

    try:
        tree = ET.parse(path)
        root = tree.getroot()
        # ElementTree prefixes the namespace: {http://www.w3.org/2000/svg}svg
        local_name = root.tag.split("}")[-1] if "}" in root.tag else root.tag
        if local_name.lower() != "svg":
            msg = f"root element must be <svg>, got <{local_name}>"
            print(f"  FORMAT ERROR: {msg}")
            annotate_error(path, f"Format error: {msg}")
            ok = False
    except FileNotFoundError:
        msg = "file not found"
        print(f"  FILE ERROR: {msg}")
        annotate_error(path, f"File error: {msg}")
        ok = False
    except ET.ParseError as e:
        msg = f"invalid XML: {e}"
        print(f"  PARSE ERROR: {msg}")
        annotate_error(path, f"Parse error: {msg}")
        ok = False
    except Exception as e:
        msg = f"could not open file: {e}"
        print(f"  READ ERROR: {msg}")
        annotate_error(path, f"Read error: {msg}")
        ok = False

    if ok:
        print("  OK")

    return ok


def validate_file(path: str) -> bool:
    """Dispatch to the correct validator based on file extension."""
    ext = Path(path).suffix.lower()
    if ext == ".png":
        return validate_png(path)
    if ext == ".svg":
        return validate_svg(path)
    print(f"Skipping unsupported file type: {path}")
    return True


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: validate_images.py <file1.png|file1.svg> [file2 ...]")
        sys.exit(1)

    files = sys.argv[1:]
    results = [validate_file(f) for f in files]

    passed = sum(results)
    failed = len(results) - passed

    print(f"\nResults: {passed} passed, {failed} failed")

    if failed:
        print("Validation FAILED")
        sys.exit(1)

    print("All images are valid!")


if __name__ == "__main__":
    main()
