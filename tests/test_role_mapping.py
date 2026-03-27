from __future__ import annotations

import pytest

from clogem.role_mapping import (
    DEFAULT_ROLE_PROVIDER_MAP,
    needed_providers,
    parse_role_provider_map_env,
    parse_role_provider_pairs,
    resolve_role_provider_map,
)


def test_parse_role_provider_pairs_valid() -> None:
    out = parse_role_provider_pairs(["coder=claude", "reviewer=gemini"])
    assert out == {"coder": "claude", "reviewer": "gemini"}


def test_parse_role_provider_pairs_invalid_role() -> None:
    with pytest.raises(ValueError):
        parse_role_provider_pairs(["writer=codex"])


def test_parse_role_provider_map_env_empty() -> None:
    assert parse_role_provider_map_env("") == {}


def test_resolve_role_provider_map_precedence_cli_over_env() -> None:
    out = resolve_role_provider_map(
        env_map_raw="coder=gemini,reviewer=claude",
        cli_pairs=["coder=claude"],
    )
    assert out["coder"] == "claude"
    assert out["reviewer"] == "claude"
    assert out["summariser"] == DEFAULT_ROLE_PROVIDER_MAP["summariser"]


def test_needed_providers_from_roles() -> None:
    mapping = {
        "orchestrator": "codex",
        "planner": "claude",
        "coder": "claude",
        "reviewer": "gemini",
        "summariser": "gemini",
    }
    assert needed_providers(mapping) == {"codex", "claude", "gemini"}
