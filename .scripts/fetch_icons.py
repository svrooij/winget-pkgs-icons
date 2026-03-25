#!/usr/bin/env python3
"""Download colored icons for winget packages listed in wishlist.txt.

Sources tried in order (all are colored SVGs hosted on raw.githubusercontent.com):
  1. Devicons  – developer-tool brand icons (colored "original" variant)
  2. Papirus   – desktop-app icons (Papirus icon theme, colored)
  3. Ionicons  – brand logo icons (logo-* variants, colored)

Every entry in wishlist.txt is attempted each run.  Entries whose icon is
successfully saved are removed from the list.  Entries for which no icon could
be found are moved to the bottom so they are retried on the next run (new
sources may appear over time).  A single git commit is made at the end when at
least one icon was downloaded.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import cairosvg
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
WISHLIST = REPO_ROOT / "wishlist.txt"

# ── URL templates ─────────────────────────────────────────────────────────────
DEVICONS_URL = (
    "https://raw.githubusercontent.com/devicons/devicon/master/icons/{slug}/{slug}-original.svg"
)
PAPIRUS_URL = (
    "https://raw.githubusercontent.com/PapirusDevelopmentTeam/"
    "papirus-icon-theme/master/Papirus/48x48/apps/{slug}.svg"
)
IONICONS_URL = (
    "https://raw.githubusercontent.com/ionic-team/ionicons/main/src/svg/logo-{slug}.svg"
)
DEVICONS_CATALOG_URL = (
    "https://raw.githubusercontent.com/devicons/devicon/master/devicon.json"
)

# Matches CamelCase word boundaries: "AndroidStudio" → "Android Studio"
CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "winget-pkgs-icons/1.0 (icon fetcher)"})


# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch(url: str) -> bytes | None:
    """Return response bytes for *url* on HTTP 200, else None."""
    try:
        r = SESSION.get(url, timeout=15, allow_redirects=True)
        return r.content if r.status_code == 200 else None
    except Exception:
        return None


def load_devicons_catalog() -> set[str]:
    """Return the set of devicon names that have a colored 'original' SVG."""
    data = fetch(DEVICONS_CATALOG_URL)
    if not data:
        print("  Warning: could not load devicons catalog; devicons source disabled.")
        return set()
    icons = json.loads(data)
    return {i["name"] for i in icons if "original" in i.get("versions", {}).get("svg", [])}


def package_path(package_id: str, suffix: str = ".png") -> Path:
    """Map a winget package ID to a repo-relative icon path.

    Examples::
        Google.Chrome            → g/google/chrome.png
        Microsoft.DotNet.SDK.9   → m/microsoft/dotnet/sdk/9.png
        Microsoft.DotNet.SDK.3_1 → m/microsoft/dotnet/sdk/3-1.png
    """
    parts = package_id.lower().replace("_", "-").split(".")
    publisher = parts[0]
    first_letter = publisher[0]
    return Path(first_letter) / publisher / Path(*parts[1:]).with_suffix(suffix)


def slug_candidates(package_id: str) -> list[str]:
    """Return an ordered list of lowercase slug candidates for icon lookups.

    Examples::
        "Google.Chrome"          → ["chrome", "google-chrome", "googlechrome"]
        "Google.AndroidStudio"   → ["androidstudio", "android-studio", "google-androidstudio"]
        "Microsoft.DotNet.SDK.9" → ["dotnetcore", "dotnet", "dotnet-sdk", "microsoft-dotnet"]
    """
    parts = package_id.split(".", 1)
    publisher = parts[0].lower()
    app = parts[1] if len(parts) > 1 else ""
    segments = app.split(".")

    def camel_words(s: str) -> list[str]:
        return CAMEL_RE.sub(" ", s).lower().split()

    first_seg = segments[0]
    first_words = camel_words(first_seg)
    first_slug = first_seg.lower()
    first_hyphen = "-".join(first_words)

    seen: list[str] = []

    def add(*slugs: str) -> None:
        for s in slugs:
            s = s.strip("-")
            if s and s not in seen:
                seen.append(s)

    # bare app name variants
    add(first_slug, first_hyphen)

    # dotnet is usually called dotnetcore in devicons
    if first_slug == "dotnet":
        add("dotnetcore")

    # two-segment join: "dotnet-sdk", "android-studio"
    if len(segments) >= 2:
        two = first_words + camel_words(segments[1])
        add("-".join(two), "".join(two))

    # publisher-prefixed: "google-chrome", "microsoft-dotnet"
    add(f"{publisher}-{first_slug}", f"{publisher}-{first_hyphen}")
    add(f"{publisher}{first_slug}")

    return seen


def find_colored_svg(package_id: str, devicons: set[str]) -> tuple[str, bytes] | None:
    """Try each icon source in priority order.  Returns (source_label, svg_bytes) or None."""
    for slug in slug_candidates(package_id):
        # 1. Devicons (colored originals)
        if slug in devicons:
            url = DEVICONS_URL.format(slug=slug)
            data = fetch(url)
            if data and b"<svg" in data:
                return (f"devicons:{slug}", data)

        # 2. Papirus desktop icons
        url = PAPIRUS_URL.format(slug=slug)
        data = fetch(url)
        if data and b"<svg" in data:
            return (f"papirus:{slug}", data)

        # 3. Ionicons brand logos
        url = IONICONS_URL.format(slug=slug)
        data = fetch(url)
        if data and b"<svg" in data:
            return (f"ionicons:logo-{slug}", data)

    return None


def save_svg(svg_bytes: bytes, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(svg_bytes)


def svg_to_png(svg_bytes: bytes, out_path: Path) -> bool:
    """Render *svg_bytes* to a 1024×1024 PNG.  Returns True on success."""
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
        print(f"    SVG→PNG failed: {e}")
        return False


def read_wishlist() -> list[str]:
    if not WISHLIST.exists():
        return []
    return [l.strip() for l in WISHLIST.read_text().splitlines() if l.strip()]


def write_wishlist(packages: list[str]) -> None:
    WISHLIST.write_text(("\n".join(packages) + "\n") if packages else "")


def git_commit(message: str) -> None:
    """Stage all changes and create a commit."""
    subprocess.run(["git", "-C", str(REPO_ROOT), "add", "-A"], check=True)
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--cached", "--quiet"]
    )
    if result.returncode == 0:
        print("  (nothing to commit)")
        return
    subprocess.run(
        ["git", "-C", str(REPO_ROOT), "commit", "-m", message],
        check=True,
    )
    print(f"  Committed: {message}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    packages = read_wishlist()
    if not packages:
        print("wishlist.txt is empty – nothing to do.")
        return

    print("Loading devicons catalog…")
    devicons = load_devicons_catalog()
    print(f"  {len(devicons)} colored devicons available.")
    print(f"Wishlist: {len(packages)} packages.\n")

    found: list[str] = []   # package IDs successfully saved this run
    deferred: list[str] = []  # package IDs with no icon found → move to bottom
    failed = 0

    for pid in packages:
        png_path = REPO_ROOT / package_path(pid, ".png")
        svg_path = REPO_ROOT / package_path(pid, ".svg")

        if png_path.exists() and svg_path.exists():
            print(f"SKIP (exists): {pid}")
            continue

        print(f"  {pid}")
        result = find_colored_svg(pid, devicons)

        if not result:
            print("    ✗ no colored icon found – deferring to next run")
            deferred.append(pid)
            continue

        source, svg_bytes = result
        save_svg(svg_bytes, svg_path)
        if svg_to_png(svg_bytes, png_path):
            print(f"    ✓ {source}  →  {package_path(pid, '.svg')}")
            found.append(pid)
        else:
            deferred.append(pid)
            failed += 1

    # Rebuild wishlist: successfully-fetched entries are removed;
    # failed entries go to the bottom so they are retried next run.
    remaining = [p for p in packages if p not in found]
    # Re-order so deferred are at the end (preserve relative order of the rest)
    not_deferred = [p for p in remaining if p not in deferred]
    write_wishlist(not_deferred + deferred)

    if found:
        ids = ", ".join(found)
        commit_msg = f"Add {len(found)} colored icons ({ids})"
        print(f"\nCommitting {len(found)} icon(s)…")
        git_commit(commit_msg)
    else:
        # Still commit the updated wishlist order if anything changed
        git_commit("Update wishlist order after icon fetch attempt")

    print(
        f"\nDone. Found: {len(found)}, Deferred to next run: {len(deferred)}, "
        f"PNG-conversion failures: {failed}, "
        f"Remaining in wishlist: {len(read_wishlist())}"
    )


if __name__ == "__main__":
    main()
