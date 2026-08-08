"""
Cython Build Script — Compiles .py files to .so and removes originals.

Used inside Docker build to protect source code in production images.
Run with: python cython_build.py

Files excluded from compilation:
  - main.py (entry points — uvicorn/python imports by string)
  - __init__.py (package discovery)
  - cython_build.py (this script)
  - scripts/ (dev-only migration scripts, not needed in production)
  - tests/ (not needed in production)
  - myenv/ (virtual environment)
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from Cython.Build import cythonize
from setuptools import setup, Extension


# ─── Configuration ───────────────────────────────────────────────

# Files that MUST remain as .py
KEEP_AS_PY = {
    "main.py",
    "cython_build.py",
}

# Filename patterns to always keep as .py
KEEP_PATTERNS = {
    "__init__.py",
}

# Directories to skip entirely (not compiled, not needed in prod)
SKIP_DIRS = {
    "myenv",
    "venv",
    ".venv",
    "__pycache__",
    ".git",
    ".github",
    "scripts",
    "tests",
    "logs",
}

# Directories to skip compilation but keep .py files
KEEP_PY_DIRS = set()


def find_compilable_files(root_dir: str) -> list[str]:
    """Find all .py files eligible for Cython compilation."""
    compilable = []
    root = Path(root_dir)

    for py_file in root.rglob("*.py"):
        rel = py_file.relative_to(root)
        rel_str = str(rel)

        # Skip files in excluded directories
        parts = rel.parts
        if any(skip_dir in parts for skip_dir in SKIP_DIRS):
            continue

        # Skip files that must stay as .py
        if py_file.name in KEEP_AS_PY:
            continue
        if py_file.name in KEEP_PATTERNS:
            continue

        # Skip files in keep-py directories
        if any(keep_dir in parts for keep_dir in KEEP_PY_DIRS):
            continue

        compilable.append(rel_str)

    return sorted(compilable)


def compile_files(root_dir: str, files: list[str]):
    """Compile .py files to .so using Cython, then remove originals."""
    root = Path(root_dir)
    success = []
    failed = []

    print(f"\n{'='*60}")
    print(f"Cython Compilation — {len(files)} files to compile")
    print(f"{'='*60}\n")

    # Build extensions list
    extensions = []
    for rel_path in files:
        py_file = root / rel_path
        # Module name: convert path separators to dots, remove .py
        module_name = rel_path.replace(os.sep, ".").replace("/", ".")[:-3]
        extensions.append(
            Extension(module_name, [str(py_file)])
        )

    if not extensions:
        print("No files to compile.")
        return

    # Compile all at once with Cython
    try:
        setup(
            name="citra-service-compiled",
            ext_modules=cythonize(
                extensions,
                compiler_directives={
                    "language_level": "3",      # Python 3
                    "boundscheck": False,        # Faster runtime
                    "wraparound": False,         # Faster runtime
                },
                nthreads=os.cpu_count() or 4,    # Parallel compilation
                quiet=False,
            ),
            script_args=["build_ext", "--inplace"],
        )
    except Exception as e:
        print(f"\nERROR: Cython compilation failed: {e}")
        sys.exit(1)

    # Verify .so files were created and remove original .py + .c files
    for rel_path in files:
        py_file = root / rel_path
        directory = py_file.parent
        stem = py_file.stem

        # Find the compiled .so file (name includes Python version tag)
        so_files = list(directory.glob(f"{stem}*.so")) + list(directory.glob(f"{stem}*.pyd"))

        if so_files:
            # Remove the original .py file
            py_file.unlink()
            # Remove the intermediate .c file
            c_file = py_file.with_suffix(".c")
            if c_file.exists():
                c_file.unlink()
            success.append(rel_path)
        else:
            failed.append(rel_path)
            print(f"  WARNING: No .so generated for {rel_path}")

    # Cleanup build directory
    build_dir = root / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)

    # Report
    print(f"\n{'='*60}")
    print(f"Compilation complete:")
    print(f"  Compiled: {len(success)}")
    print(f"  Failed:   {len(failed)}")
    print(f"  Kept .py: {len(KEEP_AS_PY) + len(KEEP_PATTERNS)} (entry points + __init__)")
    print(f"{'='*60}\n")

    if failed:
        print("FAILED files:")
        for f in failed:
            print(f"  - {f}")
        # Don't exit(1) — partially compiled is better than nothing
        # The .py originals remain for files that couldn't be compiled


def cleanup_dev_files(root_dir: str):
    """Remove development-only files not needed in production image."""
    root = Path(root_dir)
    remove_items = [
        "cython_build.py",
        "scripts",
        "tests",
        ".git",
        ".github",
        ".gitignore",
        "myenv",
        "venv",
        ".venv",
    ]
    for item in remove_items:
        path = root / item
        if path.is_file():
            path.unlink()
            print(f"  Removed: {item}")
        elif path.is_dir():
            shutil.rmtree(path)
            print(f"  Removed: {item}/")


if __name__ == "__main__":
    root_dir = os.path.dirname(os.path.abspath(__file__)) if len(sys.argv) < 2 else sys.argv[1]

    print(f"Working directory: {root_dir}")

    # Step 1: Find files to compile
    files = find_compilable_files(root_dir)
    print(f"Found {len(files)} files to compile")
    for f in files:
        print(f"  {f}")

    # Step 2: Compile
    compile_files(root_dir, files)

    # Step 3: Remove dev-only files
    print("\nCleaning up development files...")
    cleanup_dev_files(root_dir)

    print("\nDone! Production image is ready.")
