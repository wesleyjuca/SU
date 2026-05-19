"""Geração de PDFs para petições e relatórios AFJ."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

AFJ_OFFICE = "Almeida, Freire & Jucá Advogados"
AFJ_ADDRESS = "Rua das Flores, 123 — Centro — Fortaleza/CE — CEP 60.000-000"
AFJ_CONTACT = "Tel: (85) 3333-4444 | contato@afjadvogados.com.br"
AFJ_OAB = "OAB/CE 00.000"


def _try_reportlab(title: str, body_lines: list[str], metadata: dict) -> bytes | None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=3 * cm,
            rightMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2.5 * cm,
        )

        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(
            "AFJHeader",
            parent=styles["Normal"],
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1A1A1A"),
        )
        gold_style = ParagraphStyle(
            "AFJGold",
            parent=styles["Normal"],
            fontSize=11,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#C9A84C"),
            fontName="Times-Bold",
        )
        title_style = ParagraphStyle(
            "AFJTitle",
            parent=styles["Normal"],
            fontSize=14,
            fontName="Times-Bold",
            alignment=TA_CENTER,
            spaceAfter=12,
        )
        body_style = ParagraphStyle(
            "AFJBody",
            parent=styles["Normal"],
            fontSize=12,
            fontName="Times-Roman",
            leading=18,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        )

        story = []

        story.append(Paragraph(AFJ_OFFICE, gold_style))
        story.append(Paragraph(AFJ_ADDRESS, header_style))
        story.append(Paragraph(f"{AFJ_CONTACT} | {AFJ_OAB}", header_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#C9A84C"), spaceAfter=12))

        story.append(Paragraph(title.upper(), title_style))
        story.append(Spacer(1, 0.5 * cm))

        for line in body_lines:
            if line.strip():
                story.append(Paragraph(line.replace("\n", "<br/>"), body_style))
            else:
                story.append(Spacer(1, 0.3 * cm))

        story.append(Spacer(1, 1 * cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#C9A84C")))
        story.append(Spacer(1, 0.3 * cm))

        gen_at = datetime.utcnow().strftime("%d/%m/%Y às %H:%M UTC")
        story.append(Paragraph(f"Documento gerado em {gen_at} — Sistema AFJ CORE", header_style))

        doc.build(story)
        return buf.getvalue()
    except ImportError:
        return None


def _fallback_pdf(title: str, body_lines: list[str], metadata: dict) -> bytes:
    """Minimal PDF without external dependencies."""
    now = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
    text_lines = [
        f"% {AFJ_OFFICE}",
        f"% {AFJ_ADDRESS}",
        f"% {AFJ_CONTACT}",
        "",
        title.upper(),
        "=" * 60,
        "",
        *body_lines,
        "",
        "=" * 60,
        f"Gerado em {now} — Sistema AFJ CORE",
    ]

    content = "\n".join(text_lines).encode("utf-8")

    header = b"%PDF-1.4\n"
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"

    page_text = content.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    stream = b"BT /F1 10 Tf 50 750 Td 12 TL " + b"(" + page_text + b") Tj ET"
    obj4 = b"4 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream\nendobj\n"
    obj3 = b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Courier >> >> >> >>\nendobj\n"

    body = header + obj1 + obj2 + obj3 + obj4
    xref_offset = len(body)
    xref = b"xref\n0 5\n0000000000 65535 f \n"
    offsets = [len(header), len(header) + len(obj1), len(header) + len(obj1) + len(obj2),
               len(header) + len(obj1) + len(obj2) + len(obj4),
               len(header) + len(obj1) + len(obj2)]
    for off in offsets[1:]:
        xref += str(off).zfill(10).encode() + b" 00000 n \n"

    trailer = b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n" + str(xref_offset).encode() + b"\n%%EOF\n"
    return body + xref + trailer


def build_petition_pdf(title: str, content_html: str, metadata: dict[str, Any] | None = None) -> bytes:
    """Gera PDF de petição a partir de conteúdo HTML."""
    import re
    metadata = metadata or {}
    clean = re.sub(r"<[^>]+>", "\n", content_html)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    lines = clean.split("\n")

    result = _try_reportlab(title, lines, metadata)
    if result:
        return result
    return _fallback_pdf(title, lines, metadata)


def build_report_pdf(title: str, sections: list[dict[str, str]]) -> bytes:
    """Gera PDF de relatório com seções nomeadas."""
    lines = []
    for sec in sections:
        heading = sec.get("heading", "")
        body = sec.get("body", "")
        if heading:
            lines.append(f"\n{heading.upper()}\n{'—' * len(heading)}")
        lines.extend(body.split("\n"))

    result = _try_reportlab(title, lines, {})
    if result:
        return result
    return _fallback_pdf(title, lines, {})
