"""Adapters that observe a target project by running its test suite."""

from __future__ import annotations

from kept.observe.discover import DiscoveryError, discover_bindings

__all__ = ["DiscoveryError", "discover_bindings"]
