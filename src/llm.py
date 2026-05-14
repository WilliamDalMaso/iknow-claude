"""OpenAI router with retries, cost tracking, JSON validation, prompt loading.

All LLM and embedding calls in the project go through this module.

Key entry points:
  - get_router(): builds an LLMRouter from config/models.yaml
  - LLMRouter.chat_json(prompt_name, variables, model_role, ...): renders a prompt
    file with {var} substitutions, calls the model, validates JSON, returns dict
  - LLMRouter.embed(texts, ...): batch-embeds a list of strings
  - LLMRouter.totals(): cost + token totals for the session
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml
from dotenv import load_dotenv

from .artifacts import CONFIG_DIR, PROMPTS_DIR


# Load .env once on import so callers don't have to.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


def load_models_config() -> dict:
    with open(CONFIG_DIR / "models.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class CostCapExceeded(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    in_tokens: int = 0
    out_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0


@dataclass
class LLMRouter:
    config: dict
    client: Any  # openai.OpenAI
    usage: dict[str, Usage] = field(default_factory=dict)
    on_call: Callable[[dict], None] | None = None  # called after each call with a dict log row

    # ---- prompt rendering ----------------------------------------------------

    def render_prompt(self, name: str, variables: dict[str, Any], lessons_block: str = "(none yet)") -> str:
        text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
        # Inject lessons.
        text = text.replace("{lessons}", lessons_block)
        # Substitute {var} placeholders. We use a regex that ignores JSON braces.
        def sub(m: re.Match) -> str:
            key = m.group(1)
            if key not in variables:
                return m.group(0)  # leave alone
            v = variables[key]
            if isinstance(v, (dict, list)):
                return json.dumps(v, ensure_ascii=False)
            return str(v)
        # Match {identifier} only — never {{...}} (json examples).
        text = re.sub(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})", sub, text)
        return text

    # ---- chat (JSON) ---------------------------------------------------------

    def chat_json(
        self,
        prompt_name: str,
        variables: dict[str, Any],
        *,
        model_role: str,
        lessons: list[str] | None = None,
        system: str | None = None,
        max_output_tokens: int | None = None,
    ) -> tuple[dict, Usage]:
        from .memory import format_lessons_block  # local import to avoid cycle

        model_cfg = self.config["models"][model_role]
        model_name = model_cfg["name"]
        temperature = model_cfg.get("temperature", 0.0)
        max_retries = model_cfg.get("max_retries", 3)

        lessons_block = format_lessons_block(lessons or [])
        user_msg = self.render_prompt(prompt_name, variables, lessons_block=lessons_block)
        sys_msg = system or "You are a precise assistant. Respond with valid JSON only."

        last_err: Exception | None = None
        for attempt in range(1, max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = self.client.chat.completions.create(
                    model=model_name,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=max_output_tokens,
                )
                content = resp.choices[0].message.content or ""
                data = self._parse_json_strict(content)
                u = self._record_usage(model_name, resp.usage)
                ms = int((time.perf_counter() - t0) * 1000)
                if self.on_call:
                    self.on_call({
                        "kind": "chat", "prompt": prompt_name, "model": model_name,
                        "ms": ms, "tokens": {"in": u.in_tokens, "out": u.out_tokens},
                        "cost_usd": u.cost_usd, "attempt": attempt,
                    })
                self._maybe_block_on_cost()
                return data, u
            except Exception as e:
                last_err = e
                # Backoff and retry. JSON parse failure also retries.
                if attempt >= max_retries:
                    break
                time.sleep(min(2 ** attempt, 10))
        raise LLMError(f"chat_json failed after {max_retries} attempts for {prompt_name}: {last_err}")

    @staticmethod
    def _parse_json_strict(content: str) -> dict:
        s = content.strip()
        # Strip optional ```json fences.
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*", "", s)
            s = re.sub(r"\s*```$", "", s)
        return json.loads(s)

    # ---- embeddings ----------------------------------------------------------

    def embed(self, texts: list[str], *, model_role: str = "embed") -> list[list[float]]:
        model_cfg = self.config["models"][model_role]
        model_name = model_cfg["name"]
        batch_size = int(model_cfg.get("batch_size", 100))
        max_retries = int(model_cfg.get("max_retries", 3))

        out: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            last_err: Exception | None = None
            for attempt in range(1, max_retries + 1):
                t0 = time.perf_counter()
                try:
                    resp = self.client.embeddings.create(model=model_name, input=batch)
                    for d in resp.data:
                        out.append(d.embedding)
                    u = self._record_usage(model_name, resp.usage, is_embed=True)
                    ms = int((time.perf_counter() - t0) * 1000)
                    if self.on_call:
                        self.on_call({
                            "kind": "embed", "model": model_name, "ms": ms,
                            "tokens": {"in": u.in_tokens, "out": 0},
                            "cost_usd": u.cost_usd, "batch": len(batch),
                        })
                    self._maybe_block_on_cost()
                    break
                except Exception as e:
                    last_err = e
                    if attempt >= max_retries:
                        raise LLMError(f"embed failed after {max_retries} attempts: {e}") from e
                    time.sleep(min(2 ** attempt, 10))
        if len(out) != len(texts):
            raise LLMError(f"embed returned {len(out)} vectors for {len(texts)} inputs")
        return out

    # ---- cost tracking -------------------------------------------------------

    def _record_usage(self, model_name: str, usage_obj, *, is_embed: bool = False) -> Usage:
        in_tok = int(getattr(usage_obj, "prompt_tokens", 0) or getattr(usage_obj, "input_tokens", 0) or 0)
        out_tok = 0 if is_embed else int(getattr(usage_obj, "completion_tokens", 0) or 0)
        pricing = self.config.get("pricing", {}).get(model_name, {})
        in_rate = float(pricing.get("input_per_1m", 0.0))
        out_rate = float(pricing.get("output_per_1m", 0.0))
        cost = (in_tok * in_rate + out_tok * out_rate) / 1_000_000.0
        u = self.usage.setdefault(model_name, Usage())
        u.in_tokens += in_tok
        u.out_tokens += out_tok
        u.cost_usd += cost
        u.calls += 1
        return Usage(in_tokens=in_tok, out_tokens=out_tok, cost_usd=cost, calls=1)

    def total_cost(self) -> float:
        return sum(u.cost_usd for u in self.usage.values())

    def totals(self) -> dict:
        return {
            "cost_usd": round(self.total_cost(), 6),
            "by_model": {m: {"in": u.in_tokens, "out": u.out_tokens,
                              "cost_usd": round(u.cost_usd, 6), "calls": u.calls}
                          for m, u in self.usage.items()},
        }

    def _maybe_block_on_cost(self) -> None:
        block = float(self.config.get("cost_caps", {}).get("per_run_block_usd", 10.0))
        if self.total_cost() > block:
            raise CostCapExceeded(
                f"per-run cost {self.total_cost():.4f} USD exceeded block cap {block:.2f} USD"
            )


def get_router(on_call: Callable[[dict], None] | None = None) -> LLMRouter:
    from openai import OpenAI
    if not os.environ.get("OPENAI_API_KEY"):
        raise LLMError("OPENAI_API_KEY is not set. Copy .env.example to .env and paste your key.")
    return LLMRouter(config=load_models_config(), client=OpenAI(), on_call=on_call)
