from django.core.management.base import BaseCommand

from clients.services import expire_temporary_security_freezes


class Command(BaseCommand):
    help = (
        "Automatically release expired minor client security freezes."
    )

    def handle(self, *args, **options):
        expired_ids = expire_temporary_security_freezes()

        if expired_ids:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully expired {len(expired_ids)} "
                    f"temporary security freeze(s): "
                    f"{', '.join(map(str, expired_ids))}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "No expired temporary security freezes found."
                )
            )