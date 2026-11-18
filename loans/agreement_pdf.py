
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Preformatted,
)

from .calculations import monthly_installment


def generate_agreement_pdf(loan, agreement):
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "AgreementTitle",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=17,
        spaceAfter=15,
    )

    elements = []

    elements.append(
        Paragraph(
            "BAYAN BANK",
            title_style,
        )
    )

    elements.append(
        Paragraph(
            "LOAN AGREEMENT",
            styles["Heading2"],
        )
    )

    elements.append(Spacer(1, 15))

    monthly = monthly_installment(
        loan.principal,
        loan.annual_rate,
        loan.term_months,
    )

    data = [
        ["Agreement Number", agreement.agreement_number],
        ["Agreement Date", str(agreement.agreement_date)],
        ["Loan Number", str(loan.pk)],
        ["Borrower", str(loan.client)],
        ["Loan Product", str(loan.product.name)],
        ["Principal", f"PHP {loan.principal:,.2f}"],
        ["Annual Interest Rate", f"{loan.annual_rate}%"],
        ["Loan Term", f"{loan.term_months} months"],
        ["Estimated Monthly Payment", f"PHP {monthly:,.2f}"],
        ["Loan Status", loan.get_status_display()],
    ]

    table = Table(
        data,
        colWidths=[180, 310],
        hAlign="LEFT",
    )

    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ])
    )

    elements.append(table)
    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            "TERMS AND CONDITIONS",
            styles["Heading3"],
        )
    )

    elements.append(
        Preformatted(
            agreement.terms_and_conditions or
            "No additional terms provided.",
            styles["Code"],
            maxLineLength=85,
            splitChars=" ",
        )
    )

    elements.append(Spacer(1, 20))

    if agreement.signed_at:
        acceptance_text = (
            "Accepted electronically on "
            f"{agreement.signed_at.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
    else:
        acceptance_text = (
            "Not yet accepted by the borrower."
        )

    elements.append(
        Paragraph(
            f"Agreement Acceptance: {acceptance_text}",
            styles["Normal"],
        )
    )

    document.build(elements)

    pdf = buffer.getvalue()
    buffer.close()

    return pdf
