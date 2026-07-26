"""Response and plan synthesis for the deterministic baseline."""

from __future__ import annotations

from typing import Any, Mapping


def compose(*, perception: Mapping[str, Any], world: Mapping[str, Any]) -> dict[str, Any]:
    retrieval = world.get("retrieval")
    top_title = ""
    if isinstance(retrieval, list) and retrieval and isinstance(retrieval[0], Mapping):
        top_title = str(retrieval[0].get("title", "")).strip()

    if top_title:
        answer = f"{perception.get('summary', '')} Relevant ATM10 context: {top_title}."
        mode = "grounded_file_world"
    else:
        answer = (
            f"{perception.get('summary', '')} No matching local world evidence was found; "
            "continue without claiming grounded guidance."
        )
        mode = "ungrounded_degraded"

    return {
        "schema_version": "atm10_response_plan_v1",
        "status": "ok" if top_title else "degraded",
        "mode": mode,
        "answer": answer.strip(),
        "next_steps": list(perception.get("next_steps", [])),
    }
