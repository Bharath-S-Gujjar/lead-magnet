"""Safe archive creation script for the Lead Magnet project.

Usage
-----
From the project root::

    python scripts/make_archive.py

What it does
------------
1. Creates a ZIP of the backend source, excluding:
   - .env, .env.*, backend/.env (any file matching these patterns)
   - .git/ directory and all contents
   - __pycache__/ directories
   - *.pyc / *.pyo compiled files
   - node_modules/ directories
   - frontend/dist/, frontend/build/ output
   - venv/, .venv/ virtual environments
   - Previously generated *.zip archives
   - data/catalog/backup/, data/catalog/raw/ (large raw data)

2. Scans the archive listing for any file that appears to contain secrets
   (i.e., matches secret-bearing filename patterns) and FAILS if any are found.

3. Prints the final file list so the caller can verify the contents.

Constraints
-----------
- Does not read, print, or copy the contents of .env files.
- Does not commit, push, or deploy.
- Does not connect to any database.
- The output archive name contains a timestamp so archives do not overwrite
  each other accidentally.
"""

import os
import sys
import zipfile
import datetime
import fnmatch
import re

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_NAME = f"backend_safe_{TIMESTAMP}.zip"
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "scratch", OUTPUT_NAME)

# Patterns relative to project root that should be EXCLUDED from the archive.
# Uses fnmatch-style globs; ** is not supported — we check each path component.
EXCLUDE_DIR_NAMES = {
    ".git",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "ENV",
    "env",
    ".pytest_cache",
    "htmlcov",
    ".mypy_cache",
    "dist",
    "build",
}

EXCLUDE_FILE_PATTERNS = [
    "*.env",
    ".env",
    ".env.*",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so",
    "*.zip",
    "*.tar.gz",
    "*.log",
    "Thumbs.db",
    ".DS_Store",
]

# Paths (relative to project root) to skip entirely.
EXCLUDE_RELATIVE_PATHS = {
    os.path.join("data", "catalog", "backup"),
    os.path.join("data", "catalog", "raw"),
    os.path.join("data", "catalog", "cleaned_clothing_catalog.json"),
    os.path.join("data", "catalog", "resume_operation_summary.json"),
    os.path.join("data", "inventory_raw.json"),
    os.path.join("scratch"),
}

# Files that are explicitly ALLOWED despite looking like .env files.
ALLOWED_ENV_FILES = {
    ".env.example",
    ".env.local.example",
}

# ---------------------------------------------------------------------------
# Secret-bearing filename patterns — if ANY of these appear in the archive,
# the script FAILS.
# ---------------------------------------------------------------------------
SECRET_FILENAME_PATTERNS = [
    r"^\.env$",
    r"^\.env\.",      # .env.local, .env.production, etc.
    r"^\.env\.local$",
    r"^\.env\.production$",
]
# Exception: allow example templates.
SECRET_FILENAME_ALLOWLIST = {"env.example", "env.local.example"}


def _is_excluded_dir(dirname: str) -> bool:
    return dirname in EXCLUDE_DIR_NAMES


def _is_excluded_file(filename: str) -> bool:
    if filename in ALLOWED_ENV_FILES:
        return False
    for pat in EXCLUDE_FILE_PATTERNS:
        if fnmatch.fnmatch(filename, pat):
            return True
    return False


def _is_excluded_path(rel_path: str) -> bool:
    norm = os.path.normpath(rel_path)
    for excl in EXCLUDE_RELATIVE_PATHS:
        excl_norm = os.path.normpath(excl)
        if norm == excl_norm or norm.startswith(excl_norm + os.sep):
            return True
    return False


def _looks_like_secret_file(arcname: str) -> bool:
    """Return True if the archive path looks like it contains real secrets."""
    filename = os.path.basename(arcname)
    basename_no_dot = filename.lstrip(".")
    if basename_no_dot in SECRET_FILENAME_ALLOWLIST:
        return False
    for pat in SECRET_FILENAME_PATTERNS:
        if re.match(pat, filename, re.IGNORECASE):
            return True
    return False


def build_archive() -> str:
    """Build the archive and return the path to the created file."""
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    collected = []  # (abs_path, arcname)

    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        # Prune excluded directories in-place so os.walk skips them.
        dirnames[:] = [
            d for d in dirnames
            if not _is_excluded_dir(d)
        ]

        rel_dir = os.path.relpath(dirpath, PROJECT_ROOT)

        if _is_excluded_path(rel_dir):
            dirnames.clear()
            continue

        for filename in filenames:
            if _is_excluded_file(filename):
                continue

            abs_path = os.path.join(dirpath, filename)
            rel_file = os.path.join(rel_dir, filename) if rel_dir != "." else filename
            arcname = rel_file.replace(os.sep, "/")

            if _is_excluded_path(rel_file):
                continue

            collected.append((abs_path, arcname))

    print(f"Building archive: {OUTPUT_PATH}")
    print(f"Files to include: {len(collected)}")

    with zipfile.ZipFile(OUTPUT_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for abs_path, arcname in collected:
            zf.write(abs_path, arcname)

    return OUTPUT_PATH


def verify_archive(archive_path: str) -> None:
    """Open the archive and fail if any secret-bearing files are present."""
    violations = []
    with zipfile.ZipFile(archive_path, "r") as zf:
        names = zf.namelist()

    print(f"\nArchive contains {len(names)} files.")

    for name in names:
        if _looks_like_secret_file(name):
            violations.append(name)

    if violations:
        print("\n[FATAL] Secret-bearing files found in archive:")
        for v in violations:
            print(f"  {v}")
        print("\nDelete the archive and fix the exclusion rules before distributing.")
        sys.exit(1)

    print("\nSafety check PASSED — no secret-bearing files in archive.")


def print_listing(archive_path: str) -> None:
    """Print the full file listing so the caller can spot-check it."""
    with zipfile.ZipFile(archive_path, "r") as zf:
        names = sorted(zf.namelist())
    print("\nArchive contents:")
    for name in names:
        print(f"  {name}")


if __name__ == "__main__":
    archive = build_archive()
    verify_archive(archive)
    print_listing(archive)
    print(f"\nArchive created: {archive}")
