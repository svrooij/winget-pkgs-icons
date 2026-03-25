#!/usr/bin/env python3
"""Download icons for Google.* and Microsoft.* winget packages from SVGRepo."""

import csv
import io
import re
import time
from pathlib import Path

import cairosvg
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_URL = "https://github.com/svrooij/winget-pkgs-index/raw/main/index.csv"
SVGREPO_SEARCH = "https://www.svgrepo.com/vectors/{term}/multicolor/"

# Locale suffix pattern, e.g. .de-DE, .fr-FR, .zh-Hans
LOCALE_RE = re.compile(r"\.[a-z]{2}(-[A-Za-z]{2,4})?$")

# Matches CamelCase word boundaries, e.g. "AndroidStudio" → "Android Studio"
CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# Direct SVG URL pattern embedded in SVGRepo search-result pages
SVGREPO_SVG_URL_RE = re.compile(
    r'https://www\.svgrepo\.com/show/(\d+)/([a-z0-9][a-z0-9\-]*)\.svg'
)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})


def fetch(url: str, timeout: int = 30) -> requests.Response | None:
    try:
        r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r
        return None
    except Exception:
        return None


def package_path(package_id: str, suffix: str = ".png") -> Path:
    """Return the repository-relative path for a package icon.

    Underscores in package ID segments (e.g. version suffixes like ``3_1``) are
    replaced with hyphens so all path components pass the alphanumeric/hyphen
    naming validator.

    Examples::

        Google.Chrome          → g/google/chrome.png
        Microsoft.DotNet.SDK.9 → m/microsoft/dotnet/sdk/9.png
        Microsoft.DotNet.SDK.3_1 → m/microsoft/dotnet/sdk/3-1.png
    """
    parts = package_id.lower().replace("_", "-").split(".")
    publisher = parts[0]
    app_parts = parts[1:]
    first_letter = publisher[0]
    return Path(first_letter) / publisher / Path(*app_parts).with_suffix(suffix)


def make_search_terms(package_id: str) -> list[str]:
    """Generate SVGRepo search-term candidates from a winget package ID.

    Returns a prioritised list of terms to try (most-specific first).

    Examples::

        "Google.Chrome"            → ["chrome", "google chrome"]
        "Google.AndroidStudio"     → ["android studio", "androidstudio", "google androidstudio"]
        "Microsoft.DotNet.SDK.9"   → ["dotnet", "dotnet sdk", "microsoft dotnet"]
        "Microsoft.OpenJDK.17"     → ["openjdk", "open jdk", "microsoft openjdk"]
    """
    parts = package_id.split(".", 1)
    publisher = parts[0].lower()
    app = parts[1] if len(parts) > 1 else ""
    segments = app.split(".")

    def split_camel(s: str) -> list[str]:
        return CAMEL_RE.sub(" ", s).lower().split()

    first_words = split_camel(segments[0])
    first_slug = segments[0].lower()

    candidates: list[str] = []

    # "android studio", "chrome", "dotnet", "openjdk" …
    candidates.append(" ".join(first_words))
    if first_slug not in candidates:
        candidates.append(first_slug)

    # First two segments joined: "dotnet sdk", "android studio beta" …
    if len(segments) >= 2:
        two = split_camel(segments[0]) + split_camel(segments[1])
        if (joined := " ".join(two)) not in candidates:
            candidates.append(joined)

    # Publisher + first segment: "google chrome", "microsoft dotnet" …
    combined = f"{publisher} {first_slug}"
    if combined not in candidates:
        candidates.append(combined)

    # All segments flattened: last resort
    all_words: list[str] = []
    for seg in segments:
        all_words.extend(split_camel(seg))
    if len(all_words) > 1 and (full := " ".join(all_words)) not in candidates:
        candidates.append(full)

    return candidates


def search_svgrepo(term: str) -> str | None:
    """Search SVGRepo for a multicolor SVG and return the SVG URL of the first result.

    Returns ``None`` when no multicolor result is found or the site is unreachable.
    """
    safe_term = term.replace(" ", "-")
    url = SVGREPO_SEARCH.format(term=safe_term)
    r = fetch(url, timeout=20)
    if r is None:
        return None

    matches = SVGREPO_SVG_URL_RE.findall(r.text)
    if matches:
        icon_id, slug = matches[0]
        return f"https://www.svgrepo.com/show/{icon_id}/{slug}.svg"

    return None


def save_svg(svg_bytes: bytes, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(svg_bytes)


def svg_to_png(svg_bytes: bytes, out_path: Path) -> bool:
    """Convert *svg_bytes* to a 1024×1024 PNG at *out_path*.  Returns True on success."""
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(
            bytestring=svg_bytes,
            write_to=str(out_path),
            output_width=1024,
            output_height=1024,
        )
        return True
    except Exception as e:
        print(f"    SVG→PNG conversion failed: {e}")
        return False


def main() -> None:
    print("Downloading package index CSV…")
    r = SESSION.get(CSV_URL, timeout=60)
    r.raise_for_status()

    text = r.text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    rows = [
        {k.strip('"').strip("\ufeff"): v for k, v in row.items()}
        for row in reader
    ]
    print(f"Total packages in CSV: {len(rows)}")

    filtered = [
        row for row in rows
        if (
            row["PackageId"].startswith("Google.")
            or row["PackageId"].startswith("Microsoft.")
        )
        and not LOCALE_RE.search(row["PackageId"])
    ]

    latest: dict[str, dict] = {}
    for row in filtered:
        pid = row["PackageId"]
        if pid not in latest or row.get("Version", "") >= latest[pid].get("Version", ""):
            latest[pid] = row

    packages = list(latest.values())
    print(f"Unique Google/Microsoft packages: {len(packages)}")

    success = 0
    skipped = 0
    failed = 0

    for i, row in enumerate(packages, 1):
        pid = row["PackageId"]
        png_path = REPO_ROOT / package_path(pid, ".png")
        svg_path = REPO_ROOT / package_path(pid, ".svg")

        if png_path.exists() and svg_path.exists():
            print(f"[{i}/{len(packages)}] SKIP (exists): {package_path(pid)}")
            skipped += 1
            continue

        print(f"[{i}/{len(packages)}] {pid}")
        search_terms = make_search_terms(pid)

        svg_url = None
        for term in search_terms:
            svg_url = search_svgrepo(term)
            if svg_url:
                print(f"    Found via '{term}': {svg_url}")
                break
            time.sleep(0.3)

        if not svg_url:
            print("    No SVGRepo result")
            failed += 1
            continue

        resp = fetch(svg_url, timeout=30)
        if not resp or not resp.content:
            print("    Failed to download SVG")
            failed += 1
            continue

        svg_bytes = resp.content

        save_svg(svg_bytes, svg_path)
        print(f"    Saved SVG: {package_path(pid, '.svg')}")

        if svg_to_png(svg_bytes, png_path):
            print(f"    Saved PNG: {package_path(pid, '.png')}")
            success += 1
        else:
            failed += 1

        time.sleep(0.5)

    print(f"\nDone. Success: {success}, Skipped: {skipped}, Failed: {failed}")


if __name__ == "__main__":
    main()
