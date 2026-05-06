"""Document renderer: Jinja2 template → HTML → PDF (WeasyPrint).

render_to_html and html_to_pdf are separate so tests can exercise the
template layer without invoking WeasyPrint. The document service accepts
an injectable _renderer parameter for the same reason.
"""

import os
from pathlib import Path

import jinja2

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "documents"

_env: jinja2.Environment | None = None


def _get_env() -> jinja2.Environment:
    global _env
    if _env is None:
        _env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=jinja2.select_autoescape(["html"]),
        )
        _env.filters["currency"] = lambda v: f"${float(v):,.2f}" if v is not None else ""
        _env.filters["dateformat"] = lambda v: v.strftime("%B %d, %Y") if v else ""
    return _env


def render_to_html(template_file: str, context: dict) -> str:
    template = _get_env().get_template(template_file)
    return template.render(**context)


def html_to_pdf(html: str) -> bytes:
    import weasyprint  # lazy import — not needed in test environments

    return weasyprint.HTML(string=html, base_url=str(_TEMPLATE_DIR)).write_pdf()


def render_to_pdf(template_file: str, context: dict) -> bytes:
    return html_to_pdf(render_to_html(template_file, context))
