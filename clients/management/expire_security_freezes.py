from django.core.management.base import BaseCommand

from clients.services import expire_temporary_security_freezes


class Command(BaseCommand):
    help = "Automatically release expired minor client security freezes."

    def handle(self, *args, **options):
        expire_temporary_security_freezes()

        self.stdout.write(
            self.style.SUCCESS(
                "Expired minor security freezes have been processed."
            )
        )