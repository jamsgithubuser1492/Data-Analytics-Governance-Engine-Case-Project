# Getting started

## Run the app
```bash
pip install -r requirements.txt
python -m streamlit run app/app.py     # opens http://localhost:8501
```
If `streamlit: command not found` appears, keep the `python -m` prefix. On the Dashboard choose **Try with demo data**. It uses the verified case study files in `data/`, so the result is identical every time.

## One command with Docker
```bash
docker build -t mmge . && docker run -p 8501:8501 mmge     # then open http://localhost:8501
```
The Docker image runs in demo mode: sample data loads by itself and uploads are switched off. To use your own data, run with pip as above.

## Update to the latest version
`pip install` installs libraries only. It never updates the code, and a running app keeps serving old files.
```bash
git status                    # files under outputs/ or data/ are generated and can be set aside
git stash                     # or: git checkout -- outputs data
git checkout main
git pull origin main
# stop the running app with Ctrl+C, then start it again
python -m streamlit run app/app.py
```
The sidebar shows a **Version** line (commit and date). Confirm it matches the latest commit on GitHub.

## Why a pull can be refused
The optional commands `python python/database_manager.py` and `python python/governance_checker.py` rewrite tracked files in `outputs/`. Git then refuses a pull to protect those edits. Stash or discard them as above.

## Checks
```bash
python python/verify_data.py   # confirms data/*.csv match the verified originals
pytest                         # full test suite
```

## Where things are
| Need | Go to |
| --- | --- |
| How numbers are produced and what they mean | `docs/METHODOLOGY.md` (also the How it works page) |
| Privacy and governance | `docs/PRIVACY_AND_GOVERNANCE.md` |
| Writing rules | `docs/VOICE_GUIDE.md` |
| Automation design | `docs/ARCHITECTURE_MCP.md` |
| Status and roadmap | `docs/NEXT_PHASE.md` |
| History | `docs/CHANGELOG.md` |
| Each page explained | `docs/PAGE_GUIDE.md` |
| Plain word glossary | `docs/GLOSSARY.md` |
| Skills by role | `docs/ROLE_FIT.md` |
| Putting it online | `docs/DEPLOY.md` |
