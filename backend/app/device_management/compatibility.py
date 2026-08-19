"""A simple, generic demo compatibility model (Phase 31 brief §31.5) — never invented
manufacturer specifications. Firmware versions are synthetic (`docs/DEVICE_CONFIGURATION
.md`); the policy below is a deliberately simple major-version convention applied
uniformly across device types, not real vendor compatibility data.
"""

from __future__ import annotations

from app.domain.enums import CompatibilityStatus


def classify_compatibility(firmware_version: str | None) -> CompatibilityStatus:
    if not firmware_version:
        return CompatibilityStatus.UNKNOWN
    major = firmware_version.strip().split(".", 1)[0]
    if not major.isdigit():
        return CompatibilityStatus.UNKNOWN
    major_num = int(major)
    if major_num >= 2:
        return CompatibilityStatus.SUPPORTED
    if major_num == 1:
        return CompatibilityStatus.SUPPORTED_WITH_LIMITATIONS
    return CompatibilityStatus.INCOMPATIBLE
