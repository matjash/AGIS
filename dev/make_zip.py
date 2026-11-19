"""Build the release zip for plugins.qgis.org.

Run from anywhere:   python dev/make_zip.py
Writes agis-<version>.zip next to the plugin folder.

Only files tracked by git go into the zip (so stray local files never ship),
without dev/, .git*, __pycache__ and *.pyc (plugins.qgis.org rejects .pyc).
"""
import configparser
import subprocess
import sys
import zipfile
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
PACKAGE = "agis"          # folder name inside the zip = plugin id
EXCLUDE_DIRS = ("dev/", ".github/")
EXCLUDE_FILES = (".gitignore", ".gitattributes")


def main():
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(PLUGIN_DIR / "metadata.txt", encoding="utf-8")
    version = cp.get("general", "version")

    files = subprocess.run(["git", "ls-files", "-z"], cwd=PLUGIN_DIR, check=True,
                           capture_output=True).stdout.decode("utf-8").split("\0")
    files = [f for f in files if f
             and not f.startswith(EXCLUDE_DIRS)
             and Path(f).name not in EXCLUDE_FILES
             and "__pycache__" not in f
             and not f.endswith(".pyc")
             and (PLUGIN_DIR / f).is_file()]

    out = PLUGIN_DIR.parent / f"{PACKAGE}-{version}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(files):
            z.write(PLUGIN_DIR / f, f"{PACKAGE}/{f}")
    print(f"{out}  ({len(files)} files)")


if __name__ == "__main__":
    sys.exit(main())
