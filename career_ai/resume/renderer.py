"""Render a résumé JSON dict into an ATS-friendly DOCX, then optionally to PDF.

ATS-safe formula (what Greenhouse/Lever/Ashby parsers actually handle well):
  - Single column, no tables, no text boxes, no headers/footers
  - Calibri 11pt body, 14pt name, 12pt section headings
  - Standard section names: "Summary", "Experience", "Skills", "Education"
  - Bullets are real Word bullets (List Bullet style)
  - No images, no multi-column layouts, no fancy styling

PDF conversion uses docx2pdf (Word COM on Windows, LibreOffice on Linux/mac).
It's best-effort: if conversion fails, the DOCX still uploads fine — every
major ATS accepts both formats.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def render_docx(resume: dict, output_path: str | Path) -> Path:
    """Render the résumé JSON to a DOCX file. Returns the path.

    Raises ImportError if python-docx is not installed.
    """
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
    except ImportError as exc:
        raise ImportError(
            "python-docx is required to render résumés. "
            "Install with: pip install python-docx>=1.1"
        ) from exc

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()

    # Default font for the whole document
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # --- Header: name + contact line ---
    name = resume.get("name") or ""
    if name:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(name)
        run.bold = True
        run.font.size = Pt(16)

    contact = resume.get("contact") or {}
    contact_bits: list[str] = []
    for key in ("email", "phone", "location"):
        val = (contact.get(key) or "").strip()
        if val:
            contact_bits.append(val)
    for link in contact.get("links") or []:
        link_str = str(link).strip()
        if link_str:
            contact_bits.append(link_str)
    if contact_bits:
        p = doc.add_paragraph(" | ".join(contact_bits))
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.font.size = Pt(10)

    # --- Summary ---
    summary = (resume.get("summary") or "").strip()
    if summary:
        _add_heading(doc, "Summary")
        doc.add_paragraph(summary)

    # --- Experience ---
    experience = resume.get("experience") or []
    if experience:
        _add_heading(doc, "Experience")
        for role in experience:
            _add_role(doc, role)

    # --- Skills ---
    skills = resume.get("skills") or []
    if skills:
        _add_heading(doc, "Skills")
        doc.add_paragraph(", ".join(str(s) for s in skills if str(s).strip()))

    # --- Education ---
    education = resume.get("education") or []
    if education:
        _add_heading(doc, "Education")
        for edu in education:
            school = (edu.get("school") or "").strip()
            degree = (edu.get("degree") or "").strip()
            dates = (edu.get("dates") or "").strip()
            line = school
            if degree:
                line = f"{degree}, {school}" if school else degree
            p = doc.add_paragraph()
            run_main = p.add_run(line)
            run_main.bold = True
            if dates:
                p.add_run(f"  —  {dates}")

    doc.save(str(path))
    return path


def convert_to_pdf(docx_path: str | Path, pdf_path: str | Path) -> Path | None:
    """Convert a DOCX to PDF. Returns the PDF path on success, None on failure.

    Never raises — this is best-effort. On Windows it uses Word via COM; on
    Linux/mac it shells out to LibreOffice. Either may be unavailable.
    """
    src = Path(docx_path)
    dst = Path(pdf_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        from docx2pdf import convert
    except ImportError:
        return None

    try:
        convert(str(src), str(dst))
    except Exception:
        # Word/LibreOffice absent, locked file, etc. — fall back to DOCX only.
        return None

    return dst if dst.exists() else None


# --- internals ---

def _add_heading(doc: Any, text: str) -> None:
    """Section heading: bold 12pt, underlined by adding a border-ish rule.

    We use a plain bold paragraph (no Word Heading styles) so that ATS
    parsers which strip styles still see clean visual blocks.
    """
    from docx.shared import Pt

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(12)


def _add_role(doc: Any, role: dict) -> None:
    from docx.shared import Pt

    company = (role.get("company") or "").strip()
    title = (role.get("title") or "").strip()
    dates = (role.get("dates") or "").strip()
    location = (role.get("location") or "").strip()

    # Line 1: Title @ Company  —  dates
    header = doc.add_paragraph()
    left_parts = []
    if title:
        left_parts.append(title)
    if company:
        left_parts.append(company)
    left_text = " @ ".join(left_parts) if len(left_parts) == 2 else (left_parts[0] if left_parts else "")
    if left_text:
        r = header.add_run(left_text)
        r.bold = True
        r.font.size = Pt(11)
    if dates:
        r = header.add_run(f"  —  {dates}")
        r.font.size = Pt(11)

    if location:
        loc_p = doc.add_paragraph(location)
        for r in loc_p.runs:
            r.font.size = Pt(10)
            r.italic = True

    for bullet in role.get("bullets") or []:
        text = str(bullet).strip()
        if not text:
            continue
        # "List Bullet" is a Word built-in style every parser recognises
        try:
            doc.add_paragraph(text, style="List Bullet")
        except KeyError:
            # Template doesn't have the style for some reason — fall back to
            # a Unicode bullet so output is still readable.
            doc.add_paragraph(f"\u2022 {text}")
