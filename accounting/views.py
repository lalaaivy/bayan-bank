
from io import BytesIO
from html import escape

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from savings.models import SavingsAccount
from .models import BankAccount, LedgerEntry, ReportExport


def _statement_data(request, account_id, account_type="savings"):
    """
    Retrieve statement data for either a savings account
    or a regular bank account.
    """

    if account_type == "bank":
        account = get_object_or_404(
            BankAccount.objects.select_related("client__user"),
            pk=account_id,
        )

        entries = LedgerEntry.objects.filter(
            bank_account=account,
        )

    elif account_type == "savings":
        account = get_object_or_404(
            SavingsAccount.objects.select_related("client__user"),
            pk=account_id,
        )

        entries = LedgerEntry.objects.filter(
            savings_account=account,
        )

    else:
        raise ValueError("Invalid account type.")

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
        entries.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        ).order_by("created_at", "id")
    )

    holder = (
        account.client.user.get_full_name()
        or account.client.user.username
    )

    account_label = (
        "Regular Bank Account"
        if account_type == "bank"
        else "Savings Account"
    )

    return {
        "account": account,
        "holder": holder,
        "date_from": date_from,
        "date_to": date_to,
        "entries": entries,
        "account_type": account_type,
        "account_label": account_label,
    }, None


def _record_export(request, data, filename, file_format):
    export_data = {
        "report_type": ReportExport.ReportType.TRANSACTION,
        "file_format": file_format,
        "date_from": data["date_from"],
        "date_to": data["date_to"],
        "generated_by": request.user,
        "filename": filename,
    }

    if data["account_type"] == "bank":
        export_data["bank_account"] = data["account"]
    else:
        export_data["savings_account"] = data["account"]

    ReportExport.objects.create(**export_data)


def _filename(data, extension):
    account_id = data["account"].pk
    account_type = data["account_type"].capitalize()

    return (
        f"BayanBank_{account_type}_Account_{account_id}_"
        f"{data['date_from']}_{data['date_to']}."
        f"{extension}"
    )


def _safe_paragraph(value, style):
    """
    Escape dynamic text before placing it inside a ReportLab Paragraph.
    This prevents user-provided text from being interpreted as markup.
    """
    return Paragraph(
        escape(str(value if value is not None else "-")),
        style,
    )


def _export_transactions_pdf(request, account_id, account_type):
    data, error = _statement_data(
        request,
        account_id,
        account_type,
    )

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

    cell_style = ParagraphStyle(
        "StatementCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.5,
        leading=8,
    )

    header_style = ParagraphStyle(
        "StatementHeader",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    story = [
        Paragraph("BAYAN BANK", styles["Title"]),
        Paragraph(
            "Transaction Statement",
            styles["Heading2"],
        ),
        Spacer(1, 12),
        Paragraph(
            f"Account Type: {escape(data['account_label'])}",
            styles["Normal"],
        ),
        Paragraph(
            f"Account Number: "
            f"{escape(str(data['account'].account_number))}",
            styles["Normal"],
        ),
        Paragraph(
            f"Account Holder: {escape(data['holder'])}",
            styles["Normal"],
        ),
        Paragraph(
            f"Period: {data['date_from']} to {data['date_to']}",
            styles["Normal"],
        ),
        Spacer(1, 14),
    ]

    rows = [[
        Paragraph("Date", header_style),
        Paragraph("Type", header_style),
        Paragraph("Reference", header_style),
        Paragraph("Amount (PHP)", header_style),
        Paragraph("Balance (PHP)", header_style),
    ]]

    for entry in data["entries"]:
        rows.append([
            Paragraph(
                timezone.localtime(
                    entry.created_at
                ).strftime("%Y-%m-%d"),
                cell_style,
            ),
            _safe_paragraph(
                entry.get_entry_type_display(),
                cell_style,
            ),
            _safe_paragraph(
                entry.reference or "-",
                cell_style,
            ),
            Paragraph(
                f"{entry.amount:,.2f}",
                cell_style,
            ),
            Paragraph(
                (
                    f"{entry.balance_after:,.2f}"
                    if entry.balance_after is not None
                    else "-"
                ),
                cell_style,
            ),
        ])

    if not data["entries"]:
        rows.append([
            Paragraph("No transactions", cell_style),
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


def _export_transactions_excel(request, account_id, account_type):
    data, error = _statement_data(
        request,
        account_id,
        account_type,
    )

    if error is not None:
        return error

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Transactions"

    sheet["A1"] = "BAYAN BANK"
    sheet["A2"] = "Transaction Statement"

    sheet["A4"] = "Account Type"
    sheet["B4"] = data["account_label"]

    sheet["A5"] = "Account Number"
    sheet["B5"] = data["account"].account_number

    sheet["A6"] = "Account Holder"
    sheet["B6"] = data["holder"]

    sheet["A7"] = "Date From"
    sheet["B7"] = data["date_from"]

    sheet["A8"] = "Date To"
    sheet["B8"] = data["date_to"]

    sheet["B7"].number_format = "yyyy-mm-dd"
    sheet["B8"].number_format = "yyyy-mm-dd"

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

    header_row = 10

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
            vertical="center",
        )

    # Write transaction records starting directly below the headers.
    first_data_row = 11

    if data["entries"]:
        for index, entry in enumerate(data["entries"]):
            row_number = first_data_row + index

            sheet.cell(
                row=row_number,
                column=1,
                value=timezone.localtime(
                    entry.created_at
                ).replace(tzinfo=None),
            )

            sheet.cell(
                row=row_number,
                column=2,
                value=entry.get_entry_type_display(),
            )

            sheet.cell(
                row=row_number,
                column=3,
                value=entry.reference or "-",
            )

            sheet.cell(
                row=row_number,
                column=4,
                value=entry.amount,
            )

            sheet.cell(
                row=row_number,
                column=5,
                value=entry.balance_after,
            )

            sheet.cell(
                row=row_number,
                column=1,
            ).number_format = "yyyy-mm-dd hh:mm"

            for column in (4, 5):
                sheet.cell(
                    row=row_number,
                    column=column,
                ).number_format = '#,##0.00'

    else:
        sheet["A11"] = "No transactions found for this period."

    last_row = sheet.max_row

    sheet.auto_filter.ref = (
        f"A10:E{max(last_row, header_row)}"
    )

    sheet.freeze_panes = "A11"

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


# --------------------------------------------------
# SAVINGS ACCOUNT EXPORTS
# --------------------------------------------------

@login_required
def export_transactions_pdf(request, account_id):
    return _export_transactions_pdf(
        request,
        account_id,
        "savings",
    )


@login_required
def export_transactions_excel(request, account_id):
    return _export_transactions_excel(
        request,
        account_id,
        "savings",
    )


# --------------------------------------------------
# REGULAR BANK ACCOUNT EXPORTS
# --------------------------------------------------

@login_required
def export_bank_transactions_pdf(request, account_id):
    return _export_transactions_pdf(
        request,
        account_id,
        "bank",
    )


@login_required
def export_bank_transactions_excel(request, account_id):
    return _export_transactions_excel(
        request,
        account_id,
        "bank",
    )
