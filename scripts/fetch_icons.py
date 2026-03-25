#!/usr/bin/env python3
"""Download icons for Google.* and Microsoft.* winget packages."""

import csv
import io
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_URL = "https://github.com/svrooij/winget-pkgs-index/raw/main/index.csv"
WINGET_RAW = "https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests"
TARGET_SIZE = (1024, 1024)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "winget-pkgs-icons-bot/1.0"})

# Locale suffix pattern, e.g. .de-DE, .fr-FR, .zh-Hans
LOCALE_RE = re.compile(r"\.[a-z]{2}(-[A-Za-z]{2,4})?$")


def fetch(url: str, timeout: int = 30) -> requests.Response | None:
    try:
        r = SESSION.get(url, timeout=timeout)
        if r.status_code == 200:
            return r
        return None
    except Exception:
        return None


def package_path(package_id: str) -> Path:
    """Return relative path for a package icon, e.g. m/microsoft/teams.png"""
    parts = package_id.lower().split(".")
    publisher = parts[0]
    app_parts = parts[1:]
    first_letter = publisher[0]
    return Path(first_letter) / publisher / Path(*app_parts).with_suffix(".png")


def manifest_url(publisher: str, app: str, version: str) -> str:
    """Build locale YAML URL. App parts with dots become subdirectories."""
    first = publisher[0].lower()
    # app may contain dots → split into path components
    app_path = app.replace(".", "/")
    package_id = f"{publisher}.{app}"
    return (
        f"{WINGET_RAW}/{first}/{publisher}/{app_path}/{version}"
        f"/{package_id}.locale.en-US.yaml"
    )


def extract_icon_urls(yaml_text: str) -> list[str]:
    """Extract icon URLs from manifest YAML, including commented-out Icons sections."""
    # First try standard YAML parsing
    try:
        data = yaml.safe_load(yaml_text)
    except Exception:
        data = {}
    if isinstance(data, dict):
        icons = data.get("Icons") or []
        urls = []
        for icon in icons:
            if isinstance(icon, dict):
                url = icon.get("IconUrl") or icon.get("Url") or icon.get("iconUrl")
                if url:
                    urls.append(url)
        if urls:
            return urls

    # Fallback: parse commented-out Icons sections from raw text
    # Pattern: lines like "# - IconUrl: https://..."  or "#   IconUrl: ..."
    urls = re.findall(
        r"^#?\s*[-]?\s*IconUrl:\s*(.+)$",
        yaml_text,
        re.MULTILINE | re.IGNORECASE,
    )
    return [u.strip() for u in urls if u.strip().startswith("http")]


def download_and_resize(url: str) -> Image.Image | None:
    r = fetch(url, timeout=60)
    if r is None:
        return None
    try:
        img = Image.open(io.BytesIO(r.content))
        img = img.convert("RGBA")
        img = img.resize(TARGET_SIZE, Image.LANCZOS)
        # Convert to RGB+A PNG
        return img
    except Exception as e:
        print(f"    Image error: {e}")
        return None


def save_icon(img: Image.Image, rel_path: Path) -> None:
    abs_path = REPO_ROOT / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(abs_path, format="PNG")


def main() -> None:
    print("Downloading package index CSV...")
    r = SESSION.get(CSV_URL, timeout=60)
    r.raise_for_status()

    # Handle BOM and quoted header names
    text = r.text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    # Normalize keys: strip quotes and BOM
    rows = [{k.strip('"').strip('\ufeff'): v for k, v in row.items()} for row in rows]
    print(f"Total packages in CSV: {len(rows)}")

    # Filter Google.* and Microsoft.* only
    filtered = [
        row for row in rows
        if row["PackageId"].startswith("Google.") or row["PackageId"].startswith("Microsoft.")
    ]
    print(f"Google/Microsoft packages: {len(filtered)}")

    # Skip locale-specific packages
    filtered = [row for row in filtered if not LOCALE_RE.search(row["PackageId"])]
    print(f"After removing locale variants: {len(filtered)}")

    # Keep latest version per package (CSV may have duplicates; take last occurrence
    # since the index is typically sorted with latest last, or deduplicate by
    # picking the highest version string).
    latest: dict[str, dict] = {}
    for row in filtered:
        pid = row["PackageId"]
        if pid not in latest:
            latest[pid] = row
        else:
            # Simple string comparison is often good enough for semver-ish versions
            if row.get("Version", "") >= latest[pid].get("Version", ""):
                latest[pid] = row

    packages = list(latest.values())
    print(f"Unique base packages: {len(packages)}")

    success = 0
    skipped = 0
    failed = 0

    for i, row in enumerate(packages, 1):
        pid = row["PackageId"]
        version = row.get("Version", "").strip()
        if not version:
            skipped += 1
            continue

        # Split publisher and app (app may contain dots)
        parts = pid.split(".", 1)
        publisher = parts[0]
        app = parts[1] if len(parts) > 1 else ""

        rel_path = package_path(pid)
        abs_path = REPO_ROOT / rel_path

        if abs_path.exists():
            print(f"[{i}/{len(packages)}] SKIP (exists): {rel_path}")
            skipped += 1
            continue

        url = manifest_url(publisher, app, version)
        print(f"[{i}/{len(packages)}] {pid} v{version}")

        resp = fetch(url)
        if resp is None:
            print(f"    No manifest at {url}")
            failed += 1
            continue

        icon_urls = extract_icon_urls(resp.text)
        if not icon_urls:
            print(f"    No Icons in manifest")
            skipped += 1
            continue

        icon_url = icon_urls[0]
        print(f"    Icon URL: {icon_url}")

        img = download_and_resize(icon_url)
        if img is None:
            print(f"    Failed to download/resize icon")
            failed += 1
            continue

        save_icon(img, rel_path)
        print(f"    Saved: {rel_path}")
        success += 1

        # Be polite to the servers
        time.sleep(0.2)

    print(f"\nDone. Success: {success}, Skipped: {skipped}, Failed: {failed}")


if __name__ == "__main__":
    main()
