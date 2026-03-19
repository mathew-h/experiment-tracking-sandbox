"""
Hook: sync_docs_to_project_context.py
Event: PostToolUse (Write|Edit)

Automatically copies documentation files to docs/project_context/ so the external
team always has an up-to-date snapshot of the project's documentation.

Two sync rules:
  1. Any .md file written inside docs/ (excluding docs/working/, docs/project_context/,
     docs/superpowers/, and docs/sample_data/) is copied as-is.
  2. Any CLAUDE.md file written anywhere in the project is copied with a prefixed name:
     e.g. frontend/CLAUDE.md -> docs/project_context/frontend_CLAUDE.md
     The source files are NOT renamed — Claude Code still finds them by their original name.

Excluded from sync:
  - docs/working/      (internal session state)
  - docs/project_context/  (destination, avoid loops)
  - docs/superpowers/  (implementation plans, internal only)
  - docs/sample_data/  (binary/data files)
"""

import sys
import json
import os
import shutil


def dest_filename(file_path: str) -> str | None:
    """
    Returns the destination filename for project_context/, or None if this
    file should not be synced.
    """
    f_norm = file_path.replace("\\", "/")
    basename = os.path.basename(file_path)

    # Rule 1: CLAUDE.md files anywhere in the project
    if basename == "CLAUDE.md":
        # Derive prefix from the immediate parent directory name
        parent = os.path.basename(os.path.dirname(file_path))
        if not parent or parent in ("", "."):
            return "root_CLAUDE.md"
        return f"{parent}_CLAUDE.md"

    # Rule 2: .md files inside docs/ (with exclusions)
    if "/docs/" in f_norm and basename.endswith(".md"):
        excluded_dirs = {"project_context", "working", "superpowers", "sample_data"}
        path_parts = f_norm.split("/docs/", 1)[1].split("/")
        if path_parts[0] in excluded_dirs:
            return None
        return basename

    return None


def full_sync():
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    
    # 1. Sync all CLAUDE.md files
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # skip some dirs to avoid infinite recursion or unneeded scans
        if ".git" in dirs: dirs.remove(".git")
        if "node_modules" in dirs: dirs.remove("node_modules")
        if ".venv" in dirs: dirs.remove(".venv")
        
        for f in files:
            if f == "CLAUDE.md":
                file_path = os.path.join(root, f)
                dest_name = dest_filename(file_path)
                if dest_name:
                    dest = os.path.join(PROJECT_ROOT, "docs", "project_context", dest_name)
                    try:
                        shutil.copy2(file_path, dest)
                    except Exception:
                        pass
                        
    # 2. Sync docs/ directory files
    docs_dir = os.path.join(PROJECT_ROOT, "docs")
    if os.path.exists(docs_dir):
        for root, dirs, files in os.walk(docs_dir):
            for f in files:
                if f.endswith(".md"):
                    file_path = os.path.join(root, f)
                    dest_name = dest_filename(file_path)
                    if dest_name:
                        dest = os.path.join(PROJECT_ROOT, "docs", "project_context", dest_name)
                        try:
                            shutil.copy2(file_path, dest)
                        except Exception:
                            pass

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        full_sync()
        return

    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return

    dest_name = dest_filename(file_path)
    if not dest_name:
        return

    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    dest = os.path.join(PROJECT_ROOT, "docs", "project_context", dest_name)

    try:
        shutil.copy2(file_path, dest)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
