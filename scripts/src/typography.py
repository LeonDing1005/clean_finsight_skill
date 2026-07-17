"""Central typography settings and helpers for reports and charts."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Any, Iterable


# Change fonts here. Document text, generated charts, and prompt examples all
# consume these values.
LATIN_FONT = "Times New Roman"
CJK_FONT = "Microsoft YaHei"
CHART_CJK_FONT_CANDIDATES = (
    CJK_FONT,
    "SimHei",
    "KaiTi",
    "WenQuanYi Micro Hei",
    "Noto Sans CJK SC",
)
CHART_FALLBACK_FONT = "DejaVu Sans"


_TYPOGRAPHY_TOKENS = {
    "__LATIN_FONT__": LATIN_FONT,
    "__CHART_CJK_FONT__": CJK_FONT,
    "__CHART_CJK_FONT_CANDIDATES__": repr(list(CHART_CJK_FONT_CANDIDATES)),
    "__CHART_FONT_FAMILIES__": repr(
        [LATIN_FONT, *CHART_CJK_FONT_CANDIDATES, CHART_FALLBACK_FONT]
    ),
}


def apply_typography_tokens(value: Any) -> Any:
    """Replace typography tokens recursively in loaded prompt data."""
    if isinstance(value, dict):
        return {key: apply_typography_tokens(item) for key, item in value.items()}
    if isinstance(value, list):
        return [apply_typography_tokens(item) for item in value]
    if not isinstance(value, str):
        return value
    for token, replacement in _TYPOGRAPHY_TOKENS.items():
        value = value.replace(token, replacement)
    return value


def chart_font_families(extra_families: Iterable[str] = ()) -> list[str]:
    """Return the shared Matplotlib fallback chain, without duplicates."""
    ordered = [
        LATIN_FONT,
        *extra_families,
        *CHART_CJK_FONT_CANDIDATES,
        CHART_FALLBACK_FONT,
    ]
    return list(dict.fromkeys(font for font in ordered if font))


def pandoc_pdf_font_args() -> list[str]:
    """Return the shared XeLaTeX font variables for direct PDF output."""
    return [
        f"--variable=mainfont:{LATIN_FONT}",
        f"--variable=sansfont:{LATIN_FONT}",
        f"--variable=monofont:{LATIN_FONT}",
        f"--variable=CJKmainfont:{CJK_FONT}",
    ]


def configure_matplotlib_fonts(matplotlib_module, extra_families: Iterable[str] = ()) -> list[str]:
    """Apply the shared Latin-first font chain to Matplotlib."""
    families = chart_font_families(extra_families)
    matplotlib_module.rcParams["font.family"] = families
    matplotlib_module.rcParams["font.serif"] = families
    matplotlib_module.rcParams["font.sans-serif"] = families
    matplotlib_module.rcParams["axes.unicode_minus"] = False
    return families


def enforce_figure_text_fonts(figure, extra_families: Iterable[str] = ()) -> int:
    """Apply the configured fallback chain to every text artist in a figure."""
    families = chart_font_families(extra_families)
    count = 0
    for artist in figure.findobj():
        if hasattr(artist, "set_fontfamily"):
            artist.set_fontfamily(families)
            count += 1
    return count


def matplotlib_setup_code() -> str:
    """Return setup code for generated Python execution environments.

    The save hook reapplies the configured family to every text artist just
    before rasterization, so generated code cannot accidentally force a CJK
    font onto Latin letters and digits.
    """
    families = repr(chart_font_families())
    return (
        "import matplotlib\n"
        "import matplotlib.pyplot as plt\n"
        "from matplotlib.figure import Figure as _FinsightFigure\n"
        f"_finsight_font_families = {families}\n"
        "matplotlib.rcParams['font.family'] = _finsight_font_families\n"
        "matplotlib.rcParams['font.serif'] = _finsight_font_families\n"
        "matplotlib.rcParams['font.sans-serif'] = _finsight_font_families\n"
        "matplotlib.rcParams['axes.unicode_minus'] = False\n"
        "if not hasattr(_FinsightFigure, '_finsight_original_savefig'):\n"
        "    _FinsightFigure._finsight_original_savefig = _FinsightFigure.savefig\n"
        "    def _finsight_savefig(self, *args, **kwargs):\n"
        "        for _artist in self.findobj():\n"
        "            if hasattr(_artist, 'set_fontfamily'):\n"
        "                _artist.set_fontfamily(_finsight_font_families)\n"
        "        return self._finsight_original_savefig(*args, **kwargs)\n"
        "    _FinsightFigure.savefig = _finsight_savefig"
    )


def normalize_docx_typography(docx_path: str | os.PathLike[str]) -> dict[str, int]:
    """Force every Latin Word font slot to ``LATIN_FONT``.

    The pass covers styles, runs, paragraph run properties, numbering levels,
    headers, footers, notes, comments, fields, and DrawingML theme fallbacks.
    East Asian font slots are preserved.
    """
    from lxml import etree

    path = Path(docx_path)
    tmp_path = path.with_suffix(path.suffix + ".typography.tmp")
    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    w = f"{{{w_ns}}}"
    a = f"{{{a_ns}}}"
    ns = {"w": w_ns, "a": a_ns}
    stats = {"parts": 0, "runs": 0, "styles": 0, "numbering_levels": 0, "fonts": 0}

    def set_run_fonts(r_fonts) -> None:
        r_fonts.set(w + "ascii", LATIN_FONT)
        r_fonts.set(w + "hAnsi", LATIN_FONT)
        for attr in (w + "asciiTheme", w + "hAnsiTheme", w + "hint"):
            r_fonts.attrib.pop(attr, None)
        stats["fonts"] += 1

    def ensure_r_fonts(r_pr):
        r_fonts = r_pr.find(w + "rFonts")
        if r_fonts is None:
            r_fonts = etree.Element(w + "rFonts")
            r_pr.insert(0, r_fonts)
        set_run_fonts(r_fonts)
        return r_fonts

    def ensure_run_properties(parent, tag: str, *, append: bool = False):
        r_pr = parent.find(tag)
        if r_pr is None:
            r_pr = etree.Element(tag)
            if append:
                parent.append(r_pr)
            else:
                parent.insert(0, r_pr)
        ensure_r_fonts(r_pr)

    def ensure_style_run_properties(style) -> None:
        r_pr = style.find(w + "rPr")
        if r_pr is None:
            r_pr = etree.Element(w + "rPr")
            following_tags = {
                w + "tblPr",
                w + "trPr",
                w + "tcPr",
                w + "tblStylePr",
            }
            insert_at = next(
                (index for index, child in enumerate(style) if child.tag in following_tags),
                len(style),
            )
            style.insert(insert_at, r_pr)
        ensure_r_fonts(r_pr)

    def normalize_xml(filename: str, data: bytes) -> bytes:
        parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
        root = etree.fromstring(data, parser)
        changed = False

        # Normalize every existing run-properties block, including paragraph
        # marks, conditional table styles, and tracked formatting changes.
        for r_pr in root.xpath(".//w:rPr", namespaces=ns):
            ensure_r_fonts(r_pr)
            changed = True

        # Runs without rPr otherwise continue to inherit conflicting styles.
        for run in root.xpath(".//w:r", namespaces=ns):
            ensure_run_properties(run, w + "rPr")
            stats["runs"] += 1
            changed = True

        if filename in {"word/styles.xml", "word/stylesWithEffects.xml"}:
            doc_defaults = root.find(w + "docDefaults")
            if doc_defaults is None:
                doc_defaults = etree.Element(w + "docDefaults")
                root.insert(0, doc_defaults)
            r_pr_default = doc_defaults.find(w + "rPrDefault")
            if r_pr_default is None:
                r_pr_default = etree.SubElement(doc_defaults, w + "rPrDefault")
            ensure_run_properties(r_pr_default, w + "rPr", append=True)

            for style in root.findall(w + "style"):
                ensure_style_run_properties(style)
                stats["styles"] += 1
            changed = True

        if filename == "word/numbering.xml":
            for level in root.xpath(".//w:lvl", namespaces=ns):
                r_pr = level.find(w + "rPr")
                if r_pr is None:
                    r_pr = etree.SubElement(level, w + "rPr")
                ensure_r_fonts(r_pr)
                stats["numbering_levels"] += 1
            changed = True

        # Theme and DrawingML text are fallback paths for fields and shapes.
        for latin in root.xpath(".//a:latin", namespaces=ns):
            latin.set("typeface", LATIN_FONT)
            changed = True

        if not changed:
            return data
        stats["parts"] += 1
        return etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )

    try:
        with zipfile.ZipFile(path, "r") as source:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as target:
                for item in source.infolist():
                    data = source.read(item.filename)
                    if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                        data = normalize_xml(item.filename, data)
                    target.writestr(item, data)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return stats
