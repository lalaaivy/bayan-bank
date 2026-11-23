from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        (
            "accounting",
            "0006_alter_bankaccount_options_and_more",
        ),
        (
            "accounting",
            "0006_bankaccount_one_open_bank_account_per_client",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE UNIQUE INDEX IF NOT EXISTS
                "one_open_bank_account_per_client"
                ON "accounting_bankaccount" ("client_id")
                WHERE "status" IN ('active', 'frozen');
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS
                "one_open_bank_account_per_client";
            """,
        ),
    ]