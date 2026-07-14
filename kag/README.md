# ATM10-Agent Local KAG Provider

`kag/` exposes the current `ATM10-Agent` KAG provider packet as portable
source-linked records.

## Operating Card

| Field | Route |
| --- | --- |
| role | local KAG provider for project-local retrieval, KAG runtime code, and operator runbook handles |
| records | `nodes/`, `edges/`, `indexes/`, `projections/`, `receipts/` |
| manifest | `manifest.json` |
| source route | `docs/RUNBOOK.md`, `stats/README.md`, `src/kag/baseline.py`, `src/kag/neo4j_backend.py` |
| consumer route | `aoa-kag` registry/composition, `abyss-stack`, MCP resources |
| owner return | `docs/RUNBOOK.md` |

## Record Classes

| Class | Current record |
| --- | --- |
| node | source surface and owner-return route |
| edge | source surface returns to the owner route |
| index | repository source, entity, artifact, and event indexes |
| projection | MCP-readable source-return packet |
| receipt | validation receipt for the current owner route |

Git holds compact provider records and source-return handles. Runtime graph,
vector, embedding, cache, and serving state stay with runtime owners.
