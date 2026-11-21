
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)

from .calculations import monthly_installment


def generate_agreement_pdf(loan, agreement):
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    navy = colors.HexColor("#163A63")
    light_blue = colors.HexColor("#EAF2F8")
    muted = colors.HexColor("#64748B")
    border = colors.HexColor("#D5DEE8")

    title_style = ParagraphStyle(
        "AgreementTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=26,
        textColor=navy,
        alignment=TA_CENTER,
        spaceAfter=5,
    )

    subtitle_style = ParagraphStyle(
        "AgreementSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=muted,
        alignment=TA_CENTER,
        spaceAfter=18,
    )

    section_style = ParagraphStyle(
        "AgreementSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=navy,
        spaceBefore=12,
        spaceAfter=8,
    )

    body_style = ParagraphStyle(
        "AgreementBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=14,
        textColor=colors.HexColor("#263445"),
        alignment=0,
        spaceAfter=7,
    )

    label_style = ParagraphStyle(
        "AgreementLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=12,
        textColor=navy,
    )

    value_style = ParagraphStyle(
        "AgreementValue",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#263445"),
    )

    elements = []

    elements.append(
        Paragraph("BAYAN BANK", title_style)
    )

    elements.append(
        Paragraph("LOAN AGREEMENT", subtitle_style)
    )

    elements.append(
        Paragraph(
            "AGREEMENT DETAILS",
            section_style,
        )
    )

    monthly = monthly_installment(
        loan.principal,
        loan.annual_rate,
        loan.term_months,
    )

    data = [
        ("Agreement Number", agreement.agreement_number),
        ("Agreement Date", agreement.agreement_date),
        ("Loan Number", loan.pk),
        ("Borrower", loan.client),
        ("Loan Product", loan.product.name),
        ("Principal", f"PHP {loan.principal:,.2f}"),
        ("Annual Interest Rate", f"{loan.annual_rate}%"),
        ("Loan Term", f"{loan.term_months} months"),
        ("Estimated Monthly Payment", f"PHP {monthly:,.2f}"),
        ("Loan Status", loan.get_status_display()),
    ]

    table_data = []

    for label, value in data:
        table_data.append([
            Paragraph(
                escape(str(label)),
                label_style,
            ),
            Paragraph(
                escape(str(value)),
                value_style,
            ),
        ])

    table = Table(
        table_data,
        colWidths=[58 * mm, 112 * mm],
        hAlign="LEFT",
    )

    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), light_blue),
            ("BACKGROUND", (1, 0), (1, -1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, border),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )

    elements.append(table)
    elements.append(Spacer(1, 12))

    elements.append(
        Paragraph(
            "TERMS AND CONDITIONS",
            section_style,
        )
    )

    terms = (
        agreement.terms_and_conditions
        or "No additional terms and conditions provided."
    )

    for paragraph_text in terms.splitlines():
        paragraph_text = paragraph_text.strip()

        if paragraph_text:
            elements.append(
                Paragraph(
                    escape(paragraph_text),
                    body_style,
                )
            )

    elements.append(Spacer(1, 18))

    elements.append(
        Paragraph(
            "AGREEMENT ACCEPTANCE",
            section_style,
        )
    )

    if agreement.signed_at:
        signed_date = agreement.signed_at.strftime(
            "%B %d, %Y at %I:%M %p"
        )

        acceptance_text = (
            f"<b>Electronically accepted</b><br/>"
            f"Acceptance Date: {escape(signed_date)}"
        )

        acceptance_color = colors.HexColor("#E8F5E9")
        acceptance_text_color = colors.HexColor("#166534")

    else:
        acceptance_text = (
            "<b>Not yet accepted by the borrower.</b><br/>"
            "The borrower must review and accept this agreement "
            "before loan disbursement."
        )

        acceptance_color = colors.HexColor("#FFF7E6")
        acceptance_text_color = colors.HexColor("#92400E")

    acceptance_style = ParagraphStyle(
        "Acceptance",
        parent=body_style,
        textColor=acceptance_text_color,
        leading=15,
    )

    acceptance_table = Table(
        [[
            Paragraph(
                acceptance_text,
                acceptance_style,
            )
        ]],
        colWidths=[170 * mm],
    )

    acceptance_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), acceptance_color),
            ("BOX", (0, 0), (-1, -1), 0.6, border),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ])
    )

    elements.append(
        KeepTogether([
            acceptance_table,
            Spacer(1, 18),
            Paragraph(
                "This document is generated electronically by Bayan Bank. "
                "The electronic acceptance status shown above reflects "
                "the agreement record in the banking system.",
                ParagraphStyle(
                    "FooterNote",
                    parent=styles["Normal"],
                    fontSize=7.5,
                    leading=10,
                    textColor=muted,
                    alignment=TA_CENTER,
                ),
            ),
        ])
    )

    document.build(elements)

    pdf = buffer.getvalue()
    buffer.close()

    return pdf
