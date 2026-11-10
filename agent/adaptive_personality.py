"""Adaptive Personality — explicit, persistent user-preference profile.

Builds on the existing built-in memory store (MEMORY.md / USER.md) via
``MemoryStore``. Preferences are stored as structured entries in USER.md
(profile-scoped through ``get_hermes_home()``), loaded at session start into
a frozen system-prompt snapshot (prefix-cache safe), and surfaced to the
agent through a dedicated volatile-tier prompt block.

Only *explicit* user preferences are persisted — current-task instructions
never silently become permanent preferences. The first implementation is
explicit-input only; no automatic inference from conversation history.

All writes flow through the existing memory-tool approval gates; destructive
operations keep their existing gates.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from tools.memory_tool_store import MemoryStore, ENTRY_DELIMITER

logger = logging.getLogger(__name__)

# Entry prefix that distinguishes a structured preference from a plain-text
# user-profile entry in USER.md. MemoryStore joins entries with ENTRY_DELIMITER
# and persists them to USER.md under the profile's memories/ directory.
PREFERENCE_ENTRY_PREFIX = "PREF:"

# Schema version for forward-compatible migrations.
PREFERENCE_SCHEMA_VERSION = 1

# Valid scopes. "global" applies to every session; "domain:<name>" is a named
# task/domain context the user has bound the preference to.
VALID_SCOPES = frozenset({"global"})

# Valid provenance values. "explicit" = user stated it directly; "confirmed"
# = user confirmed a suggested preference.
VALID_PROVENANCE = frozenset({"explicit", "confirmed"})


@dataclass
class Preference:
    """A single explicit user preference."""

    category: str
    preference: str
    scope: str = "global"
    provenance: str = "explicit"
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    version: int = PREFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.scope not in VALID_SCOPES and not self.scope.startswith("domain:"):
            raise ValueError(f"invalid scope: {self.scope!r}")
        if self.provenance not in VALID_PROVENANCE:
            raise ValueError(f"invalid provenance: {self.provenance!r}")
        if not self.category or not self.preference:
            raise ValueError("category and preference must be non-empty")

    def to_entry(self) -> str:
        """Serialize as a single USER.md entry string."""
        data = {
            "category": self.category,
            "preference": self.preference,
            "scope": self.scope,
            "provenance": self.provenance,
            "updated_at": self.updated_at,
            "version": self.version,
        }
        return f"{PREFERENCE_ENTRY_PREFIX}{json.dumps(data, ensure_ascii=False)}"

    @classmethod
    def from_entry(cls, entry: str) -> Optional["Preference"]:
        """Parse a USER.md entry into a :class:`Preference`, or ``None`` when
        the entry is not a structured preference (plain text or malformed)."""
        if not entry.startswith(PREFERENCE_ENTRY_PREFIX):
            return None
        json_str = entry[len(PREFERENCE_ENTRY_PREFIX):]
        try:
            data = json.loads(json_str)
            if not isinstance(data, dict):
                return None
            return cls(
                category=str(data.get("category", "")),
                preference=str(data.get("preference", "")),
                scope=str(data.get("scope", "global")),
                provenance=str(data.get("provenance", "explicit")),
                updated_at=str(
                    data.get("updated_at")
                    or datetime.now(timezone.utc).isoformat()
                ),
                version=int(data.get("version", PREFERENCE_SCHEMA_VERSION)),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Malformed preference entry, skipping: %.80s", entry)

class AdaptivePersonalityManager:
    """Manage explicit user preferences stored in the built-in USER.md store.

    Wraps a :class:`MemoryStore` and parses preference entries out of its user
    entries. All persistence goes through the wrapped store, so preference
    writes use the same approval gates, threat scanning, and char limits as
    the rest of the user profile.

    One instance per AIAgent, bound to the agent's profile home. No global
    mutable state; profile isolation is inherited from the store.
    """

    def __init__(self, store: MemoryStore) -> None:
        self._store = store
        self._preferences: dict[str, Preference] = {}
        self._loaded = False

    def load(self) -> None:
        self._preferences = {}
        for entry in self._store._entries_for("user"):
            pref = Preference.from_entry(entry)
            if pref is not None:
                key = self._pref_key(pref.category, pref.scope)
                self._preferences[key] = pref
        self._loaded = True
        logger.debug(
            "Adaptive Personality loaded %d preference(s) for profile",
            len(self._preferences),
        )

    @staticmethod
    def _pref_key(category: str, scope: str) -> str:
        return f"{category}|{scope}"

    def get_preferences(self) -> list[Preference]:
        return sorted(self._preferences.values(), key=lambda p: (p.category, p.scope))

    def get_preference(self, category: str, scope: str = "global") -> Optional[Preference]:
        return self._preferences.get(self._pref_key(category, scope))

    def has_preferences(self) -> bool:
        return bool(self._preferences)

    def add_preference(self, preference: Preference) -> dict[str, Any]:
        key = self._pref_key(preference.category, preference.scope)
        entry = preference.to_entry()

        existing = self._preferences.get(key)
        if existing is not None:
            for old_entry in self._store._entries_for("user"):
                old_pref = Preference.from_entry(old_entry)
                if old_pref is not None and self._pref_key(
                    old_pref.category, old_pref.scope
                ) == key:
                    rm = self._store.remove("user", old_entry)
                    if not rm.get("success"):
                        return rm
                    result = self._store.add("user", entry)
                    if result.get("success"):
                        self._preferences[key] = preference
                    return result
                    break

        result = self._store.add("user", entry)
        if result.get("success"):
            self._preferences[key] = preference
        return result

    def remove_preference(self, category: str, scope: str = "global") -> dict[str, Any]:
        key = self._pref_key(category, scope)
        existing = self._preferences.get(key)
        if existing is None:
            return {"success": False, "error": f"no preference for {key}"}

        for old_entry in self._store._entries_for("user"):
            old_pref = Preference.from_entry(old_entry)
            if old_pref is not None and self._pref_key(
                old_pref.category, old_pref.scope
            ) == key:
                result = self._store.remove("user", old_entry)
                if result.get("success"):
                    del self._preferences[key]
                return result
                break

        return {"success": False, "error": f"preference entry not found for {key}"}

    def clear(self) -> dict[str, Any]:
        removed = 0
        errors: list[str] = []
        for key in list(self._preferences.keys()):
            category, _, scope = key.partition("|")
            result = self.remove_preference(category, scope or "global")
            if result.get("success"):
                removed += 1
            else:
                errors.append(result.get("error", "unknown error"))
        return {
            "success": len(errors) == 0,
            "removed": removed,
            "errors": errors,
        }

    def build_personality_block(self) -> str:
        if not self._preferences:
            return ""
        lines = ["═" * 46, "ADAPTIVE PERSONALITY (user preferences)", "═" * 46]
        for pref in self.get_preferences():
            scope_tag = f" [{pref.scope}]" if pref.scope != "global" else ""
            prov_tag = f" ({pref.provenance})" if pref.provenance != "explicit" else ""
            lines.append(f"- {pref.category}{scope_tag}{prov_tag}: {pref.preference}")
        lines.append("═" * 46)
        lines.append(
            "Honor these stated preferences in your communication and work. "
            "They apply across sessions; an explicit current-task instruction "
            "overrides them for this task only."
        )
        return "\n".join(lines)

    def schema_version(self) -> int:
        return PREFERENCE_SCHEMA_VERSION

    def needs_migration(self) -> bool:
        return any(p.version < PREFERENCE_SCHEMA_VERSION for p in self._preferences.values())


def build_personality_block_from_store(store: Optional[MemoryStore]) -> str:
    """Convenience: render a personality block from a store's current entries.

    Parses preference entries on the fly without constructing a manager.
    Returns ``""`` when the store is ``None`` or has no preferences.
    """
    if store is None:
        return ""
    prefs: list[Preference] = []
    for entry in store._entries_for("user"):
        pref = Preference.from_entry(entry)
        if pref is not None:
            prefs.append(pref)
    if not prefs:
        return ""
    lines = ["═" * 46, "ADAPTIVE PERSONALITY (user preferences)", "═" * 46]
    for pref in sorted(prefs, key=lambda p: (p.category, p.scope)):
        scope_tag = f" [{pref.scope}]" if pref.scope != "global" else ""
        prov_tag = f" ({pref.provenance})" if pref.provenance != "explicit" else ""
        lines.append(f"- {pref.category}{scope_tag}{prov_tag}: {pref.preference}")
    lines.append("═" * 46)
    lines.append(
        "Honor these stated preferences in your communication and work. "
        "They apply across sessions; an explicit current-task instruction "
        "overrides them for this task only."
    )
    return "\n".join(lines)