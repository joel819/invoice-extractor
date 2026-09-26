"""The Groq extractor with the OpenAI client mocked: no key, no network."""
import json
from types import SimpleNamespace

import openai
import pytest

from app import pipeline
from app.config import get_settings
from app.errors import ExtractionFailed
from app.extract.llm_extractor import GroqExtractor, LLMUnavailable
from tests.conftest import sample

GOOD = {
    "invoice": {
        "invoice_number": "AF-2026-0142", "invoice_date": "2026-09-03", "due_date": "2026-10-03", "currency": "EUR",
        "vendor": {"name": "Alder & Finch Design Studio", "address": None, "tax_id": "NL859301762B01",
                   "email": "hello@alderfinch.example"},
        "bill_to": "Kestrel Outdoor Supply B.V.",
        "line_items": [
            {"description": "Brand identity workshop (half day)", "quantity": 1, "unit_price": 1200, "amount": 1200},
            {"description": "Logo design, three concepts", "quantity": 1, "unit_price": 850, "amount": 850},
            {"description": "Business card layout", "quantity": 2, "unit_price": 75, "amount": 150}],
        "totals": {"subtotal": 2200, "discount": 0, "tax": 462, "tax_rate": 21, "total": 2662},
    },
    "uncertain_fields": [],
}


def reply(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class Script:
    def __init__(self, *contents):
        self.contents, self.requests = list(contents), []

    def __call__(self, **kwargs):
        self.requests.append(kwargs)
        c = self.contents.pop(0)
        if isinstance(c, Exception):
            raise c
        return reply(c)


@pytest.fixture
def llm():
    return GroqExtractor(get_settings().model_copy(update={"groq_api_key": "gsk_test"}))


def test_request_uses_groq_json_mode(llm, monkeypatch):
    script = Script(json.dumps(GOOD))
    monkeypatch.setattr(llm.client.chat.completions, "create", script)
    inv, unc = llm.extract("invoice text")
    req = script.requests[0]
    assert req["model"] == "llama-3.3-70b-versatile" and req["response_format"] == {"type": "json_object"}
    assert str(llm.client.base_url).startswith("https://api.groq.com/openai/v1")
    assert inv.totals.total == 2662 and unc == []


def test_invalid_json_is_repaired(llm, monkeypatch):
    script = Script("{not json", json.dumps(GOOD))
    monkeypatch.setattr(llm.client.chat.completions, "create", script)
    llm.extract("text")
    assert "invalid JSON" in script.requests[1]["messages"][-1]["content"]


def test_schema_errors_are_sent_back_for_repair(llm, monkeypatch):
    bad = json.loads(json.dumps(GOOD))
    bad["invoice"]["currency"] = "Euros"
    script = Script(json.dumps(bad), json.dumps(GOOD))
    monkeypatch.setattr(llm.client.chat.completions, "create", script)
    inv, _ = llm.extract("text")
    assert inv.currency == "EUR"
    assert "currency" in script.requests[1]["messages"][-1]["content"]


def test_gives_up_after_repair_attempts(llm, monkeypatch):
    monkeypatch.setattr(llm.client.chat.completions, "create", Script("{}", "{}"))
    with pytest.raises(ExtractionFailed) as exc:
        llm.extract("text")
    assert exc.value.details and not exc.value.not_invoice


def test_not_an_invoice(llm, monkeypatch):
    monkeypatch.setattr(llm.client.chat.completions, "create",
                        Script(json.dumps({"not_invoice": True, "reason": "It is a restaurant menu."})))
    with pytest.raises(ExtractionFailed, match="restaurant menu") as exc:
        llm.extract("text")
    assert exc.value.not_invoice


def test_api_error_raises_unavailable(llm, monkeypatch):
    monkeypatch.setattr(llm.client.chat.completions, "create", Script(openai.APIConnectionError(request=None)))
    with pytest.raises(LLMUnavailable):
        llm.extract("text")


def test_pipeline_uses_llm_then_falls_back(post, llm, monkeypatch):
    monkeypatch.setattr(pipeline, "get_llm_extractor", lambda: llm)
    monkeypatch.setattr(llm.client.chat.completions, "create", Script(json.dumps(GOOD)))
    assert post(sample("01-clean-simple.pdf")).json()["mode"] == "groq"

    monkeypatch.setattr(llm.client.chat.completions, "create", Script(openai.APIConnectionError(request=None)))
    r = post(sample("01-clean-simple.pdf")).json()
    assert r["mode"] == "fallback" and r["invoice"]["totals"]["total"] == "2662.00"


def test_llm_hallucination_is_caught_by_confidence(post, llm, monkeypatch):
    fake = json.loads(json.dumps(GOOD))
    fake["invoice"]["vendor"]["name"] = "Invented Company GmbH"
    monkeypatch.setattr(pipeline, "get_llm_extractor", lambda: llm)
    monkeypatch.setattr(llm.client.chat.completions, "create", Script(json.dumps(fake)))
    r = post(sample("01-clean-simple.pdf")).json()
    assert r["status"] == "needs_review" and "vendor.name" in r["low_confidence_fields"]
