"""Check the Simple index before building a new release."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from http import HTTPStatus
import os
from pathlib import Path
import re
import tomllib
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

from packaging.utils import InvalidWheelFilename, parse_wheel_filename
from packaging.version import Version


class WheelLinks(HTMLParser):
    """Collect filenames from Simple API anchor links."""

    def __init__(self) -> None:
        """Initialize the filename collection."""
        super().__init__()
        self.filenames: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """Read filenames from href paths, ignoring labels and fragments."""
        if tag == "a" and (href := dict(attrs).get("href")):
            filename = urlsplit(href).path.rsplit("/", 1)[-1]
            self.filenames.append(unquote(filename))


def contains_wheel(html: str, name: str, version: str) -> bool:
    """Return whether links contain a wheel of this exact project/version."""
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    parser = WheelLinks()
    parser.feed(html)
    for filename in parser.filenames:
        try:
            project, wheel_version, _, _ = parse_wheel_filename(filename)
        except InvalidWheelFilename:
            continue
        if project == normalized and wheel_version == Version(version):
            return True
    return False


def wheel_exists(index_url: str, name: str, version: str) -> bool:
    """Read the public Simple index.

    Returns:
        Whether any wheel of the exact version is present.

    Raises:
        RuntimeError: If the server does not return HTML.
        HTTPError: For HTTP failures other than a missing project.
        ValueError: If the URL is not HTTPS.
    """
    if urlsplit(index_url).scheme != "https":
        raise ValueError("The package index must use HTTPS")
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    request = Request(  # ruff: ignore[suspicious-url-open-usage]
        f"{index_url.rstrip('/')}/{normalized}/",
        headers={"Accept": "application/vnd.pypi.simple.v1+html, text/html"},
    )
    try:
        with urlopen(request, timeout=30) as response:  # ruff: ignore[suspicious-url-open-usage]
            if response.headers.get_content_type() != "text/html":
                raise RuntimeError("Expected an HTML Simple index")
            html = response.read().decode("utf-8")
    except HTTPError as error:
        if error.code == HTTPStatus.NOT_FOUND:
            return False
        raise
    return contains_wheel(html, name, version)


def main() -> None:
    """Validate the tag and emit a GitHub Actions output.

    Raises:
        RuntimeError: If the release tag differs from the project version.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index-url",
        default="https://python.wattka.dev/simple/",
    )
    args = parser.parse_args()
    with Path("pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    name, version = project["name"], project["version"]
    if (
        os.environ.get("GITHUB_REF", "").startswith("refs/tags/")
        and os.environ["GITHUB_REF_NAME"] != f"v{version}"
    ):
        raise RuntimeError("Tag must match project.version")
    exists = wheel_exists(args.index_url, name, version)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"publish={str(not exists).lower()}\n")
    status = "wheel exists; skipping release" if exists else "building release"
    print(f"{name} {version}: {status}")  # ruff: ignore[print]


if __name__ == "__main__":
    main()
