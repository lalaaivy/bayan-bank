
from datetime import date
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from openpyxl import Workbook
from openpyxl.styles import (
    Alignment,
    Font,
    PatternFill,
)
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from savings.models import SavingsAccount
from .models import LedgerEntry, ReportExport


def _statement_data(request, account_id):
    account = get_object_or_404(
        SavingsAccount.objects.select_related("client__user"),
        pk=account_id,
    )

    role = getattr(
        getattr(request.user, "role", None),
        "name",
        None,
    )

    if role == "client":
        if account.client.user_id != request.user.pk:
            raise PermissionDenied
    elif role not in ("admin", "staff", "loan_officer"):
        raise PermissionDenied

    today = timezone.localdate()

    raw_from = request.GET.get("date_from")
    raw_to = request.GET.get("date_to")

    date_from = (
        parse_date(raw_from)
        if raw_from is not None
        else today.replace(month=1, day=1)
    )
    date_to = (
        parse_date(raw_to)
        if raw_to is not None
        else today
    )

    if not date_from or not date_to:
        return None, HttpResponse(
            "Invalid date. Use YYYY-MM-DD.",
            status=400,
        )

    if date_from > date_to:
        return None, HttpResponse(
            "Start date must not exceed end date.",
            status=400,
        )

    entries = list(
        LedgerEntry.objects.filter(
            savings_account=account,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        ).order_by("created_at", "id")
    )

    holder = (
        account.client.user.get_full_name()
        or account.client.user.username
    )

    return {
        "account": account,
        "holder": holder,
        "date_from": date_from,
        "date_to": date_to,
        "entries": entries,
    }, None


def _record_export(request, data, filename, file_format):
    ReportExport.objects.create(
        report_type=ReportExport.ReportType.TRANSACTION,
        file_format=file_format,
        savings_account=data["account"],
        date_from=data["date_from"],
        date_to=data["date_to"],
        generated_by=request.user,
        filename=filename,
    )


def _filename(data, extension):
    account_id = data["account"].pk
    return (
        f"BayanBank_Account_{account_id}_"
        f"{data['date_from']}_{data['date_to']}."
        f"{extension}"
    )


@login_required
def export_transactions_pdf(request, account_id):
    data, error = _statement_data(request, account_id)
    if error is not None:
        return error

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

    story = [
        Paragraph("BAYAN BANK", styles["Title"]),
        Paragraph(
            "Transaction Statement",
            styles["Heading2"],
        ),
        Spacer(1, 12),
        Paragraph(
            f"Account: {data['account'].account_number}",
            styles["Normal"],
        ),
        Paragraph(
            f"Account Holder: {data['holder']}",
            styles["Normal"],
        ),
        Paragraph(
            f"Period: {data['date_from']} to "
            f"{data['date_to']}",
            styles["Normal"],
        ),
        Spacer(1, 14),
    ]

    rows = [[
        "Date",
        "Type",
        "Reference",
        "Amount (PHP)",
        "Balance (PHP)",
    ]]

    for entry in data["entries"]:
        rows.append([
            timezone.localtime(
                entry.created_at
            ).strftime("%Y-%m-%d"),
            entry.get_entry_type_display(),
            entry.reference or "-",
            f"{entry.amount:,.2f}",
            (
                f"{entry.balance_after:,.2f}"
                if entry.balance_after is not None
                else "-"
            ),
        ])

    if not data["entries"]:
        rows.append([
            "No transactions",
            "",
            "",
            "",
            "",
        ])

    table = Table(
        rows,
        colWidths=[
            27 * mm,
            38 * mm,
            40 * mm,
            38 * mm,
            37 * mm,
        ],
        repeatRows=1,
    )

    table.setStyle(TableStyle([
        (
            "BACKGROUND",
            (0, 0), (-1, 0),
            colors.HexColor("#163A63"),
        ),
        (
            "TEXTCOLOR",
            (0, 0), (-1, 0),
            colors.white,
        ),
        (
            "FONTNAME",
            (0, 0), (-1, 0),
            "Helvetica-Bold",
        ),
        (
            "FONTSIZE",
            (0, 0), (-1, -1),
            7,
        ),
        (
            "VALIGN",
            (0, 0), (-1, -1),
            "MIDDLE",
        ),
        (
            "ALIGN",
            (3, 1), (4, -1),
            "RIGHT",
        ),
        (
            "GRID",
            (0, 0), (-1, -1),
            0.25,
            colors.grey,
        ),
        (
            "BOTTOMPADDING",
            (0, 0), (-1, 0),
            9,
        ),
        (
            "TOPPADDING",
            (0, 0), (-1, 0),
            9,
        ),
    ]))

    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Generated from Bayan Bank transaction records.",
        styles["Normal"],
    ))

    document.build(story)
    filename = _filename(data, "pdf")

    with transaction.atomic():
        _record_export(
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
def export_transactions_excel(request, account_id):
    data, error = _statement_data(request, account_id)
    if error is not None:
        return error

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Transactions"

    sheet["A1"] = "BAYAN BANK"
    sheet["A2"] = "Transaction Statement"
    sheet["A4"] = "Account Number"
    sheet["B4"] = data["account"].account_number
    sheet["A5"] = "Account Holder"
    sheet["B5"] = data["holder"]
    sheet["A6"] = "Date From"
    sheet["B6"] = data["date_from"]
    sheet["A7"] = "Date To"
    sheet["B7"] = data["date_to"]

    sheet["B6"].number_format = "yyyy-mm-dd"
    sheet["B7"].number_format = "yyyy-mm-dd"

    sheet.merge_cells("A1:E1")
    sheet.merge_cells("A2:E2")

    sheet["A1"].font = Font(
        size=18,
        bold=True,
        color="163A63",
    )
    sheet["A2"].font = Font(
        size=13,
        bold=True,
    )

    headers = [
        "Date",
        "Transaction Type",
        "Reference",
        "Amount (PHP)",
        "Balance After (PHP)",
    ]

    header_row = 9

    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(
            row=header_row,
            column=column,
            value=header,
        )
        cell.fill = PatternFill(
            "solid",
            fgColor="163A63",
        )
        cell.font = Font(
            bold=True,
            color="FFFFFF",
        )
        cell.alignment = Alignment(
            horizontal="center",
        )

    for entry in data["entries"]:
        sheet.append([
            timezone.localtime(
                entry.created_at
            ).replace(tzinfo=None),
            entry.get_entry_type_display(),
            entry.reference,
            entry.amount,
            entry.balance_after,
        ])

    last_row = sheet.max_row

    for row in range(10, last_row + 1):
        sheet.cell(row, 1).number_format = (
            "yyyy-mm-dd hh:mm"
        )
        for column in (4, 5):
            sheet.cell(
                row, column
            ).number_format = '#,##0.00'

    sheet.auto_filter.ref = (
        f"A9:E{max(last_row, 9)}"
    )
    sheet.freeze_panes = "A10"

    widths = {
        "A": 23,
        "B": 24,
        "C": 28,
        "D": 20,
        "E": 23,
    }

    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    buffer = BytesIO()
    workbook.save(buffer)

    filename = _filename(data, "xlsx")

    with transaction.atomic():
        _record_export(
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
