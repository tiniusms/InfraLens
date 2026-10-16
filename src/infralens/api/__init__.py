"""Read-only HTTP adapter for the existing InfraLens modules.

The adapter does not train, score, ingest, or recalculate frozen evaluation
statistics. Financial amounts come from ``infralens.finance``.
"""

from infralens.api.app import create_app

__all__ = ["create_app"]
