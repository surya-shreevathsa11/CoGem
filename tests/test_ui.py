from __future__ import annotations

from clogem.ui import boot_sequence


def test_boot_sequence_allows_empty_required_provider_set() -> None:
    # With no required providers, boot sequence should complete without
    # checking external CLIs/SDK keys.
    assert boot_sequence(required_providers=set()) is True
