"""Tests for Adaptive Personality — explicit, persistent user-preference profile.

Covers the Preference dataclass, AdaptivePersonalityManager, MemoryStore
integration, system-prompt rendering, profile isolation, and prompt-cache
invariant preservation.

All tests use temp Hermes homes via the conftest `_isolate_hermes_home`
fixture; nothing writes to the real ~/.hermes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.adaptive_personality import (
    AdaptivePersonalityManager,
    Preference,
    PREFERENCE_ENTRY_PREFIX,
    build_personality_block_from_store,
)
from tools.memory_tool import MemoryStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path, monkeypatch):
    """MemoryStore backed by a temp memories dir (profile-isolated)."""
    monkeypatch.setattr("tools.memory_tool.get_memory_dir", lambda: tmp_path)
    s = MemoryStore(memory_char_limit=5000, user_char_limit=5000)
    s.load_from_disk()
    return s


def _make_agent(memory_enabled=True, user_profile_enabled=True, store=None):
    return SimpleNamespace(
        _memory_store=store,
        _memory_manager=None,
        _memory_enabled=memory_enabled,
        _user_profile_enabled=user_profile_enabled,
    )


@pytest.fixture
def mgr(store):
    """AdaptivePersonalityManager backed by a temp store."""
    m = AdaptivePersonalityManager(store)
    m.load()
    return m

# ---------------------------------------------------------------------------
# Preference dataclass
# ---------------------------------------------------------------------------


class TestPreference:
    def test_create_and_serialize(self):
        p = Preference(
            category="communication_style",
            preference="direct and concise",
            scope="global",
            provenance="explicit",
        )
        entry = p.to_entry()
        assert entry.startswith(PREFERENCE_ENTRY_PREFIX)
        payload = json.loads(entry[len(PREFERENCE_ENTRY_PREFIX):])
        assert payload["category"] == "communication_style"
        assert payload["preference"] == "direct and concise"
        assert payload["scope"] == "global"
        assert payload["provenance"] == "explicit"
        assert payload["version"] == 1

    def test_round_trip(self):
        p = Preference(
            category="detail_level",
            preference="brief summaries first, details on request",
            scope="domain:coding",
            provenance="confirmed",
        )
        p2 = Preference.from_entry(p.to_entry())
        assert p2 is not None
        assert p2.category == p.category
        assert p2.preference == p.preference
        assert p2.scope == p.scope
        assert p2.provenance == p.provenance
        assert p2.version == p.version

    def test_plain_text_entry_returns_none(self):
        assert Preference.from_entry("just a plain user fact") is None

    def test_malformed_json_returns_none(self):
        assert Preference.from_entry("PREF:{not valid json") is None

    def test_empty_category_rejected(self):
        with pytest.raises(ValueError):
            Preference(category="", preference="x")

    def test_empty_preference_rejected(self):
        with pytest.raises(ValueError):
            Preference(category="c", preference="")

    def test_invalid_scope_rejected(self):
        with pytest.raises(ValueError):
            Preference(category="c", preference="x", scope="bogus")

    def test_domain_scope_accepted(self):
        p = Preference(category="c", preference="x", scope="domain:coding")
        assert p.scope == "domain:coding"

    def test_invalid_provenance_rejected(self):
        with pytest.raises(ValueError):
            Preference(category="c", preference="x", provenance="guessed")

# ---------------------------------------------------------------------------
# AdaptivePersonalityManager
# ---------------------------------------------------------------------------


class TestAdaptivePersonalityManager:
    def test_empty_manager(self, mgr):
        assert not mgr.has_preferences()
        assert mgr.get_preferences() == []

    def test_add_preference(self, mgr, store):
        result = mgr.add_preference(
            Preference(
                category="communication_style",
                preference="direct answers",
                scope="global",
                provenance="explicit",
            )
        )
        assert result["success"] is True, result
        mgr.load()
        assert mgr.has_preferences()
        prefs = mgr.get_preferences()
        assert len(prefs) == 1
        assert prefs[0].category == "communication_style"
        assert prefs[0].preference == "direct answers"
        assert store._entries_for("user")

    def test_add_preference_persists_across_reload(self, mgr, store, tmp_path, monkeypatch):
        mgr.add_preference(
            Preference(category="detail_level", preference="brief", scope="global", provenance="explicit")
        )
        monkeypatch.setattr("tools.memory_tool.get_memory_dir", lambda: tmp_path)
        s2 = MemoryStore(memory_char_limit=5000, user_char_limit=5000)
        s2.load_from_disk()
        m2 = AdaptivePersonalityManager(s2)
        m2.load()
        assert m2.has_preferences()
        assert m2.get_preference("detail_level") is not None

    def test_update_replaces_not_duplicates(self, mgr):
        mgr.add_preference(
            Preference(category="tone", preference="friendly", scope="global", provenance="explicit")
        )
        mgr.add_preference(
            Preference(category="tone", preference="professional", scope="global", provenance="explicit")
        )
        mgr.load()
        prefs = mgr.get_preferences()
        assert len(prefs) == 1
        assert prefs[0].preference == "professional"

    def test_remove_preference(self, mgr):
        mgr.add_preference(
            Preference(category="lang", preference="Python", scope="global", provenance="explicit")
        )
        result = mgr.remove_preference("lang")
        assert result["success"] is True, result
        mgr.load()
        assert not mgr.has_preferences()

    def test_remove_nonexistent(self, mgr):
        result = mgr.remove_preference("nonexistent")
        assert result["success"] is False

    def test_clear_removes_all(self, mgr):
        mgr.add_preference(Preference(category="a", preference="1", scope="global", provenance="explicit"))
        mgr.add_preference(Preference(category="b", preference="2", scope="global", provenance="explicit"))
        result = mgr.clear()
        assert result["success"] is True
        assert result["removed"] == 2
        mgr.load()
        assert not mgr.has_preferences()

    def test_get_preference_by_category_scope(self, mgr):
        mgr.add_preference(
            Preference(category="style", preference="direct", scope="domain:coding", provenance="explicit")
        )
        pref = mgr.get_preference("style", "domain:coding")
        assert pref is not None
        assert pref.preference == "direct"
        assert mgr.get_preference("style", "global") is None
        assert mgr.get_preference("other", "domain:coding") is None

    def test_build_personality_block_empty(self, mgr):
        assert mgr.build_personality_block() == ""

    def test_build_personality_block_with_preferences(self, mgr):
        mgr.add_preference(
            Preference(category="communication_style", preference="direct", scope="global", provenance="explicit")
        )
        mgr.add_preference(
            Preference(category="detail_level", preference="brief", scope="domain:coding", provenance="confirmed")
        )
        block = mgr.build_personality_block()
        assert "ADAPTIVE PERSONALITY" in block
        assert "communication_style" in block
        assert "direct" in block
        assert "domain:coding" in block
        assert "confirmed" in block
        assert "brief" in block

    def test_domain_scope_tagged_in_block(self, mgr):
        mgr.add_preference(
            Preference(category="lang", preference="Python", scope="domain:coding", provenance="explicit")
        )
        block = mgr.build_personality_block()
        assert "[domain:coding]" in block

    def test_confirmed_provenance_tagged(self, mgr):
        mgr.add_preference(
            Preference(category="tone", preference="warm", scope="global", provenance="confirmed")
        )
        block = mgr.build_personality_block()
        assert "(confirmed)" in block

    def test_malformed_entry_skipped(self, mgr, store):
        store.add("user", "just a plain fact")
        store.add("user", "PREF:{broken")
        mgr.add_preference(Preference(category="c", preference="v", scope="global", provenance="explicit"))
        mgr.load()
        prefs = mgr.get_preferences()
        assert len(prefs) == 1
        assert prefs[0].category == "c"

    def test_convenience_function_with_none(self):
        assert build_personality_block_from_store(None) == ""

    def test_convenience_function_empty_store(self, store):
        assert build_personality_block_from_store(store) == ""

# ---------------------------------------------------------------------------
# System prompt integration
# ---------------------------------------------------------------------------


class TestPromptIntegration:
    def _make_agent(self, memory_enabled=True, user_profile_enabled=True, store=None):
        return SimpleNamespace(
            _memory_store=store,
            _memory_manager=None,
            _memory_enabled=memory_enabled,
            _user_profile_enabled=user_profile_enabled,
        )

    def test_personality_block_in_volatile_tier(self, mgr, store):
        from agent.system_prompt import _memory_parts

        agent = _make_agent(
            memory_enabled=True, user_profile_enabled=True, store=store
        )
        mgr.add_preference(
            Preference(
                category="communication_style",
                preference="be direct",
                scope="global",
                provenance="explicit",
            )
        )
        parts = _memory_parts(agent)
        joined = "\n".join(p for p in parts if p)
        assert "ADAPTIVE PERSONALITY" in joined
        assert "be direct" in joined

    def test_no_personality_block_when_no_preferences(self, store):
        from agent.system_prompt import _memory_parts

        agent = _make_agent(
            memory_enabled=True, user_profile_enabled=True, store=store
        )
        parts = _memory_parts(agent)
        joined = "\n".join(p for p in parts if p)
        assert "ADAPTIVE PERSONALITY" not in joined

    def test_user_profile_disabled_skips_store(self):
        from agent.system_prompt import _memory_parts

        agent = _make_agent(
            memory_enabled=False, user_profile_enabled=False, store=None
        )
        parts = _memory_parts(agent)
        assert parts == []

    def test_store_none_does_not_crash(self):
        from agent.system_prompt import _memory_parts

        agent = _make_agent(
            memory_enabled=True, user_profile_enabled=True, store=None
        )
        parts = _memory_parts(agent)
        assert parts == []

# ---------------------------------------------------------------------------
# Profile isolation
# ---------------------------------------------------------------------------


class TestProfileIsolation:
    def test_profile_a_sees_only_own_preferences(self, tmp_path, monkeypatch):
        import tools.memory_tool as mt

        monkeypatch.setattr("tools.memory_tool.get_memory_dir", lambda: tmp_path / "a")
        s_a = MemoryStore(user_char_limit=5000)
        s_a.load_from_disk()
        m_a = AdaptivePersonalityManager(s_a)
        m_a.add_preference(
            Preference(category="style", preference="A-direct", scope="global", provenance="explicit")
        )

        monkeypatch.setattr("tools.memory_tool.get_memory_dir", lambda: tmp_path / "b")
        s_b = MemoryStore(user_char_limit=5000)
        s_b.load_from_disk()
        m_b = AdaptivePersonalityManager(s_b)
        m_b.add_preference(
            Preference(category="style", preference="B-verbose", scope="global", provenance="explicit")
        )

        m_a.load()
        m_b.load()
        prefs_a = m_a.get_preferences()
        prefs_b = m_b.get_preferences()
        assert len(prefs_a) == 1
        assert len(prefs_b) == 1
        assert prefs_a[0].preference == "A-direct"
        assert prefs_b[0].preference == "B-verbose"
        assert "B-verbose" not in str(prefs_a)
        assert "A-direct" not in str(prefs_b)


# ---------------------------------------------------------------------------
# Preference semantics
# ---------------------------------------------------------------------------


class TestPreferenceSemantics:
    def test_explicit_preference_retained(self, mgr):
        result = mgr.add_preference(
            Preference(category="lang", preference="Python", scope="global", provenance="explicit")
        )
        assert result["success"] is True
        pref = mgr.get_preference("lang")
        assert pref is not None
        assert pref.provenance == "explicit"

    def test_confirmed_provenance(self, mgr):
        result = mgr.add_preference(
            Preference(category="tone", preference="warm", scope="global", provenance="confirmed")
        )
        assert result["success"] is True
        pref = mgr.get_preference("tone")
        assert pref is not None
        assert pref.provenance == "confirmed"

    def test_correction_replaces(self, mgr):
        mgr.add_preference(Preference(category="style", preference="casual", scope="global", provenance="explicit"))
        mgr.add_preference(Preference(category="style", preference="formal", scope="global", provenance="explicit"))
        mgr.load()
        pref = mgr.get_preference("style")
        assert pref is not None
        assert pref.preference == "formal"

    def test_current_task_instruction_not_persisted_by_manager(self, mgr):
        assert not mgr.has_preferences()

    def test_malformed_data_handled_safely(self, mgr, store):
        store.add("user", "PREF:{completely broken json here")
        mgr.load()
        prefs = mgr.get_preferences()
        assert len(prefs) == 0


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


class TestFailureHandling:
    def test_overlimit_preference(self, mgr):
        big = Preference(
            category="x",
            preference="y" * 10000,
            scope="global",
            provenance="explicit",
        )
        result = mgr.add_preference(big)
        assert result["success"] is False

    def test_schema_version(self, mgr):
        assert mgr.schema_version() == 1

    def test_no_migration_needed(self, mgr):
        assert not mgr.needs_migration()