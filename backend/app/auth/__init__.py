"""Authentication and authorization.

Phase 24 implements the OIDC/OAuth2-compatible architecture boundary this package
reserved since Phase 1 (`docs/ARCHITECTURE.md` §9.2): a signed-bearer-token demo identity
provider (`app.auth.demo_tokens`), a fixed six-role/permission model
(`app.auth.permissions`), and a centralized authorization check (`app.auth.service`). See
`docs/SECURITY.md` for the full model and its explicit demo-auth boundary.
"""
