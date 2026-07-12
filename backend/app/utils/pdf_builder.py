"""Geração de PDFs para petições e relatórios AFJ."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

AFJ_OFFICE = "Almeida, Freire & Jucá Advogados"
AFJ_ADDRESS = "Rua das Flores, 123 — Centro — Fortaleza/CE — CEP 60.000-000"
AFJ_CONTACT = "Tel: (85) 3333-4444 | contato@afjadvogados.com.br"
AFJ_OAB = "OAB/CE 00.000"


def _resolve_letterhead(letterhead: dict | None) -> dict:
    """Normaliza o timbrado: se o escritório configurou QUALQUER campo, usa só
    o que foi configurado (linhas vazias somem); senão, padrão AFJ (fallback)."""
    lh = letterhead or {}
    campos = ("office_name", "address", "contact", "oab", "footer")
    custom = any(lh.get(k) for k in campos)
    if custom:
        contato = lh.get("contact") or ""
        oab = lh.get("oab") or ""
        linha_contato = " | ".join(x for x in (contato, oab) if x) or None
        return {
            "office": lh.get("office_name"),
            "address": lh.get("address"),
            "contact_line": linha_contato,
            "footer": lh.get("footer"),
            "logo_data_url": lh.get("logo_data_url") if lh.get("use_logo", True) else None,
        }
    return {
        "office": AFJ_OFFICE,
        "address": AFJ_ADDRESS,
        "contact_line": f"{AFJ_CONTACT} | {AFJ_OAB}",
        "footer": None,
        "logo_data_url": lh.get("logo_data_url") if lh.get("use_logo", True) else None,
    }


def _try_reportlab(title: str, body_lines: list[str], metadata: dict, letterhead: dict | None = None) -> bytes | None:
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

        lh = _resolve_letterhead(letterhead)

        # Logo do escritório no topo (opcional; falha de decodificação não quebra o PDF)
        if lh.get("logo_data_url"):
            try:
                import base64 as _b64
                from reportlab.platypus import Image as RLImage
                from reportlab.lib.utils import ImageReader

                data_url = lh["logo_data_url"]
                raw = _b64.b64decode(data_url.split(",", 1)[1])
                img_reader = ImageReader(io.BytesIO(raw))
                iw, ih = img_reader.getSize()
                h = 1.5 * cm
                w = iw * (h / ih) if ih else h
                logo = RLImage(io.BytesIO(raw), width=w, height=h)
                logo.hAlign = "CENTER"
                story.append(logo)
                story.append(Spacer(1, 0.2 * cm))
            except Exception:
                pass

        if lh.get("office"):
            story.append(Paragraph(lh["office"], gold_style))
        if lh.get("address"):
            story.append(Paragraph(lh["address"], header_style))
        if lh.get("contact_line"):
            story.append(Paragraph(lh["contact_line"], header_style))
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
        if lh.get("footer"):
            story.append(Paragraph(lh["footer"], header_style))
        story.append(Paragraph(f"Documento gerado em {gen_at} — Sistema AFJ CORE", header_style))

        doc.build(story)
        return buf.getvalue()
    except ImportError:
        return None


def _fallback_pdf(title: str, body_lines: list[str], metadata: dict, letterhead: dict | None = None) -> bytes:
    """Minimal PDF without external dependencies."""
    lh = _resolve_letterhead(letterhead)
    now = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
    text_lines = [
        f"% {lh.get('office') or AFJ_OFFICE}",
        f"% {lh.get('address') or ''}",
        f"% {lh.get('contact_line') or ''}",
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


def build_petition_pdf(
    title: str,
    content_html: str,
    metadata: dict[str, Any] | None = None,
    letterhead: dict | None = None,
) -> bytes:
    """Gera PDF de petição a partir de conteúdo HTML, com timbrado do escritório."""
    import re
    metadata = metadata or {}
    clean = re.sub(r"<[^>]+>", "\n", content_html)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    lines = clean.split("\n")

    result = _try_reportlab(title, lines, metadata, letterhead)
    if result:
        return result
    return _fallback_pdf(title, lines, metadata, letterhead)


def build_consolidated_pdf(
    banca_name: str,
    periodo_label: str,
    linhas: list[dict[str, Any]],
    totais: dict[str, Any],
    letterhead: dict | None = None,
) -> bytes:
    """Gera o PDF do relatório consolidado da banca com tabela real (matriz por unidade).

    Fallback para texto (build_report_pdf) se reportlab não estiver disponível.
    """
    def _brl(v: float) -> str:
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=landscape(A4),
            leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        )
        styles = getSampleStyleSheet()
        gold = ParagraphStyle("g", parent=styles["Normal"], fontSize=13, alignment=TA_CENTER,
                              textColor=colors.HexColor("#C9A84C"), fontName="Times-Bold")
        header_style = ParagraphStyle("h", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER,
                                      textColor=colors.HexColor("#1A1A1A"))
        title_style = ParagraphStyle("t", parent=styles["Normal"], fontSize=13, fontName="Times-Bold",
                                     alignment=TA_CENTER, spaceAfter=4)

        story = []
        lh = _resolve_letterhead(letterhead)
        if lh.get("logo_data_url"):
            try:
                import base64 as _b64
                from reportlab.platypus import Image as RLImage
                from reportlab.lib.utils import ImageReader
                raw = _b64.b64decode(lh["logo_data_url"].split(",", 1)[1])
                iw, ih = ImageReader(io.BytesIO(raw)).getSize()
                h = 1.3 * cm
                logo = RLImage(io.BytesIO(raw), width=(iw * (h / ih) if ih else h), height=h)
                logo.hAlign = "CENTER"
                story.append(logo)
                story.append(Spacer(1, 0.15 * cm))
            except Exception:
                pass
        if lh.get("office"):
            story.append(Paragraph(lh["office"], gold))
        if lh.get("contact_line"):
            story.append(Paragraph(lh["contact_line"], header_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#C9A84C"), spaceAfter=10))

        story.append(Paragraph(f"Relatório Consolidado — {banca_name}", title_style))
        story.append(Paragraph(periodo_label, header_style))
        story.append(Spacer(1, 0.5 * cm))

        header = ["Unidade", "Proc. ativos", "Proc. total", "Receita mês", "Despesa mês",
                  "Saldo mês", "Custo IA", "Execuções", "Usuários"]
        data = [header]
        for l in linhas:
            data.append([
                l["unidade"], str(l["processos_ativos"]), str(l["processos_total"]),
                _brl(l["receita_mes"]), _brl(l["despesa_mes"]), _brl(l["saldo_mes"]),
                f"$ {l['custo_ia_mes']:.2f}", str(l["execucoes_mes"]), str(l["usuarios_ativos"]),
            ])
        data.append([
            "TOTAL DA BANCA", str(totais["processos_ativos"]), str(totais["processos_total"]),
            _brl(totais["receita_mes"]), _brl(totais["despesa_mes"]), _brl(totais["saldo_mes"]),
            f"$ {totais['custo_ia_mes']:.2f}", str(totais["execucoes_mes"]), str(totais["usuarios_ativos"]),
        ])

        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E2229")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F7F3EC")]),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#C9A84C")),
            ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9D2C4")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

        story.append(Spacer(1, 0.8 * cm))
        gen_at = datetime.utcnow().strftime("%d/%m/%Y às %H:%M UTC")
        story.append(Paragraph(f"Documento gerado em {gen_at} — Sistema AFJ CORE", header_style))
        doc.build(story)
        return buf.getvalue()
    except ImportError:
        # Fallback textual (sem reportlab)
        linhas_txt = []
        for l in linhas:
            linhas_txt.append(
                f"{l['unidade']}: ativos={l['processos_ativos']} total={l['processos_total']} "
                f"receita={_brl(l['receita_mes'])} despesa={_brl(l['despesa_mes'])} "
                f"saldo={_brl(l['saldo_mes'])} IA=${l['custo_ia_mes']:.2f} usuarios={l['usuarios_ativos']}"
            )
        linhas_txt.append(
            f"TOTAL: ativos={totais['processos_ativos']} receita={_brl(totais['receita_mes'])} "
            f"despesa={_brl(totais['despesa_mes'])} saldo={_brl(totais['saldo_mes'])}"
        )
        return build_report_pdf(
            f"Relatório Consolidado — {banca_name}",
            [{"heading": periodo_label, "body": "\n".join(linhas_txt)}],
            letterhead,
        )


def build_invoice_pdf(
    numero: str,
    cliente_nome: str,
    periodo: str,
    itens: list[dict[str, Any]],
    valor_total: float,
    data_vencimento: str | None = None,
    letterhead: dict | None = None,
) -> bytes:
    """PDF de fatura de honorários com timbrado da banca e tabela de itens."""
    def _brl(v) -> str:
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2.5 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
        styles = getSampleStyleSheet()
        gold = ParagraphStyle("g", parent=styles["Normal"], fontSize=13, alignment=TA_CENTER, textColor=colors.HexColor("#C9A84C"), fontName="Times-Bold")
        header_style = ParagraphStyle("h", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#1A1A1A"))
        title_style = ParagraphStyle("t", parent=styles["Normal"], fontSize=14, fontName="Times-Bold", alignment=TA_CENTER, spaceAfter=6)
        body = ParagraphStyle("b", parent=styles["Normal"], fontSize=10, fontName="Times-Roman", leading=16)

        story = []
        lh = _resolve_letterhead(letterhead)
        if lh.get("logo_data_url"):
            try:
                import base64 as _b64
                from reportlab.platypus import Image as RLImage
                from reportlab.lib.utils import ImageReader
                raw = _b64.b64decode(lh["logo_data_url"].split(",", 1)[1])
                iw, ih = ImageReader(io.BytesIO(raw)).getSize()
                h = 1.4 * cm
                logo = RLImage(io.BytesIO(raw), width=(iw * (h / ih) if ih else h), height=h)
                logo.hAlign = "CENTER"
                story.append(logo)
                story.append(Spacer(1, 0.15 * cm))
            except Exception:
                pass
        if lh.get("office"):
            story.append(Paragraph(lh["office"], gold))
        if lh.get("address"):
            story.append(Paragraph(lh["address"], header_style))
        if lh.get("contact_line"):
            story.append(Paragraph(lh["contact_line"], header_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#C9A84C"), spaceAfter=12))

        story.append(Paragraph(f"FATURA Nº {numero}", title_style))
        story.append(Paragraph(f"<b>Cliente:</b> {cliente_nome}", body))
        if periodo:
            story.append(Paragraph(f"<b>Período:</b> {periodo}", body))
        if data_vencimento:
            story.append(Paragraph(f"<b>Vencimento:</b> {data_vencimento}", body))
        story.append(Spacer(1, 0.5 * cm))

        data = [["Descrição", "Valor"]]
        for it in itens:
            data.append([str(it.get("descricao", "")), _brl(it.get("valor", 0))])
        data.append(["TOTAL", _brl(valor_total)])
        table = Table(data, colWidths=[13 * cm, 4 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E2229")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F7F3EC")]),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#C9A84C")),
            ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9D2C4")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
        story.append(Spacer(1, 1 * cm))
        gen_at = datetime.utcnow().strftime("%d/%m/%Y às %H:%M UTC")
        if lh.get("footer"):
            story.append(Paragraph(lh["footer"], header_style))
        story.append(Paragraph(f"Fatura gerada em {gen_at} — Sistema AFJ CORE", header_style))
        doc.build(story)
        return buf.getvalue()
    except ImportError:
        linhas = [f"{it.get('descricao','')}: {_brl(it.get('valor',0))}" for it in itens]
        linhas.append(f"TOTAL: {_brl(valor_total)}")
        return build_report_pdf(
            f"Fatura Nº {numero}",
            [{"heading": f"Cliente: {cliente_nome}", "body": "\n".join(linhas)}],
            letterhead,
        )


def build_report_pdf(title: str, sections: list[dict[str, str]], letterhead: dict | None = None) -> bytes:
    """Gera PDF de relatório com seções nomeadas."""
    lines = []
    for sec in sections:
        heading = sec.get("heading", "")
        body = sec.get("body", "")
        if heading:
            lines.append(f"\n{heading.upper()}\n{'—' * len(heading)}")
        lines.extend(body.split("\n"))

    result = _try_reportlab(title, lines, {}, letterhead)
    if result:
        return result
    return _fallback_pdf(title, lines, {}, letterhead)
