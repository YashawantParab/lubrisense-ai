"""Persistence-layer repositories.

Every repository is tenant-scoped (see app.repositories.base.TenantScopedRepository) and
takes an AsyncSession injected per-request — route handlers never touch SQLAlchemy
directly, only through a repository or a service built on one.
"""
