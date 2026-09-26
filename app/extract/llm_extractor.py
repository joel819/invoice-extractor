"""LLM extractor: Llama 3.3 70B on Groq, JSON mode, validated against the Pydantic schema.
If the JSON fails validation, the model gets one chance to repair it with the exact errors."""
import json

import openai
from pydantic import ValidationError

from app.config import Settings
from app.errors import ExtractionFailed
from app.extract.prompts import SYSTEM_PROMPT, repair_prompt, user_prompt
from app.schemas.invoice import Invoice

MAX_TEXT_CHARS = 30_000


class LLMUnavailable(Exception):
    """Network/API failure; the caller falls back to the rule extractor."""


def _errors(exc: ValidationError) -> list[dict]:
    return [{"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]} for e in exc.errors()]


class GroqExtractor:
    name = "groq"

    def __init__(self, settings: Settings):
        self.model = settings.groq_model
        self.repair_attempts = settings.llm_repair_attempts
        self.client = openai.OpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    def _ask(self, messages: list[dict]) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except openai.OpenAIError as exc:
            raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc
        content = resp.choices[0].message.content if resp.choices else None
        if not content:
            raise LLMUnavailable("Empty response from model")
        return content

    def extract(self, text: str) -> tuple[Invoice, list[str]]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(text[:MAX_TEXT_CHARS])},
        ]
        details: list[dict] = []
        for attempt in range(1 + self.repair_attempts):
            content = self._ask(messages)
            try:
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError("top level is not an object")
            except ValueError as exc:
                details = [{"field": "(json)", "problem": f"invalid JSON: {exc}"}]
            else:
                if data.get("not_invoice"):
                    raise ExtractionFailed(str(data.get("reason") or "The document is not an invoice."),
                                           not_invoice=True)
                try:
                    invoice = Invoice.model_validate(data.get("invoice", data))
                    uncertain = [str(f) for f in data.get("uncertain_fields") or []][:50]
                    return invoice, uncertain
                except ValidationError as exc:
                    details = _errors(exc)
            messages += [{"role": "assistant", "content": content},
                         {"role": "user", "content": repair_prompt(details)}]
        raise ExtractionFailed("The model's output did not pass schema validation.", details)
