# taskboard (VeriCode demo project)

Small task-tracking library used by the VeriCode demos. Its `.venv` pins **pydantic 2.9.2** while
`requirements.txt` still declares the old `pydantic>=1.10` range - a realistic setup where an LLM's
Pydantic-v1 knowledge produces code that breaks on the installed version.

Setup: `python3 -m venv .venv && .venv/bin/pip install pydantic==2.9.2 pytest`
