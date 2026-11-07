"""Environment-based configuration. Secrets are read from env only and never returned to clients."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Category half-lives in days for evidence freshness: Freshness = 100 * 2^(-age_days / half_life)
DEFAULT_HALF_LIVES: dict[str, float] = {
    "software_version": 90,
    "api_documentation": 180,
    "pricing": 60,
    "leadership": 365,
    "law_regulation": 365,
    "product_spec": 180,
    "release_date": 365,
    "deadline": 30,
    "current_events": 14,
    "other_volatile": 180,
    "stable": 3650,
}


# Category -> domains treated as primary sources (configurable in Settings, persisted).
DEFAULT_AUTHORITY_RULES: dict[str, list[str]] = {
    "law_regulation": [".gov", ".gov.uk", ".gov.in", "europa.eu", "eur-lex.europa.eu", "legislation.gov.uk", ".gouv.fr"],
    "software_version": ["python.org", "nodejs.org", "github.com", "pypi.org", "npmjs.com", "go.dev", "rust-lang.org"],
    "api_documentation": ["docs.python.org", "developer.mozilla.org", "fastapi.tiangolo.com", "docs.pydantic.dev", "react.dev"],
    "pricing": [], "leadership": [], "product_spec": [], "release_date": [], "deadline": [".gov"],
    "current_events": [], "other_volatile": [],
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _load_dotenv() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: _env("VERICODE_DB", str(ROOT / "vericode.db")))
    workspaces_root: str = field(default_factory=lambda: _env("VERICODE_WORKSPACES", str(ROOT / "demos")))
    # LLM provider: "anthropic", "openai" (OpenAI-compatible), or "mock" (scripted, demo only)
    llm_provider: str = field(default_factory=lambda: _env("VERICODE_LLM_PROVIDER", ""))
    planner_model: str = field(default_factory=lambda: _env("VERICODE_PLANNER_MODEL", ""))
    coder_model: str = field(default_factory=lambda: _env("VERICODE_CODER_MODEL", ""))
    openai_base_url: str = field(default_factory=lambda: _env("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    anthropic_base_url: str = field(default_factory=lambda: _env("VERICODE_ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
    tavily_timeout: float = field(default_factory=lambda: float(_env("TAVILY_TIMEOUT", "20")))
    tavily_max_retries: int = field(default_factory=lambda: int(_env("TAVILY_MAX_RETRIES", "2")))
    max_repair_attempts: int = field(default_factory=lambda: int(_env("VERICODE_MAX_REPAIRS", "3")))
    command_timeout: int = field(default_factory=lambda: int(_env("VERICODE_COMMAND_TIMEOUT", "120")))
    cache_ttl_seconds: int = field(default_factory=lambda: int(_env("VERICODE_CACHE_TTL", "86400")))
    demo_mode: bool = field(default_factory=lambda: _env("VERICODE_DEMO_MODE", "1") == "1")
    half_lives: dict = field(default_factory=lambda: dict(DEFAULT_HALF_LIVES))
    # cost per 1M tokens (USD), user-configurable, used only for display
    cost_input_per_mtok: float = field(default_factory=lambda: float(_env("VERICODE_COST_IN", "3.0")))
    cost_output_per_mtok: float = field(default_factory=lambda: float(_env("VERICODE_COST_OUT", "15.0")))
    # per-model USD price per 1M tokens: {"model-id": {"input": 3.0, "output": 15.0}} (user-maintained; no prices are invented)
    model_prices: dict = field(default_factory=dict)
    # sandbox: auto (docker if daemon reachable, else process), docker, process
    sandbox_backend: str = field(default_factory=lambda: _env("VERICODE_SANDBOX", "auto"))
    sandbox_memory: str = field(default_factory=lambda: _env("VERICODE_SANDBOX_MEMORY", "1g"))
    sandbox_image: str = field(default_factory=lambda: _env("VERICODE_SANDBOX_IMAGE", "vericode-sandbox:full"))
    sandbox_cpus: str = field(default_factory=lambda: _env("VERICODE_SANDBOX_CPUS", "1"))
    # LLM evidence judge for claims without concrete values (only with a real provider)
    use_llm_judge: bool = field(default_factory=lambda: _env("VERICODE_LLM_JUDGE", "1") == "1")
    live_search_default: bool = True
    tavily_search_depth: str = field(default_factory=lambda: _env("TAVILY_SEARCH_DEPTH", "basic"))
    default_workspace: str = "sample_project"
    authority_rules: dict = field(default_factory=lambda: dict(DEFAULT_AUTHORITY_RULES))
    trusted_registry: dict = field(default_factory=dict)  # user additions to source_authority.DEFAULT_TRUSTED_REGISTRY
    # network exposure / auth
    host: str = field(default_factory=lambda: _env("VERICODE_HOST", "127.0.0.1"))
    allow_remote: bool = field(default_factory=lambda: _env("VERICODE_ALLOW_REMOTE", "0") == "1")
    llm_stream: bool = field(default_factory=lambda: _env("VERICODE_LLM_STREAM", "1") == "1")
    llm_timeout: float = field(default_factory=lambda: float(_env("VERICODE_LLM_TIMEOUT", "180")))

    @property
    def tavily_api_key(self) -> str:
        return _env("TAVILY_API_KEY")

    @property
    def anthropic_api_key(self) -> str:
        return _env("ANTHROPIC_API_KEY")

    @property
    def openai_api_key(self) -> str:
        return _env("OPENAI_API_KEY")

    def effective_provider(self) -> str:
        if self.llm_provider:
            return self.llm_provider
        if self.anthropic_api_key:
            return "anthropic"
        if self.openai_api_key:
            return "openai"
        return "mock" if self.demo_mode else "none"

    def public_dict(self) -> dict:
        """Settings safe to send to the browser: secret values are replaced by presence flags."""
        return {
            "llm_provider": self.effective_provider(),
            "planner_model": self.planner_model,
            "coder_model": self.coder_model,
            "search_provider": "tavily",
            "tavily_configured": bool(self.tavily_api_key),
            "anthropic_configured": bool(self.anthropic_api_key),
            "openai_configured": bool(self.openai_api_key),
            "workspaces_root": self.workspaces_root,
            "max_repair_attempts": self.max_repair_attempts,
            "command_timeout": self.command_timeout,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "tavily_timeout": self.tavily_timeout,
            "tavily_max_retries": self.tavily_max_retries,
            "demo_mode": self.demo_mode,
            "half_lives": self.half_lives,
            "cost_input_per_mtok": self.cost_input_per_mtok,
            "cost_output_per_mtok": self.cost_output_per_mtok,
            "sandbox_backend": self.sandbox_backend,
            "use_llm_judge": self.use_llm_judge,
            "live_search_default": self.live_search_default,
            "tavily_search_depth": self.tavily_search_depth,
            "default_workspace": self.default_workspace,
            "authority_rules": self.authority_rules,
            "trusted_registry": self.trusted_registry,
            "model_prices": self.model_prices,
            "llm_stream": self.llm_stream,
            "host": self.host,
            "allow_remote": self.allow_remote,
            "openai_base_url": self.openai_base_url,
        }

    EDITABLE = {
        "planner_model": str, "coder_model": str, "max_repair_attempts": int, "command_timeout": int,
        "cache_ttl_seconds": int, "tavily_timeout": float, "tavily_max_retries": int,
        "cost_input_per_mtok": float, "cost_output_per_mtok": float, "llm_provider": str,
        "sandbox_backend": str, "use_llm_judge": bool, "live_search_default": bool, "tavily_search_depth": str,
        "default_workspace": str, "llm_stream": bool,
    }

    def load_persisted(self) -> None:
        """Apply settings saved in SQLite (non-secret values only)."""
        from . import db
        for r in db.rows("SELECT key, value FROM settings"):
            try:
                self.update({r["key"]: db.loads(r["value"])}, persist=False)
            except (ValueError, TypeError):
                continue

    def update(self, data: dict, persist: bool = True) -> None:
        for k, v in data.items():
            if k in self.EDITABLE:
                if k == "llm_provider" and v not in ("", "anthropic", "openai", "mock"):
                    raise ValueError("invalid provider")
                if k == "sandbox_backend" and v not in ("auto", "docker", "process"):
                    raise ValueError("invalid sandbox backend")
                if k == "tavily_search_depth" and v not in ("basic", "advanced", "fast", "ultra-fast"):
                    raise ValueError("invalid search depth")
                if k in ("max_repair_attempts",) and not 0 <= int(v) <= 5:
                    raise ValueError("max_repair_attempts must be 0-5")
                cast = self.EDITABLE[k]
                if cast is bool:
                    v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
                setattr(self, k, cast(v))
            elif k == "half_lives" and isinstance(v, dict):
                for cat, days in v.items():
                    if cat in self.half_lives and float(days) > 0:
                        self.half_lives[cat] = float(days)
            elif k == "model_prices" and isinstance(v, dict):
                self.model_prices = {str(m): {"input": float(p.get("input", 0)), "output": float(p.get("output", 0))}
                                     for m, p in v.items() if isinstance(p, dict)}
            elif k == "trusted_registry" and isinstance(v, dict):
                self.trusted_registry = {str(c): [str(d).lower() for d in ds][:100] for c, ds in v.items() if isinstance(ds, list)}
            elif k == "authority_rules" and isinstance(v, dict):
                self.authority_rules = {str(c): [str(d).lower() for d in ds][:50] for c, ds in v.items() if isinstance(ds, list)}
            else:
                continue
            if persist:
                from . import db
                with db.tx() as c:
                    c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES(?,?,strftime('%s','now'))",
                              (k, db.dumps(getattr(self, k)), ))


settings = Settings()
