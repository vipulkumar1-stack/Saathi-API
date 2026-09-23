"""Types for the generated API spec (src/spec/operations.py, endpoints.py).

Populated by tools/import_postman.py from postman/collection_raw.json.
Do not hand-edit the generated files - re-run the importer instead.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class OperationDef:
    """A single named GraphQL operation captured from the collection."""
    service: str            # e.g. "finex", "payout", "insurance", "bank-integration", "reporting-api"
    name: str                # operation name, or a derived name if the body was anonymous
    kind: str                 # "query" | "mutation"
    path: str                 # e.g. "/finex/api/v1/graphql"
    query: str
    variables: Dict[str, Any] = field(default_factory=dict)
    anonymous: bool = False   # True if the captured body had no operation name
    confidence: str = "confirmed"  # "confirmed" (from collection) | "inferred"


@dataclass(frozen=True)
class EndpointDef:
    """A single REST endpoint captured from the collection."""
    service: str
    name: str
    method: str
    path: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None
    confidence: str = "confirmed"
