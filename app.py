# ------------------------
# app.py  (repo-root shim)
# ------------------------
"""
Thin shim so `streamlit run app.py` works from the repo root. The real app lives in
``dynamix.webapp.app``. Prefer the console script: `dynamix-gui`.
"""
from dynamix.webapp.app import main

main()
