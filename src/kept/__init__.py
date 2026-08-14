"""kept — an evidence ledger for agent-written code.

Your spec is a list of promises. `kept` proves, per promise, which ones your
code actually keeps, and it does not take a test suite's word for it.

`kept` produces evidence, not proof. See `docs/` for the verdict taxonomy and
the limits of what mutation survival does and does not establish.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
