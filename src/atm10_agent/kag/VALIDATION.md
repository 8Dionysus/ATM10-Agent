# Validation routes

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_kag_neo4j_backend.py tests/test_kag_build_baseline.py tests/test_kag_query_demo.py tests/test_kag_query_neo4j.py tests/test_kag_sync_neo4j.py tests/test_eval_kag_file.py tests/test_eval_kag_neo4j.py
```
