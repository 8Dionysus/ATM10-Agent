# Validation routes

## Repository setup and full suite

```powershell
cd <repo>
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
```

## Public surface and hardening

```powershell
python -m pytest tests/test_antifragility_public_surface.py
```

```powershell
python -m pytest tests/test_public_repo_hardening.py tests/test_workflow_public_surface.py tests/test_nested_agents_docs.py
```

## Decision records and indexes

```powershell
cd <repo-root>
python -m scripts.generate_decision_indexes
python -m scripts.generate_decision_indexes --check
python -m scripts.validate_decision_records
python -m pytest tests/test_decision_indexes.py tests/test_nested_agents_docs.py tests/test_validate_nested_agents.py
```
