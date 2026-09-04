# Validation routes

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m scripts.phase_a_smoke --vlm-provider stub --runs-dir runs\smoke-phase-a
python -m scripts.retrieve_demo --in tests/fixtures/retrieval_docs_sample.jsonl --query "mekanism steel" --topk 3 --candidate-k 10 --reranker none --runs-dir runs\smoke-retrieve
atm10 eval --suite companion-core --runs-dir runs\eval --state-dir .atm10-state\eval --reports-dir eval-results
```

Use the repository root `VALIDATION.md` for the full suite and its
`Decision records and indexes` route for decision-lane checks.
