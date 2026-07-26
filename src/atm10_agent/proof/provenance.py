"""Small source and evidence handles for ATM10-owned proof surfaces."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


PROVENANCE_KINDS = {
    "artifact",
    "fixture",
    "revision",
    "source",
    "test",
    "trace",
}
PROVENANCE_ROLES = {"primary", "supporting", "derived"}
_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ProvenanceRef:
    """A bounded handle to evidence without importing another authority."""

    ref: str
    kind: str
    role: str = "supporting"
    owner: str = "ATM10-Agent"
    revision: str | None = None

    def __post_init__(self) -> None:
        if not self.ref.strip():
            raise ValueError("provenance ref must not be empty")
        if self.kind not in PROVENANCE_KINDS:
            raise ValueError(f"unsupported provenance kind: {self.kind!r}")
        if self.role not in PROVENANCE_ROLES:
            raise ValueError(f"unsupported provenance role: {self.role!r}")
        if not self.owner.strip():
            raise ValueError("provenance owner must not be empty")
        if self.revision is not None and not _GIT_REVISION.fullmatch(self.revision):
            raise ValueError("provenance revision must be a 40-character git SHA")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
