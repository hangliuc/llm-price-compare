import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvidenceRecord:
    source_id: str
    artifact_kind: str
    content_type: str
    sha256: str
    artifact_path: str
    byte_size: int


def _bytes(payload: Any, content_type: str) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def persist_evidence(root: Path, source_id: str, payload: Any,
                     artifact_kind: str = "raw_response",
                     content_type: str = "application/json") -> EvidenceRecord:
    raw = _bytes(payload, content_type)
    digest = hashlib.sha256(raw).hexdigest()
    suffix = "html" if "html" in content_type else "json"
    target = root / "objects" / digest[:2] / f"{digest}.{suffix}.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(target.suffix + ".tmp")
        with gzip.open(temporary, "wb", compresslevel=6) as handle:
            handle.write(raw)
        temporary.replace(target)
    return EvidenceRecord(source_id, artifact_kind, content_type, digest,
                          str(target), len(raw))

