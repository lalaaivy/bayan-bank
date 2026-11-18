
from datetime import timedelta
from decimal import Decimal
from html import escape
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from accounting.models import LedgerEntry, ReportExport
from .models import Loan


def _get_loan(request, loan_id):
    loan = get_object_or_404(
        Loan.objects.select_related("client__user", "product"),
        pk=loan_id,
    )

    role = getattr(
        getattr(request.user, "role", None),
        "name",
        None,
    )

    if role == "client":
        if loan.client.user_id != request.user.pk:
            raise PermissionDenied
    elif role not in ("admin", "staff", "loan_officer"):
        raise PermissionDenied

    return loan


def _report_data(request, loan_id):
    loan = _get_loan(request, loan_id)

    today = timezone.localdate()
    raw_from = request.GET.get("date_from")
    raw_to = request.GET.get("date_to")

    date_from = (
        parse_date(raw_from)
        if raw_from is not None
        else loan.applied_at.date()
    )
    date_to = (
        parse_date(raw_to)
        if raw_to is not None
        else today
    )

    if not date_from or not date_to or date_from > date_to:
        return None, HttpResponse(
            "Invalid report date range. Use YYYY-MM-DD.",
            status=400,
        )

    installments = list(
        loan.installments.order_by("number")
    )

    payments = list(
        LedgerEntry.objects.filter(
            loan=loan,
            entry_type=LedgerEntry.EntryType.LOAN_PAYMENT,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        ).order_by("created_at", "id")
    )

    total_due = sum(
        (item.total_due for item in installments),
        Decimal("0.00"),
    )
    total_paid = sum(
        (item.amount_paid for item in installments),
        Decimal("0.00"),
    )
    remaining = max(
        total_due - total_paid,
        Decimal("0.00"),
    )

    return {
        "loan": loan,
        "installments": installments,
        "payments": payments,
        "date_from": date_from,
        "date_to": date_to,
        "total_due": total_due,
        "total_paid": total_paid,
        "remaining": remaining,
        "holder": (
            loan.client.user.get_full_name()
            or loan.client.user.username
        ),
    }, None


def _save_history(request, data, filename, file_format):
    ReportExport.objects.create(
        report_type=ReportExport.ReportType.LOAN,
        file_format=file_format,
        loan=data["loan"],
        date_from=data["date_from"],
        date_to=data["date_to"],
        generated_by=request.user,
        filename=filename,
    )


def _filename(data, extension):
    return (
        f"BayanBank_Loan_{data['loan'].pk}_"
        f"{data['date_from']}_{data['date_to']}.{extension}"
    )


@login_required
def export_loan_pdf(request, loan_id):
    data, error = _report_data(request, loan_id)
    if error is not None:
        return error

    loan = data["loan"]
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    def p(value):
        return Paragraph(
            escape(str(value)),
            styles["Normal"],
        )

    story = [
        Paragraph("BAYAN BANK", styles["Title"]),
        Paragraph("Loan Statement", styles["Heading2"]),
        Spacer(1, 12),
        p(f"Loan Number: {loan.pk}"),
        p(f"Borrower: {data['holder']}"),
        p(f"Product: {loan.product.name}"),
        p(f"Principal: PHP {loan.principal:,.2f}"),
        p(f"Annual Interest Rate: {loan.annual_rate}%"),
        p(f"Term: {loan.term_months} months"),
        p(f"Status: {loan.get_status_display()}"),
        p(
            f"Payment history period: "
            f"{data['date_from']} to {data['date_to']}"
        ),
        Spacer(1, 12),
        Paragraph(
            "Amortization Schedule",
            styles["Heading3"],
        ),
    ]

    rows = [[
        "#", "Due Date", "Principal",
        "Interest", "Paid", "Status",
    ]]

    for item in data["installments"]:
        rows.append([
            str(item.number),
            str(item.due_date),
            f"{item.principal_due:,.2f}",
            f"{item.interest_due:,.2f}",
            f"{item.amount_paid:,.2f}",
            item.get_status_display(),
        ])

    if not data["installments"]:
        rows.append([
            "-", "Not scheduled", "-", "-", "-", "-"
        ])

    table = Table(
        rows,
        colWidths=[
            10 * mm, 34 * mm, 34 * mm,
            34 * mm, 34 * mm, 34 * mm,
        ],
        repeatRows=1,
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#163A63")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (2, 1), (4, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    story.append(table)
    story.append(Spacer(1, 12))

    story.append(Paragraph(
        "Payment History",
        styles["Heading3"],
    ))

    payment_rows = [[
        "Date", "Reference", "Amount (PHP)",
    ]]

    for entry in data["payments"]:
        payment_rows.append([
            timezone.localtime(
                entry.created_at
            ).strftime("%Y-%m-%d %H:%M"),
            p(entry.reference or "-"),
            f"{entry.amount:,.2f}",
        ])

    if not data["payments"]:
        payment_rows.append([
            "No payments in selected period", "", ""
        ])

    payment_table = Table(
        payment_rows,
        colWidths=[45 * mm, 80 * mm, 55 * mm],
        repeatRows=1,
    )

    payment_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#163A63")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    story.append(payment_table)
    story.append(Spacer(1, 12))
    story.extend([
        p(f"Scheduled Total: PHP {data['total_due']:,.2f}"),
        p(f"Total Applied to Installments: PHP {data['total_paid']:,.2f}"),
        p(f"Remaining Scheduled Balance: PHP {data['remaining']:,.2f}"),
    ])

    document.build(story)
    filename = _filename(data, "pdf")

    with transaction.atomic():
        _save_history(
            request,
            data,
            filename,
            ReportExport.Format.PDF,
        )

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    buffer.close()
    return response


@login_required
def export_loan_excel(request, loan_id):
    data, error = _report_data(request, loan_id)
    if error is not None:
        return error

    loan = data["loan"]
    workbook = Workbook()

    summary = workbook.active
    summary.title = "Loan Summary"

    summary.append(["BAYAN BANK - LOAN STATEMENT"])
    summary.append([])
    summary.append(["Loan Number", loan.pk])
    summary.append(["Borrower", data["holder"]])
    summary.append(["Loan Product", loan.product.name])
    summary.append(["Principal", loan.principal])
    summary.append(["Annual Interest Rate (%)", loan.annual_rate])
    summary.append(["Term (Months)", loan.term_months])
    summary.append(["Status", loan.get_status_display()])
    summary.append(["Applied Date", loan.applied_at.date()])
    summary.append(["Report From", data["date_from"]])
    summary.append(["Report To", data["date_to"]])
    summary.append([])
    summary.append(["Scheduled Total", data["total_due"]])
    summary.append(["Total Applied Payments", data["total_paid"]])
    summary.append(["Remaining Scheduled Balance", data["remaining"]])

    for row in (6, 14, 15, 16):
        summary.cell(row, 2).number_format = '#,##0.00'

    for row in (10, 11, 12):
        summary.cell(row, 2).number_format = "yyyy-mm-dd"

    installments_sheet = workbook.create_sheet(
        "Amortization"
    )
    installments_sheet.append([
        "Installment #",
        "Due Date",
        "Principal",
        "Interest",
        "Total Due",
        "Amount Paid",
        "Remaining",
        "Status",
    ])

    for item in data["installments"]:
        installments_sheet.append([
            item.number,
            item.due_date,
            item.principal_due,
            item.interest_due,
            item.total_due,
            item.amount_paid,
            max(
                item.total_due - item.amount_paid,
                Decimal("0.00"),
            ),
            item.get_status_display(),
        ])

    payments_sheet = workbook.create_sheet(
        "Payment History"
    )
    payments_sheet.append([
        "Payment Date",
        "Reference",
        "Amount",
    ])

    for entry in data["payments"]:
        payments_sheet.append([
            timezone.localtime(
                entry.created_at
            ).replace(tzinfo=None),
            entry.reference,
            entry.amount,
        ])

    for sheet in workbook.worksheets:
        sheet.freeze_panes = (
            "A2" if sheet != summary else "A3"
        )

        header_row = 1

        for cell in sheet[header_row]:
            cell.font = Font(
                bold=True,
                color="FFFFFF",
            )
            cell.fill = PatternFill(
                "solid",
                fgColor="163A63",
            )

        for column in range(1, sheet.max_column + 1):
            letter = get_column_letter(column)
            sheet.column_dimensions[letter].width = (
                27 if column == 1 else 23
            )

    installments_sheet.auto_filter.ref = (
        installments_sheet.dimensions
    )
    payments_sheet.auto_filter.ref = (
        payments_sheet.dimensions
    )

    for row in installments_sheet.iter_rows(
        min_row=2
    ):
        row[1].number_format = "yyyy-mm-dd"
        for cell in row[2:7]:
            cell.number_format = '#,##0.00'

    for row in payments_sheet.iter_rows(
        min_row=2
    ):
        row[0].number_format = "yyyy-mm-dd hh:mm"
        row[2].number_format = '#,##0.00'

    buffer = BytesIO()
    workbook.save(buffer)
    filename = _filename(data, "xlsx")

    with transaction.atomic():
        _save_history(
            request,
            data,
            filename,
            ReportExport.Format.XLSX,
        )

    response = HttpResponse(
        buffer.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    buffer.close()
    return response
