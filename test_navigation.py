
from html.parser import HTMLParser
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse, resolve, Resolver404
from django.db import transaction


USERS = {
    "admin": ("admin", "admin_home"),
    "staff": ("teststaff", "staff_home"),
    "loan_officer": ("testofficer", "officer_home"),
    "client": ("testclient", "portal_home"),
}


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return

        attributes = dict(attrs)
        href = attributes.get("href")

        if href:
            self.links.append(href)


User = get_user_model()

passed = 0
failed = 0
warnings = 0

with override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"]
):
    for role, (username, dashboard) in USERS.items():
        print(f"\n{'=' * 60}")
        print(f"{role.upper()} NAVIGATION")
        print(f"{'=' * 60}")

        user = User.objects.get(username=username)

        client = Client(raise_request_exception=False)
        client.force_login(user)

        with transaction.atomic():
            response = client.get(reverse(dashboard))
            transaction.set_rollback(True)

        if response.status_code != 200:
            print(
                f"[FAIL] Dashboard returned "
                f"HTTP {response.status_code}"
            )
            failed += 1
            continue

        parser = LinkParser()
        parser.feed(
            response.content.decode(
                "utf-8", errors="replace"
            )
        )

        links = sorted(set(parser.links))

        print(f"Found {len(links)} unique links.\n")

        for href in links:
            parsed = urlparse(href)

            if parsed.scheme or parsed.netloc:
                continue

            if href.startswith("#"):
                continue

            path = parsed.path

            if not path or not path.startswith("/"):
                continue

            try:
                match = resolve(path)

                print(
                    f"[OK] {path} "
                    f"-> {match.url_name}"
                )
                passed += 1

            except Resolver404:
                print(f"[BROKEN] {path}")
                failed += 1

        client.logout()

print(f"\n{'=' * 60}")
print("FINAL NAVIGATION RESULTS")
print(f"{'=' * 60}")
print(f"Valid links: {passed}")
print(f"Broken links: {failed}")
print(f"Warnings: {warnings}")

print(
    "\nNote: This checks link resolution only, "
    "not whether each role is authorized "
    "to open every linked page."
)
