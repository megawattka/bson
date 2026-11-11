"""Rename PyMongo sources, build via Hatch, and install only ``_p_bson``."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import sysconfig
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def run(*args: str) -> None:
    """Run a command with the current Python interpreter."""
    subprocess.run([sys.executable, *args], check=True)  # ruff: ignore[subprocess-without-shell-equals-true]


def patch_sources(source: Path) -> None:
    """Rename the package and its references, including C imports and Hatch."""
    (source / "bson").rename(source / "_p_bson")
    pattern = re.compile(r"(?<![A-Za-z0-9_])bson(?![A-Za-z0-9_])")
    suffixes = {".py", ".pyi", ".c", ".h", ".toml"}
    for path in source.rglob("*"):
        if path.is_file() and path.suffix in suffixes:
            text = path.read_text(encoding="utf-8")
            renamed = pattern.sub("_p_bson", text)
            if renamed != text:
                path.write_text(renamed, encoding="utf-8")

    # Includes such as bson-endian.h were renamed above as well.
    def _key(item: Path) -> int:
        return len(item.parts)

    for path in sorted(source.rglob("*"), key=_key, reverse=True):
        renamed = pattern.sub("_p_bson", path.name)
        if renamed != path.name:
            path.rename(path.with_name(renamed))


def download_source(version: str, destination: Path) -> Path:
    """Download the PyPI sdist without executing its metadata/build hooks.

    Returns:
        Path to downloaded sources.

    Raises:
        RuntimeError: if something went wrong.
    """
    url = f"https://pypi.org/pypi/pymongo/{version}/json"
    with urlopen(url, timeout=60) as response:
        metadata = json.load(response)

    archives = [
        entry for entry in metadata["urls"]
        if entry["packagetype"] == "sdist"
    ]
    if len(archives) != 1:
        raise RuntimeError(f"Expected one sdist, found {len(archives)}")

    entry = archives[0]
    log.info("Downloading %s", entry["url"])

    with urlopen(entry["url"], timeout=120) as response:  # ruff: ignore[suspicious-url-open-usage]
        data = response.read()

    if hashlib.sha256(data).hexdigest() != entry["digests"]["sha256"]:
        raise RuntimeError("PyMongo sdist SHA256 mismatch")

    archive = destination / Path(entry["filename"]).name
    archive.write_bytes(data)
    return archive


def main() -> None:
    """Build a renamed source distribution using PyMongo's original hooks.

    Raises:
        RuntimeError: if something went wrong.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="4.19.0")
    args = parser.parse_args()
    site_packages = Path(sysconfig.get_path("platlib"))

    with tempfile.TemporaryDirectory(prefix="pymongo-bson-") as temporary:
        work = Path(temporary)
        download = work / "download"
        extract = work / "source"
        wheels = work / "wheels"
        download.mkdir()
        extract.mkdir()

        run("-m", "ensurepip", "--upgrade")
        archive_path = download_source(args.version, download)

        with tarfile.open(archive_path) as archive:
            archive.extractall(extract, filter="data")
        sources = [path for path in extract.iterdir() if path.is_dir()]
        if len(sources) != 1:
            raise RuntimeError("Expected one source directory")

        source = sources[0]
        patch_sources(source)

        # pip invokes hatchling.build and its CustomHook.initialize().
        environment = os.environ.copy()
        environment["PYMONGO_C_EXT_MUST_BUILD"] = "1"
        environment.pop("NO_EXT", None)
        subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-m", "pip", "-v", "wheel", "--no-deps",
             "--wheel-dir", str(wheels), str(source)],
            env=environment,
            check=True,
        )
        built = list(wheels.glob("*.whl"))
        if len(built) != 1:
            raise RuntimeError(f"Expected one wheel, found {len(built)}")

        staged = work / "built"
        with zipfile.ZipFile(built[0]) as archive:
            archive.extractall(staged)  # ruff: ignore[tarfile-unsafe-members]

        package = staged / "_p_bson"
        if not any(package.glob("_cbson*.pyd")) and not any(
            package.glob("_cbson*.so"),
        ):
            raise RuntimeError("The wheel has no compiled _p_bson._cbson")

        target = site_packages / "_p_bson"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(package, target)

        run(
            "-c",
            "import elune, _p_bson; from _p_bson import _cbson; "
            "assert _p_bson.has_c(); "
            "assert _p_bson.decode(_p_bson.encode({'x': 42})) == {'x': 42}; "
            "assert _p_bson.InvalidBSON is not elune.InvalidBSON; "
            "print(_cbson.__file__)",
        )
        log.info("Installed compiled PyMongo BSON package as %s", target)


if __name__ == "__main__":
    main()
