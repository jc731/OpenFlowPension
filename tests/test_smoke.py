"""Smoke tests — catch failures the service-level suite can't see.

The rest of the suite tests services directly and never imports app.main,
so a router with a bad import passes every test while the API fails to
boot. Likewise, document tests inject a stub renderer, so WeasyPrint's
system libraries (pango/gobject) can be missing without any test failing.
"""

from fastapi.testclient import TestClient


def test_app_boots_and_serves_health():
    # Importing app.main exercises every router module's imports.
    from app.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_builds():
    from app.main import app

    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "OpenFlow Pension API"


def test_weasyprint_renders_pdf():
    # Real WeasyPrint, no stub — fails if pango/gobject libs are absent.
    from app.services.document_renderer import html_to_pdf

    pdf = html_to_pdf("<html><body><p>smoke test</p></body></html>")
    assert pdf.startswith(b"%PDF")
