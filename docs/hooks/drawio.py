"""Export referenced Draw.io pages while MkDocs renders Markdown snippets."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
from xml.etree import ElementTree

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from mkdocs.structure.files import File, Files, InclusionLevel


LOG = logging.getLogger("mkdocs.hooks.drawio")

DRAWIO_REFERENCE = re.compile(
    r"!?\[(?P<alt>[^\]\n]*)\]"
    r"\(\s*(?P<path>[^)\n]+?\.drawio)::(?P<page>[^)\n]+?)\s*\)"
)
FENCE = re.compile(r"^[ \t]{0,3}(?P<marker>`{3,}|~{3,})")
PAGE_NUMBER = re.compile(r"(?:page[-_ ]?)?(?P<number>[1-9][0-9]*)", re.IGNORECASE)
EXPORT_OPTIONS = ("svg", "diagram", "transparent", "theme-auto", "border-0")

_current_page_source: Path | None = None
_current_page_uri: str | None = None
_current_files: Files | None = None
_current_config = None
_generated_root: Path | None = None


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return value or "page"


def _diagram_page(source: Path, selector: str) -> tuple[int, str, bytes]:
    try:
        content = source.read_bytes()
    except OSError as error:
        raise RuntimeError(f"Cannot read Draw.io file: {source}") from error

    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise RuntimeError(f"Invalid Draw.io XML in {source}: {error}") from error

    diagrams = [element for element in root if element.tag.rsplit("}", 1)[-1] == "diagram"]
    if not diagrams:
        raise RuntimeError(f"Draw.io file contains no pages: {source}")

    selector = selector.strip()
    exact = [
        index
        for index, diagram in enumerate(diagrams, start=1)
        if diagram.get("name") == selector
    ]
    if not exact:
        exact = [
            index
            for index, diagram in enumerate(diagrams, start=1)
            if (diagram.get("name") or "").casefold() == selector.casefold()
        ]

    if len(exact) == 1:
        page_index = exact[0]
    elif len(exact) > 1:
        raise RuntimeError(f"Draw.io page name is not unique in {source}: {selector!r}")
    else:
        match = PAGE_NUMBER.fullmatch(selector)
        if match is None:
            names = ", ".join(repr(diagram.get("name") or "") for diagram in diagrams)
            raise RuntimeError(
                f"Draw.io page {selector!r} does not exist in {source}; available: {names}"
            )
        page_index = int(match.group("number"))
        if page_index > len(diagrams):
            raise RuntimeError(
                f"Draw.io page index {page_index} is outside 1..{len(diagrams)} in {source}"
            )

    page_name = diagrams[page_index - 1].get("name") or f"page-{page_index}"
    return page_index, page_name, content


def _export_svg(source: Path, selector: str) -> str:
    if _generated_root is None:
        raise RuntimeError("Draw.io MkDocs hook has not been configured")

    page_index, page_name, content = _diagram_page(source, selector)
    digest = hashlib.sha256()
    digest.update(content)
    digest.update(str(page_index).encode())
    digest.update("\0".join(EXPORT_OPTIONS).encode())
    filename = (
        f"{_safe_name(source.stem)}-{_safe_name(page_name)}-"
        f"{digest.hexdigest()[:16]}.svg"
    )
    asset_uri = f"assets/drawio/{filename}"
    output = _generated_root / asset_uri

    if not output.is_file():
        executable = shutil.which("drawio")
        if executable is None:
            raise RuntimeError(
                "Draw.io CLI is required to build referenced diagrams; "
                "install it or make 'drawio' available on PATH"
            )

        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.{os.getpid()}.tmp.svg")
        command = [executable]
        if getattr(os, "geteuid", lambda: -1)() == 0:
            command.append("--no-sandbox")
        command.extend([
            "--disable-update",
            "--export",
            "--format",
            "svg",
            "--page-index",
            str(page_index),
            "--size",
            "diagram",
            "--transparent",
            "--theme",
            "auto",
            "--border",
            "0",
            "--output",
            str(temporary),
            str(source),
        ])
        if not os.environ.get("DISPLAY"):
            xvfb_run = shutil.which("xvfb-run")
            if xvfb_run is not None:
                command = [xvfb_run, "--auto-servernum", *command]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0 or not temporary.is_file():
                details = (result.stderr or result.stdout).strip()
                raise RuntimeError(
                    f"Draw.io export failed for {source} page {page_name!r}"
                    + (f": {details}" if details else "")
                )
            temporary.replace(output)
            LOG.info("Exported Draw.io page %s::%s", source, page_name)
        finally:
            temporary.unlink(missing_ok=True)

    _register_asset(asset_uri)
    return asset_uri


def _register_asset(asset_uri: str) -> None:
    if _current_files is None or _current_config is None or _generated_root is None:
        raise RuntimeError("Draw.io reference was processed outside an MkDocs page")
    if _current_files.get_file_from_path(asset_uri) is not None:
        return

    _current_files.append(
        File(
            asset_uri,
            src_dir=str(_generated_root),
            dest_dir=_current_config.site_dir,
            use_directory_urls=_current_config.use_directory_urls,
            inclusion=InclusionLevel.INCLUDED,
        )
    )


def _asset_link(asset_uri: str) -> str:
    if _current_page_uri is None:
        raise RuntimeError("Draw.io reference was processed outside an MkDocs page")
    page_directory = posixpath.dirname(_current_page_uri) or "."
    return posixpath.relpath(asset_uri, start=page_directory)


def _replace_reference(match: re.Match[str], markdown_source: Path) -> str:
    drawio_path = (markdown_source.parent / match.group("path").strip()).resolve()
    asset_uri = _export_svg(drawio_path, match.group("page"))
    return f"![{match.group('alt')}]({_asset_link(asset_uri)})"


def _transform_lines(lines: list[str], markdown_source: Path) -> list[str]:
    transformed = []
    fence_character = None
    fence_length = 0
    in_comment = False

    for line in lines:
        fence_match = FENCE.match(line)
        if fence_match:
            marker = fence_match.group("marker")
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            transformed.append(line)
            continue

        if in_comment:
            if "-->" in line:
                in_comment = False
            transformed.append(line)
            continue
        if "<!--" in line:
            if "-->" not in line.split("<!--", 1)[1]:
                in_comment = True
            transformed.append(line)
            continue

        if fence_character is None:
            line = DRAWIO_REFERENCE.sub(
                lambda match: _replace_reference(match, markdown_source),
                line,
            )
        transformed.append(line)

    return transformed


class DrawioPreprocessor(Preprocessor):
    def run(self, lines: list[str]) -> list[str]:
        if _current_page_source is None:
            return lines
        return _transform_lines(lines, _current_page_source)


class DrawioExtension(Extension):
    def extendMarkdown(self, md):
        try:
            snippets = md.preprocessors["snippet"]
        except KeyError:
            md.preprocessors.register(DrawioPreprocessor(md), "drawio", 31)
            return

        original_parse = snippets.parse_snippets

        def parse_snippets(lines, file_name=None, is_url=False, is_section=False):
            source = Path(file_name).resolve() if file_name else _current_page_source
            if source is not None and not is_url:
                lines = _transform_lines(lines, source)
            return original_parse(lines, file_name, is_url, is_section)

        snippets.parse_snippets = parse_snippets


def on_config(config):
    global _generated_root
    _generated_root = Path(config.config_file_path).resolve().parent / "generated"
    config.markdown_extensions.append(DrawioExtension())
    return config


def on_page_markdown(markdown, *, page, config, files):
    global _current_page_source, _current_page_uri, _current_files, _current_config
    _current_page_source = Path(page.file.abs_src_path).resolve()
    _current_page_uri = page.file.src_uri
    _current_files = files
    _current_config = config
    return markdown
