"""Generic document assembler.

Reads the context spec from DocumentTemplate.config_value["context"],
calls each named provider, and merges results into a single context dict.

Escape hatch (Option A): register an explicit assembler for a slug in
EXPLICIT_ASSEMBLERS. When present, it replaces the declarative path entirely.
The explicit assembler receives (member_id, params, session) and returns a dict.
"""

import uuid
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentTemplate
from app.services.document_context_providers import CONTEXT_PROVIDERS

# Explicit per-slug assemblers (Option A override). Register here when the
# declarative context spec isn't expressive enough for a specific document.
EXPLICIT_ASSEMBLERS: dict[str, Callable] = {}


async def assemble(
    template: DocumentTemplate,
    member_id: uuid.UUID | None,
    params: dict,
    session: AsyncSession,
) -> dict:
    """Build the full Jinja2 context for a document."""

    # Option A: explicit assembler wins if registered
    explicit = EXPLICIT_ASSEMBLERS.get(template.slug)
    if explicit:
        return await explicit(member_id, params, session)

    # Option B: declarative — call each named provider and merge
    context_keys: list[str] = template.config_value.get("context", [])

    # fund_info is always included so every template has consistent letterhead
    if "fund_info" not in context_keys:
        context_keys = ["fund_info"] + context_keys

    context: dict = {"params": params}
    for key in context_keys:
        provider = CONTEXT_PROVIDERS.get(key)
        if provider is None:
            raise ValueError(
                f"Unknown context provider '{key}' in template '{template.slug}'. "
                f"Available providers: {sorted(CONTEXT_PROVIDERS)}"
            )
        context.update(await provider(member_id, params, session))

    return context
