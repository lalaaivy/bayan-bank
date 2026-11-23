from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render


def service_worker(request):
    """
    Serve the service worker from the website root.

    Root scope allows it to control both client and staff pages.
    """
    worker_path = (
        Path(settings.BASE_DIR)
        / "static"
        / "js"
        / "service-worker.js"
    )

    try:
        worker_code = worker_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return HttpResponse(
            "Service worker file not found.",
            status=404,
            content_type="text/plain",
        )

    response = HttpResponse(
        worker_code,
        content_type="application/javascript",
    )

    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"

    return response


def offline_page(request):
    """
    Display a generic offline page.

    This page must never contain private banking information.
    """
    return render(request, "pwa/offline.html")