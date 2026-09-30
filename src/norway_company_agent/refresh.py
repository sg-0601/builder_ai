from __future__ import annotations

import copy
from typing import Any, Literal

# Supported typed changes per Signalpost Learning Harness specification
TypedChangeKind = Literal[
    "new_role",
    "closed_job",
    "new_location",
    "new_filing",
    "changed_description",
    "generic_change",
]

TRACKED_FIELDS: dict[str, tuple[str, ...]] = {
    "registry.name": ("name",),
    "registry.legal_form": ("legal_form",),
    "registry.employees": ("employees",),
    "registry.municipality": ("municipality",),
    "registry.website": ("website",),
    "registry.latest_submitted_accounts": ("latest_submitted_accounts",),
    "financials.records": ("evidence", "financials", "value", "records"),
    "financial_history.years": ("evidence", "financial_history", "value", "years"),
    "roles.roles": ("evidence", "roles", "value", "roles"),
    "locations.locations": ("evidence", "locations", "value", "locations"),
    "website.title": ("evidence", "website", "value", "title"),
    "website.description": ("evidence", "website", "value", "description"),
    "website.social_links": ("evidence", "website", "value", "social_links"),
}


def classify_change_type(field: str, old_value: Any, new_value: Any) -> TypedChangeKind:
    """Classifies an observed evidence delta into typed change categories."""
    if "roles" in field:
        return "new_role"
    elif "location" in field:
        return "new_location"
    elif field in {"financials.records", "registry.latest_submitted_accounts", "financial_history.years"}:
        return "new_filing"
    elif field in {"website.description", "website.title"}:
        return "changed_description"
    elif "job" in field:
        return "closed_job"
    return "generic_change"


def _read(value: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _evidence_for(profile: dict[str, Any], field: str) -> dict[str, Any]:
    module = field.split(".", 1)[0]
    records = profile.get("evidence", {})
    if module == "registry":
        return records.get("registry_live") or records.get("registry", {})
    return records.get(module, {})


def diff_profile(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    """Emits typed changes between previous and current profiles.
    
    Adheres strictly to Signalpost Learning Harness:
    emits typed changes such as new_role, closed_job, new_location,
    new_filing or changed_description.
    """
    old_org = previous.get("organisation_number")
    new_org = current.get("organisation_number")
    if not old_org or old_org != new_org:
        raise ValueError("Refresh comparison requires the same exact organisation number")
    changes = []
    for field, path in TRACKED_FIELDS.items():
        old_value = _read(previous, path)
        new_value = _read(current, path)
        if old_value == new_value:
            continue
        record = _evidence_for(current, field)
        previous_record = _evidence_for(previous, field)
        typed_change = classify_change_type(field, old_value, new_value)
        changes.append({
            "organisation_number": new_org,
            "field": field,
            "change_type": typed_change,
            "old_value": old_value,
            "new_value": new_value,
            "source_url": record.get("source_url"),
            "retrieved_at": record.get("retrieved_at"),
            "effective_at": record.get("effective_at") or record.get("as_of"),
            "source_class": record.get("source_class") or record.get("source_type"),
            "old_content_sha256": previous_record.get("content_sha256"),
            "new_content_sha256": record.get("content_sha256"),
            "status": record.get("status"),
        })
    return changes


def diff_datasets(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    old_by_org = {row["organisation_number"]: row for row in previous}
    new_by_org = {row["organisation_number"]: row for row in current}
    if set(old_by_org) != set(new_by_org):
        raise ValueError("Refresh datasets must have identical organisation-number membership")
    return [
        change
        for org in sorted(old_by_org)
        for change in diff_profile(old_by_org[org], new_by_org[org])
    ]


def apply_safe_refresh(
    previous: dict[str, Any],
    refreshed: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Applies a refresh while enforcing the non-erasure rule.
    
    Organizer Specification Requirement 5:
    'A failed refresh must not erase the last supported value.'
    
    If the refresh encounters an error or returns empty/unavailable data for
    a module that previously had valid supported data, the previous value is
    preserved and retained in the updated profile.
    """
    merged = copy.deepcopy(previous)
    prev_ev = previous.get("evidence", {})
    ref_ev = refreshed.get("evidence", {})

    for mod, ref_record in ref_ev.items():
        prev_record = prev_ev.get(mod, {})
        ref_status = ref_record.get("status")
        ref_val = ref_record.get("value")

        # Non-erasure rule: If refresh failed or was empty, but previous was available
        if ref_status in {"source_error", "blocked", "not_found", "failed", "unavailable"} or ref_val in (None, "", [], {}):
            if prev_record.get("status") == "available" and prev_record.get("value") not in (None, "", [], {}):
                # Preserve previous value and note the failed refresh attempt
                preserved_rec = copy.deepcopy(prev_record)
                preserved_rec["refresh_attempted_at"] = ref_record.get("retrieved_at")
                preserved_rec["refresh_error"] = ref_record.get("note") or f"Status: {ref_status}"
                merged.setdefault("evidence", {})[mod] = preserved_rec
                continue

        # If refresh succeeded, adopt the new snapshot
        merged.setdefault("evidence", {})[mod] = ref_record

    # Emit typed changes
    changes = diff_profile(previous, merged)
    return merged, changes
