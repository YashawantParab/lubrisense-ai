"""API request/response schemas.

Strictly separate from the ORM models in app.domain.models (TECHNICAL_DECISIONS.md,
domain-vs-ORM-separation ADR): route handlers never return an ORM object directly to
FastAPI without a response_model schema in this package translating it. Response schemas
use `model_config = ConfigDict(from_attributes=True)` so they can validate straight from
an ORM instance without a manual field-by-field mapping.
"""
