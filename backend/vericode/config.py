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
        }

    EDITABLE = {
        "planner_model": str, "coder_model": str, "max_repair_attempts": int, "command_timeout": int,
        "cache_ttl_seconds": int, "tavily_timeout": float, "tavily_max_retries": int,
        "cost_input_per_mtok": float, "cost_output_per_mtok": float, "llm_provider": str,
    }

    def update(self, data: dict) -> None:
        for k, v in data.items():
            if k in self.EDITABLE:
                if k == "llm_provider" and v not in ("", "anthropic", "openai", "mock"):
                    raise ValueError("invalid provider")
                setattr(self, k, self.EDITABLE[k](v))
            elif k == "half_lives" and isinstance(v, dict):
                for cat, days in v.items():
                    if cat in self.half_lives and float(days) > 0:
                        self.half_lives[cat] = float(days)


settings = Settings()
