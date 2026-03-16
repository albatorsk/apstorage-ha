"""Helpers for APstorage entity naming."""
from __future__ import annotations

import re
from typing import Any

from homeassistant.helpers import entity_registry as er


def slugify_fragment(value: str) -> str:
    """Convert a string to a Home Assistant-friendly slug fragment."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return slug.strip("_")


def get_serial_number(data: dict[int, dict[str, Any]] | None) -> str | None:
    """Return the device serial number from coordinator data if available."""
    if not data or 40052 not in data:
        return None

    serial_number = data[40052].get("value")
    if not isinstance(serial_number, str):
        return None

    serial_number = serial_number.strip()
    return serial_number or None


def get_suggested_object_id(
    data: dict[int, dict[str, Any]] | None, entity_name: str
) -> str | None:
    """Build the preferred object ID for an entity using the device serial."""
    name_slug = slugify_fragment(entity_name)
    if not name_slug:
        return None

    serial_number = get_serial_number(data)
    if not serial_number:
        return name_slug

    serial_slug = slugify_fragment(serial_number)
    if not serial_slug:
        return name_slug

    return f"aps_{serial_slug}_{name_slug}"


def build_prefixed_entity_id(
    current_entity_id: str | None,
    data: dict[int, dict[str, Any]] | None,
    entity_name: str,
) -> str | None:
    """Build the full entity ID with the serial-based prefix."""
    suggested_object_id = get_suggested_object_id(data, entity_name)
    if not current_entity_id or not suggested_object_id or "." not in current_entity_id:
        return None

    domain = current_entity_id.split(".", maxsplit=1)[0]
    return f"{domain}.{suggested_object_id}"


def async_migrate_entity_id(
    hass,
    current_entity_id: str | None,
    data: dict[int, dict[str, Any]] | None,
    entity_name: str,
) -> bool:
    """Rename an entity registry entry to the serial-prefixed entity ID."""
    new_entity_id = build_prefixed_entity_id(current_entity_id, data, entity_name)
    if not current_entity_id or not new_entity_id or current_entity_id == new_entity_id:
        return False

    registry = er.async_get(hass)
    registry_entry = registry.async_get(current_entity_id)
    if not registry_entry:
        return False

    registry.async_update_entity(current_entity_id, new_entity_id=new_entity_id)
    return True