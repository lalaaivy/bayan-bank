
from decimal import Decimal
from html import escape
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum
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

from accounting.models import ReportExport
from .models import Loan, LoanPayment


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
        LoanPayment.objects.filter(
            loan=loan,
            payment_date__date__gte=date_from,
            payment_date__date__lte=date_to,
        )
        .select_related("ledger_entry", "recorded_by")
        .order_by("payment_date", "pk")
    )

    total_due = sum(
        (item.total_due for item in installments),
        Decimal("0.00"),
    )

    total_applied = sum(
        (item.amount_paid for item in installments),
        Decimal("0.00"),
    )

    total_paid = (
        LoanPayment.objects.filter(loan=loan)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    remaining = max(
        total_due - total_applied,
        Decimal("0.00"),
    )

    holder = (
        loan.client.user.get_full_name()
        or loan.client.user.username
    )

    return {
        "loan": loan,
        "installments": installments,
        "payments": payments,
        "date_from": date_from,
        "date_to": date_to,
        "total_due": total_due,
        "total_paid": total_paid,
        "total_applied": total_applied,
        "remaining": remaining,
        "holder": holder,
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


def _payment_reference(payment):
    reference = payment.ledger_entry.reference

    if reference:
        return reference

    return f"Payment #{payment.pk}"


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

    schedule_rows = [[
        "#",
        "Due Date",
        "Principal",
        "Interest",
        "Penalty",
        "Total Due",
        "Paid",
        "Status",
    ]]

    for item in data["installments"]:
        schedule_rows.append([
            str(item.number),
            str(item.due_date),
            f"{item.principal_due:,.2f}",
            f"{item.interest_due:,.2f}",
            f"{item.penalty_amount:,.2f}",
            f"{item.total_due:,.2f}",
            f"{item.amount_paid:,.2f}",
            item.get_status_display(),
        ])

    if not data["installments"]:
        schedule_rows.append([
            "-", "Not scheduled", "-", "-",
            "-", "-", "-", "-",
        ])

    schedule_table = Table(
        schedule_rows,
        colWidths=[
            8 * mm,
            23 * mm,
            23 * mm,
            20 * mm,
            20 * mm,
            25 * mm,
            25 * mm,
            21 * mm,
        ],
        repeatRows=1,
    )

    schedule_table.setStyle(TableStyle([
        (
            "BACKGROUND",
            (0, 0),
            (-1, 0),
            colors.HexColor("#163A63"),
        ),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (2, 1), (6, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))

    story.append(schedule_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph(
        "Payment History",
        styles["Heading3"],
    ))

    payment_rows = [[
        "Payment Date",
        "Reference",
        "Amount (PHP)",
    ]]

    for payment in data["payments"]:
        payment_rows.append([
            timezone.localtime(
                payment.payment_date
            ).strftime("%Y-%m-%d %H:%M"),
            p(_payment_reference(payment)),
            f"{payment.amount:,.2f}",
        ])

    if not data["payments"]:
        payment_rows.append([
            "No payments in selected period",
            "",
            "",
        ])

    payment_table = Table(
        payment_rows,
        colWidths=[
            45 * mm,
            80 * mm,
            55 * mm,
        ],
        repeatRows=1,
    )

    payment_table.setStyle(TableStyle([
        (
            "BACKGROUND",
            (0, 0),
            (-1, 0),
            colors.HexColor("#163A63"),
        ),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    story.append(payment_table)
    story.append(Spacer(1, 12))

    story.extend([
        p(
            f"Scheduled Total: "
            f"PHP {data['total_due']:,.2f}"
        ),
        p(
            f"Total Payments Recorded: "
            f"PHP {data['total_paid']:,.2f}"
        ),
        p(
            f"Total Applied to Installments: "
            f"PHP {data['total_applied']:,.2f}"
        ),
        p(
            f"Remaining Scheduled Balance: "
            f"PHP {data['remaining']:,.2f}"
        ),
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

    # ------------------------------------------
    # LOAN SUMMARY
    # ------------------------------------------

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
    summary.append(["Total Payments Recorded", data["total_paid"]])
    summary.append(["Total Applied to Installments", data["total_applied"]])
    summary.append(["Remaining Scheduled Balance", data["remaining"]])

    for row in (6, 14, 15, 16, 17):
        summary.cell(row, 2).number_format = '#,##0.00'

    for row in (10, 11, 12):
        summary.cell(row, 2).number_format = "yyyy-mm-dd"

    # ------------------------------------------
    # AMORTIZATION SCHEDULE
    # ------------------------------------------

    installments_sheet = workbook.create_sheet("Amortization")

    installments_sheet.append([
        "Installment #",
        "Due Date",
        "Principal",
        "Interest",
        "Penalty",
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
            item.penalty_amount,
            item.total_due,
            item.amount_paid,
            max(
                item.total_due - item.amount_paid,
                Decimal("0.00"),
            ),
            item.get_status_display(),
        ])

    # ------------------------------------------
    # PAYMENT HISTORY
    # ------------------------------------------

    payments_sheet = workbook.create_sheet("Payment History")

    payments_sheet.append([
        "Payment Date",
        "Reference",
        "Recorded By",
        "Amount",
    ])

    for payment in data["payments"]:
        payments_sheet.append([
            timezone.localtime(
                payment.payment_date
            ).replace(tzinfo=None),
            _payment_reference(payment),
            str(payment.recorded_by),
            payment.amount,
        ])

    if not data["payments"]:
        payments_sheet.append([
            "No payments in selected period",
            "",
            "",
            "",
        ])

    # ------------------------------------------
    # FORMATTING
    # ------------------------------------------

    for sheet in workbook.worksheets:
        sheet.freeze_panes = (
            "A2" if sheet != summary else "A3"
        )

        for cell in sheet[1]:
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

    for row in installments_sheet.iter_rows(min_row=2):
        row[1].number_format = "yyyy-mm-dd"

        for cell in row[2:8]:
            cell.number_format = '#,##0.00'

    for row in payments_sheet.iter_rows(min_row=2):
        row[0].number_format = "yyyy-mm-dd hh:mm"
        row[3].number_format = '#,##0.00'

    # ------------------------------------------
    # SAVE AND DOWNLOAD
    # ------------------------------------------

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
