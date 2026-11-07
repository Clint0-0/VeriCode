"""MOCK LLM PROVIDER - scripted, deterministic, DEMO/TEST ONLY.

It does not reason or generate code. It recognises the two bundled demo tasks and returns canned
responses that *react to context* the way a model with Pydantic-v1-era knowledge would: it emits
v1-style API calls unless the prompt contains the corrected API (from a VeriCode pre-flight briefing
or from a test-failure message). Every token count produced through it is an ESTIMATE (chars/4).
Any other task returns an explicit "no script" error so it can never masquerade as a real model.
"""
from __future__ import annotations

import json

NO_SCRIPT = ("MOCK_PROVIDER_NO_SCRIPT: the offline MOCK provider is scripted and cannot solve arbitrary tasks. "
             "It supports only the bundled demo tasks: 'users' (Pydantic User model, sample_project), 'summary' "
             "(TaskStore.priority_summary, sample_project) and 'signup' (zod schema, ts_project) - pick them in "
             "Coding Workspace > Demo task or run scripts/demo.sh a|b|3. For any other task configure a real provider: "
             "ANTHROPIC_API_KEY or OPENAI_API_KEY plus VERICODE_CODER_MODEL in .env.")


def _task_kind(prompt: str) -> str | None:
    head = prompt.split("TASK:", 1)[-1][:800].lower()
    if "signup" in head and "zod" in head:
        return "signup"
    if "user" in head and "username" in head:
        return "users"
    if "priority_summary" in head:
        return "summary"
    if "signup" in head and "zod" in head:
        return "signup"
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
        if kind == "signup":
            return json.dumps({"packages": [{
                "package": "zod", "ecosystem": "node", "installed_version": None, "assumed_version": "3.20",
                "planned_apis": [
                    {"import_path": "zod", "name": "z", "type": "attribute", "arguments": [], "purpose": "schema builder namespace"},
                    {"import_path": "zod", "name": "ZodString.nonempty", "type": "method", "arguments": [], "purpose": "username required", "version_sensitive": True},
                    {"import_path": "zod", "name": "ZodString.min", "type": "method", "arguments": ["\"3\""], "purpose": "username length", "version_sensitive": True},
                    {"import_path": "zod", "name": "ZodString.email", "type": "method", "arguments": [], "purpose": "email format"},
                ]}], "notes": "zod schema"})
        return NO_SCRIPT
    if stage in ("coder", "repair"):
        if kind == "users":
            return _users_code(prompt)
        if kind == "summary":
            return _summary_code()
        if kind == "signup":
            return _signup_code(prompt)
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


def _signup_code(prompt: str) -> str:
    # an LLM with older zod habits writes .nonempty() and min("3") unless told otherwise
    fixed_min = "TS2345" in prompt or "minLength: number" in prompt
    fixed_nonempty = "min(1) instead" in prompt or "nonempty" in prompt and "deprecated" in prompt.lower()
    username = "z.string()" + (".min(1)" if fixed_nonempty else ".nonempty()") + (".min(3)" if fixed_min else '.min("3")')
    code = (
        "import { z } from 'zod'\n\n"
        "export const Signup = z.object({\n"
        f"  username: {username},\n"
        "  email: z.string().email(),\n"
        "})\n\n"
        "export type Signup = z.infer<typeof Signup>\n"
    )
    cur_marker = "CURRENT CONTENT OF src/signup.ts:\n"
    if cur_marker in prompt:
        cur = prompt.split(cur_marker, 1)[1].split("\n<<<END FILE>>>", 1)[0]
        return "Updating signup schema.\n\nFILE: src/signup.ts\n<<<<<<< SEARCH\n" + cur + "\n=======\n" + code + ">>>>>>> REPLACE\n"
    return "Adding signup schema.\n\nFILE: src/signup.ts\n<<<<<<< SEARCH\n=======\n" + code + ">>>>>>> REPLACE\n"
