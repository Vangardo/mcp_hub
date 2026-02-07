"""Rule-based evaluation for memory auto-save decisions."""

import re

SECRET_PATTERNS = re.compile(
    r"(password|passwd|secret|api_key|api_secret|private_key|access_token|"
    r"refresh_token|bearer|authorization|credential|ssh_key|pgp_key|"
    r"mnemonic|seed_phrase|recovery_phrase)",
    re.IGNORECASE,
)

DURABLE_TYPES = {"preference", "constraint", "decision"}
ENTITY_TYPES = {"asset", "project", "contact"}
GOAL_TYPES = {"goal"}
NOTE_TYPES = {"note"}

VALID_TYPES = DURABLE_TYPES | ENTITY_TYPES | GOAL_TYPES | NOTE_TYPES
VALID_SENSITIVITIES = {"low", "medium", "high"}


def evaluate_write(candidate: dict) -> dict:
    """
    Evaluate whether a memory item should be saved and with what parameters.

    Returns:
        {
            "allow": bool,
            "type": str,           # validated/suggested type
            "ttl_days": int|None,  # None = permanent
            "sensitivity": str,
            "reason_code": str,
        }
    """
    title = str(candidate.get("title", ""))
    value = str(candidate.get("value_json", ""))
    item_type = candidate.get("type", "note")
    sensitivity = candidate.get("sensitivity", "low")
    pinned = candidate.get("pinned", False)
    explicit = candidate.get("explicit", False)  # user explicitly said "запомни"

    # Normalize
    if item_type not in VALID_TYPES:
        item_type = "note"
    if sensitivity not in VALID_SENSITIVITIES:
        sensitivity = "low"

    # Rule 1: Reject secrets
    combined = f"{title} {value}"
    if SECRET_PATTERNS.search(combined):
        # Allow only if user explicitly asked and it's not the actual secret value
        if not explicit:
            return {
                "allow": False,
                "type": item_type,
                "ttl_days": None,
                "sensitivity": "high",
                "reason_code": "SECRET_REJECTED",
            }
        # If explicit, allow but mark high sensitivity
        sensitivity = "high"

    # Rule 2: High sensitivity without explicit user request
    if sensitivity == "high" and not explicit:
        return {
            "allow": False,
            "type": item_type,
            "ttl_days": None,
            "sensitivity": "high",
            "reason_code": "HIGH_SENSITIVITY_NEEDS_EXPLICIT",
        }

    # Rule 3: Durable types (preference, constraint, decision)
    if item_type in DURABLE_TYPES:
        return {
            "allow": True,
            "type": item_type,
            "ttl_days": None,
            "sensitivity": sensitivity,
            "reason_code": "PREFERENCE_STABLE",
        }

    # Rule 4: Entity types (asset, project, contact)
    if item_type in ENTITY_TYPES:
        return {
            "allow": True,
            "type": item_type,
            "ttl_days": None,
            "sensitivity": sensitivity,
            "reason_code": "DURABLE_ENTITY",
        }

    # Rule 5: Goals
    if item_type in GOAL_TYPES:
        return {
            "allow": True,
            "type": item_type,
            "ttl_days": 30,
            "sensitivity": sensitivity,
            "reason_code": "GOAL_MEDIUM_TERM",
        }

    # Rule 6: Notes — short-term unless pinned
    if item_type in NOTE_TYPES:
        ttl = None if pinned else 7
        reason = "USER_PINNED" if pinned else "SHORT_TERM_NOTE"
        return {
            "allow": True,
            "type": item_type,
            "ttl_days": ttl,
            "sensitivity": sensitivity,
            "reason_code": reason,
        }

    # Default: short-term
    return {
        "allow": True,
        "type": item_type,
        "ttl_days": 7,
        "sensitivity": sensitivity,
        "reason_code": "DEFAULT_SHORT_TERM",
    }
