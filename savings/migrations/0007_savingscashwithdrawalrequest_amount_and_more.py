import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def initialize_savings_balances(apps, schema_editor):
    SavingsDeposit = apps.get_model("savings", "SavingsDeposit")
    CashWithdrawalRequest = apps.get_model(
        "savings",
        "SavingsCashWithdrawalRequest",
    )

    database = schema_editor.connection.alias

    # Initialize the remaining principal of every existing deposit.
    for deposit in SavingsDeposit.objects.using(database).all().iterator():
        if deposit.status == "released":
            remaining = 0
        else:
            remaining = deposit.amount

        SavingsDeposit.objects.using(database).filter(
            pk=deposit.pk
        ).update(
            remaining_principal=remaining
        )

    # Existing requests were created under the previous full-withdrawal
    # workflow, so their requested amount was the entire deposit principal.
    for withdrawal in CashWithdrawalRequest.objects.using(database).select_related(
        "deposit"
    ).all().iterator():

        updates = {
            "amount": withdrawal.deposit.amount,
        }

        # Under the previous workflow, approval already processed the payout.
        # Preserve that historical meaning instead of treating it as unpaid.
        if withdrawal.status == "approved":
            updates["status"] = "completed"
            updates["paid_at"] = (
                withdrawal.deposit.released_at
                or withdrawal.reviewed_at
            )
            updates["paid_by_id"] = (
                withdrawal.deposit.released_by_id
                or withdrawal.reviewed_by_id
            )
            updates["payout_ledger_entry_id"] = (
                withdrawal.deposit.release_ledger_entry_id
            )

        CashWithdrawalRequest.objects.using(database).filter(
            pk=withdrawal.pk
        ).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0008_merge_20261123_0728"),
        ("savings", "0006_savingsdeposit_source_savingscashwithdrawalrequest"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="savingscashwithdrawalrequest",
            name="amount",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="savingscashwithdrawalrequest",
            name="paid_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="savingscashwithdrawalrequest",
            name="paid_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="completed_savings_cash_withdrawals",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="savingscashwithdrawalrequest",
            name="payout_ledger_entry",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="savings_cash_withdrawal",
                to="accounting.ledgerentry",
            ),
        ),
        migrations.AddField(
            model_name="savingsdeposit",
            name="remaining_principal",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="savingscashwithdrawalrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending Review"),
                    ("approved", "Approved - Awaiting Payout"),
                    ("rejected", "Rejected"),
                    ("completed", "Successfully Paid"),
                ],
                default="pending",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="savingsdeposit",
            name="status",
            field=models.CharField(
                choices=[
                    ("locked", "Locked"),
                    ("matured", "Matured"),
                    ("released", "Fully Released"),
                ],
                default="locked",
                max_length=10,
            ),
        ),
        migrations.RunPython(
            initialize_savings_balances,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="savingscashwithdrawalrequest",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount__gte", 0)),
                name="savings_cash_withdrawal_amount_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="savingsdeposit",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("remaining_principal__isnull", True))
                    | models.Q(
                        ("remaining_principal__gte", 0),
                        ("remaining_principal__lte", models.F("amount")),
                    )
                ),
                name="savings_remaining_principal_valid",
            ),
        ),
    ]