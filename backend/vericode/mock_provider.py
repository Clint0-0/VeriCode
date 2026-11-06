"""MOCK LLM PROVIDER - scripted, deterministic, DEMO/TEST ONLY.

It does not reason or generate code. It recognises the two bundled demo tasks and returns canned
responses that *react to context* the way a model with Pydantic-v1-era knowledge would: it emits
v1-style API calls unless the prompt contains the corrected API (from a VeriCode pre-flight briefing
or from a test-failure message). Every token count produced through it is an ESTIMATE (chars/4).
Any other task returns an explicit "no script" error so it can never masquerade as a real model.
"""
from __future__ import annotations

import json

NO_SCRIPT = "MOCK_PROVIDER_NO_SCRIPT: the scripted mock provider only supports the bundled demo tasks. Configure ANTHROPIC_API_KEY or OPENAI_API_KEY for real code generation."


def _task_kind(prompt: str) -> str | None:
    head = prompt.split("TASK:", 1)[-1][:800].lower()
    if "user" in head and "username" in head:
        return "users"
    if "priority_summary" in head:
        return "summary"
    return None


def respond(stage: str, system: str, prompt: str) -> str:
    kind = _task_kind(prompt)
    if stage == "planner":
        if kind == "users":
            return json.dumps({"packages": [{
                "package": "pydantic", "ecosystem": "python", "installed_version": None, "assumed_version": "1.10",
                "planned_apis": [
                    {"import_path": "pydantic", "name": "BaseModel", "type": "class", "arguments": [], "purpose": "User model base", "version_sensitive": False},
                    {"import_path": "pydantic", "name": "Field", "type": "function", "arguments": ["min_length", "max_length", "regex"], "purpose": "username constraints", "version_sensitive": True},
                    {"import_path": "pydantic", "name": "validator", "type": "decorator", "arguments": [], "purpose": "lowercase the email", "version_sensitive": True},
                    {"import_path": "pydantic", "name": "BaseModel.dict", "type": "method", "arguments": ["exclude"], "purpose": "serialize without email", "version_sensitive": True},
                ],
                "documentation_needed": ["pydantic validators", "Field constraints"]}], "notes": "v1-style plan"})
        if kind == "summary":
            return json.dumps({"packages": [], "notes": "No third-party APIs needed; uses project-local Task/Priority."})
        return NO_SCRIPT
    if stage in ("coder", "repair"):
        if kind == "users":
            return _users_code(prompt)
        if kind == "summary":
            return _summary_code()
        return NO_SCRIPT
    return NO_SCRIPT


def _users_code(prompt: str) -> str:
    # keep fixes already present in the current file (a model keeps its own earlier corrections)
    use_pattern = "use `pattern`" in prompt or 'pattern=r"' in prompt
    use_field_validator = "field_validator" in prompt
    use_model_dump = "model_dump" in prompt
    imports = ["BaseModel", "Field"] + (["field_validator"] if use_field_validator else ["validator"])
    constraint = 'pattern=r"^[a-z0-9_]+$"' if use_pattern else 'regex=r"^[a-z0-9_]+$"'
    if use_field_validator:
        validator_block = '    @field_validator("email")\n    @classmethod\n    def normalize_email(cls, v: str) -> str:\n        return v.strip().lower()\n'
    else:
        validator_block = '    @validator("email")\n    def normalize_email(cls, v: str) -> str:\n        return v.strip().lower()\n'
    dump = 'self.model_dump(exclude={"email"})' if use_model_dump else 'self.dict(exclude={"email"})'
    code = (
        "from __future__ import annotations\n\n"
        f"from pydantic import {', '.join(imports)}\n\n\n"
        "class User(BaseModel):\n"
        f"    username: str = Field(min_length=3, max_length=20, {constraint})\n"
        "    email: str\n\n"
        f"{validator_block}\n"
        "    def to_public_dict(self) -> dict:\n"
        f"        return {dump}\n"
    )
    edit = "FILE: taskboard/users.py\n<<<<<<< SEARCH\n=======\n" + code + ">>>>>>> REPLACE\n"
    if "taskboard/users.py" in prompt and "CURRENT CONTENT OF taskboard/users.py" in prompt:
        # repair round: replace the whole small file we created earlier
        cur = prompt.split("CURRENT CONTENT OF taskboard/users.py:\n", 1)[1].split("\n<<<END FILE>>>", 1)[0]
        edit = "FILE: taskboard/users.py\n<<<<<<< SEARCH\n" + cur + "\n=======\n" + code + ">>>>>>> REPLACE\n"
    return "Implementing the users module.\n\n" + edit


def _summary_code() -> str:
    return (
        "Adding priority_summary to TaskStore.\n\n"
        "FILE: taskboard/storage.py\n<<<<<<< SEARCH\n"
        "    def overdue(self, now: datetime) -> list[Task]:\n"
        "        return [t for t in self._tasks.values() if t.is_overdue(now)]\n"
        "=======\n"
        "    def overdue(self, now: datetime) -> list[Task]:\n"
        "        return [t for t in self._tasks.values() if t.is_overdue(now)]\n\n"
        "    def priority_summary(self) -> dict[str, int]:\n"
        "        \"\"\"Count open (not done) tasks per priority.\"\"\"\n"
        "        counts = {p.value: 0 for p in Priority}\n"
        "        for t in self._tasks.values():\n"
        "            if not t.done:\n"
        "                counts[t.priority.value] += 1\n"
        "        return counts\n"
        ">>>>>>> REPLACE\n"
    )
