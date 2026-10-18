"""
TRIAGE — DeepSeek AI Hospital Handover Note Generator (Chunk 5)

Implements CONTEXT.md Section 6.7 (Handover notes):
  - `NoteFacts` dataclass holding structured, de-identified patient & routing data.
  - `NoteGenerator` class with:
      1. `_generate_template(facts: NoteFacts) -> str`: Clean 2-sentence fallback.
      2. `async generate(facts: NoteFacts) -> str`: Calls OpenRouter (`deepseek/deepseek-chat`
         or `LLM_MODEL` from env) using `httpx.AsyncClient` with a strict 4.0-second timeout,
         in-memory caching, and numeric hallucination validation. Automatically falls back
         to `_generate_template(facts)` if the API key is missing, times out, or fails.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Any

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE_PATH = PROJECT_ROOT / ".env"

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_LLM_MODEL = "deepseek/deepseek-chat"
STRICT_TIMEOUT_SECONDS = 4.0

SYSTEM_PROMPT = (
    "Write at most 40 words for a hospital reception team. "
    "Use only the facts given. Do not add clinical facts."
)


def _load_dotenv_if_present(dotenv_path: Path = ENV_FILE_PATH) -> None:
    """
    Lightweight, zero-dependency .env loader so `os.getenv("OPENROUTER_API_KEY")`
    works out-of-the-box whether run via CLI or uvicorn.
    Does not overwrite environment variables that are already set.
    """
    if not dotenv_path.exists():
        return
    try:
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            # Strip inline comments and surrounding quotes
            val = val.split("#", 1)[0].strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        # Never crash if .env has formatting quirks
        pass


@dataclass
class NoteFacts:
    """
    Structured, de-identified clinical and routing facts passed to the handover
    note generator (CONTEXT.md Section 6.7).
    """

    age: int
    sex: str
    condition_name: str
    severity_s0: float
    deterioration_rate: float
    category: int
    hospital_name: str
    eta_minutes: int
    special_needs: str = "Standard ED bay needed"
    patient_id: str = "p_unknown"
    vitals_summary: str = ""

    def cache_key(self) -> tuple[str, str, int]:
        """Cache key per CONTEXT.md Section 6.7: (patient_id, hospital_name, ETA rounded to minute)."""
        return (self.patient_id, self.hospital_name, int(round(self.eta_minutes)))


class NoteGenerator:
    """
    Generates concise hospital reception pre-alert notes using DeepSeek via OpenRouter
    with an instant, deterministic 2-sentence template fallback.
    """

    def __init__(self, timeout_s: float = STRICT_TIMEOUT_SECONDS) -> None:
        self.timeout_s: float = float(timeout_s)
        self._cache: dict[tuple[str, str, int], str] = {}

    def _generate_template(self, facts: NoteFacts) -> str:
        """
        Deterministic 2-sentence fallback method combining the raw facts.
        Always succeeds in < 1 millisecond with zero network dependency.
        """
        sex_norm = str(facts.sex).strip().upper()
        if sex_norm == "F" or sex_norm.startswith("FEM"):
            sex_word = "female"
        elif sex_norm == "M" or sex_norm.startswith("MAL"):
            sex_word = "male"
        else:
            sex_word = str(facts.sex).strip().lower() or "patient"

        needs_clean = str(facts.special_needs).strip().rstrip(".")
        if not needs_clean:
            needs_clean = "Standard ED bay required"

        vitals_clause = f" ({facts.vitals_summary})" if facts.vitals_summary else ""

        sentence_1 = (
            f"Incoming Category {facts.category} alert: {facts.age}-year-old {sex_word} "
            f"with suspected {facts.condition_name}{vitals_clause}, severity {facts.severity_s0:.1f}/100 "
            f"and deteriorating at +{facts.deterioration_rate:.1f}/min."
        )
        sentence_2 = (
            f"ETA {int(round(facts.eta_minutes))} min to {facts.hospital_name}; "
            f"{needs_clean}."
        )
        return f"{sentence_1} {sentence_2}"

    def _build_user_prompt(self, facts: NoteFacts) -> str:
        """Format the exact facts for the LLM prompt."""
        sex_label = "female" if str(facts.sex).upper().startswith("F") else "male"
        lines = [
            "Write at most 40 words for a hospital reception team. Use only the facts given. Do not add clinical facts.",
            "",
            "Facts:",
            f"- Patient: {facts.age}-year-old {sex_label}",
            f"- Suspected condition: {facts.condition_name}",
            f"- Response Category: Category {facts.category}",
            f"- Current severity score: {facts.severity_s0:.1f}",
            f"- Deterioration rate: {facts.deterioration_rate:.1f} per minute",
            f"- Destination hospital: {facts.hospital_name}",
            f"- ETA: {int(round(facts.eta_minutes))} minutes",
            f"- Special preparation needed: {facts.special_needs}",
        ]
        if facts.vitals_summary:
            lines.append(f"- Vitals: {facts.vitals_summary}")
        return "\n".join(lines)

    @staticmethod
    def _validate_llm_output(text: str, facts: NoteFacts) -> bool:
        """
        Verify the LLM output is non-empty, reasonably concise, and does not
        invent ungrounded numbers (CONTEXT.md Section 6.7 validation guard).
        """
        cleaned = text.strip()
        if not cleaned:
            return False

        # Allow a tiny buffer over 40 words for hyphenated terms, reject rambling responses
        words = cleaned.split()
        if len(words) > 52:
            return False

        # Collect all allowed numeric values from NoteFacts (both exact and rounded ints)
        allowed_numbers: set[float] = {
            float(facts.age),
            float(facts.category),
            round(float(facts.severity_s0), 1),
            float(int(round(facts.severity_s0))),
            round(float(facts.deterioration_rate), 2),
            round(float(facts.deterioration_rate), 1),
            float(int(round(facts.deterioration_rate))),
            float(int(round(facts.eta_minutes))),
            100.0,  # e.g., "72.0/100"
        }
        # Also include any numbers present in vitals_summary
        for num_str in re.findall(r"\d+(?:\.\d+)?", facts.vitals_summary or ""):
            try:
                allowed_numbers.add(float(num_str))
            except ValueError:
                pass

        # Check every number in the LLM response against allowed_numbers
        extracted_numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)
        for num_str in extracted_numbers:
            try:
                val = float(num_str)
                if not any(abs(val - allowed) < 0.15 for allowed in allowed_numbers):
                    return False
            except ValueError:
                return False

        return True

    async def generate(self, facts: NoteFacts) -> str:
        """
        Asynchronously generate a handover note using OpenRouter (`deepseek/deepseek-chat`).
        - Reads `OPENROUTER_API_KEY` and `LLM_MODEL` from the environment (`os.getenv`).
        - Enforces a strict 4.0-second timeout via `httpx.AsyncClient`.
        - Immediately falls back to `_generate_template(facts)` on missing key, timeout,
          HTTP error, or validation failure.
        """
        ck = facts.cache_key()
        if ck in self._cache:
            return self._cache[ck]

        # Ensure .env is loaded if present on disk
        _load_dotenv_if_present()

        api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        model_id = (os.getenv("LLM_MODEL") or DEFAULT_LLM_MODEL).strip()
        llm_enabled = (os.getenv("LLM_ENABLED", "true")).strip().lower() not in (
            "false",
            "0",
            "no",
        )

        if not api_key or not llm_enabled:
            fallback_note = self._generate_template(facts)
            self._cache[ck] = fallback_note
            return fallback_note

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/w-sung/IBMZ_TRIAGE",
            "X-Title": "TRIAGE - IBM Z Datathon 2026",
        }

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._build_user_prompt(facts)},
            ],
            "temperature": 0.1,
            "max_tokens": 90,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(
                    OPENROUTER_ENDPOINT,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            choices = data.get("choices", [])
            if not choices:
                raise ValueError("OpenRouter returned empty choices list.")

            content = (
                choices[0]
                .get("message", {})
                .get("content", "")
                .strip()
                .replace("\n", " ")
            )

            if not self._validate_llm_output(content, facts):
                raise ValueError("LLM output failed numeric or length validation guard.")

            self._cache[ck] = content
            return content

        except Exception:
            # Any network issue, timeout, 401/429 error, or validation mismatch
            # immediately returns the deterministic 2-sentence template.
            fallback_note = self._generate_template(facts)
            self._cache[ck] = fallback_note
            return fallback_note


if __name__ == "__main__":
    async def _self_test() -> None:
        dummy_facts = NoteFacts(
            patient_id="p_017",
            age=68,
            sex="F",
            condition_name="Heart attack (STEMI)",
            severity_s0=72.4,
            deterioration_rate=1.2,
            category=2,
            hospital_name="Salford Royal",
            eta_minutes=8,
            special_needs="Cardiac team and cath lab needed",
            vitals_summary="HR 125, SBP 85 mmHg, SpO2 91%",
        )

        print("=" * 76)
        print("TRIAGE — Chunk 5 DeepSeek Handover Note Generator Self-Test")
        print("=" * 76)

        # Load .env first so we can test both modes cleanly
        _load_dotenv_if_present()
        saved_key = os.environ.pop("OPENROUTER_API_KEY", None)

        # Test 1: Prove fallback to _generate_template when no API key is present
        gen_fallback = NoteGenerator(timeout_s=4.0)
        fallback_result = await gen_fallback.generate(dummy_facts)
        print("[Test 1] Fallback Mode (No API Key Present):")
        print(f"  -> {fallback_result}")
        print(f"  -> Word count: {len(fallback_result.split())} words")

        # Test 2: Restore API key (if present in .env or environment) and test live call
        if saved_key:
            os.environ["OPENROUTER_API_KEY"] = saved_key

        active_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        print("-" * 76)
        if active_key:
            gen_live = NoteGenerator(timeout_s=4.0)
            live_result = await gen_live.generate(dummy_facts)
            print(f"[Test 2] Live OpenRouter Mode (model={os.getenv('LLM_MODEL', DEFAULT_LLM_MODEL)}):")
            print(f"  -> {live_result}")
            print(f"  -> Word count: {len(live_result.split())} words")
        else:
            print("[Test 2] Tip: Add OPENROUTER_API_KEY to your .env file to test live DeepSeek notes!")
        print("=" * 76)

    asyncio.run(_self_test())