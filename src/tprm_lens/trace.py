from __future__ import annotations

class Trace:
    def __init__(self, timestamp: str = "2026-08-13T12:00:00Z") -> None:
        self.nodes: list[dict] = []
        self.timestamp = timestamp

    def emit(self, stage: str, kind: str, label: str, detail: str = "", parent_id: str | None = None,
             refs: list[str] | None = None, confidence: float | None = None) -> str:
        node_id = f"n{len(self.nodes) + 1}"
        self.nodes.append({
            "seq": len(self.nodes) + 1,
            "ts": self.timestamp,
            "stage": stage,
            "node_id": node_id,
            "parent_id": parent_id,
            "kind": kind,
            "label": label,
            "detail": detail,
            "refs": refs or [],
            "confidence": confidence,
        })
        return node_id
