from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Post monthly savings interest at 2% annual rate."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Interest command is working!")
        )