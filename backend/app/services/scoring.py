"""Validate the scoring model's output before it is saved.

The model is untrusted, so its text is never saved as-is. We pull the first JSON
object out of the text (so ```json fences or extra prose still parse), then apply
a few hard rules that keep the saved data trustworthy:

- ``score`` must be a whole number 1-5. Anything else is invalid: we never clamp
  or guess a score.
- unknown risk flags are dropped (only allow-listed flags are kept, no duplicates)
  rather than failing the whole answer.
- a missing or empty ``reason`` gets a placeholder so a complete assessment still
  passes the downstream validity check.

If the model call fails, or returns unusable text, we retry it once and then
raise ``ScoringError`` so the caller can return a controlled error.
"""
import json
import math

from . import llm
from .assessment import ALLOWED_RISK_FLAGS

MIN_SCORE = 1
MAX_SCORE = 5
DEFAULT_REASON = "No explanation was returned by the scoring model."
ATTEMPTS = 2  # try once, then retry once


class ScoringError(Exception):
    """The model's raw scoring output is not valid assessment data."""


def _extract_json_object(raw) -> dict:
    """Return the first JSON object found in raw, or raise ScoringError."""
    if not isinstance(raw, str):
        raise ScoringError("scoring model did not return text")
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[index:])
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise ScoringError("scoring model returned no JSON object")


def _valid_score(value) -> int:
    # bool is a subclass of int, so reject it before the numeric check.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScoringError("score must be a whole number between 1 and 5")
    if not math.isfinite(value) or not float(value).is_integer():
        raise ScoringError("score must be a whole number between 1 and 5")
    score = int(value)
    if not MIN_SCORE <= score <= MAX_SCORE:
        raise ScoringError("score must be a whole number between 1 and 5")
    return score


def _clean_flags(value) -> list:
    """Keep only allow-listed flags, drop the rest, and remove duplicates."""
    if not isinstance(value, list):
        return []
    flags = []
    for flag in value:
        if isinstance(flag, str) and flag in ALLOWED_RISK_FLAGS and flag not in flags:
            flags.append(flag)
    return flags


def validate_score(raw) -> dict:
    """Validate one raw model response and return the clean scoring dict."""
    data = _extract_json_object(raw)
    score = _valid_score(data.get("score"))
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = DEFAULT_REASON
    return {"score": score, "reason": reason.strip(), "flags": _clean_flags(data.get("flags"))}


def score_open_answer(question_text: str, answer: str) -> dict:
    """Score one open answer. Retries the model call once, then raises ScoringError."""
    last_error = None
    for _ in range(ATTEMPTS):
        try:
            raw = llm.score_answer(question_text, answer)
            return validate_score(raw)
        except ScoringError as exc:
            last_error = exc
        except Exception as exc:  # model call/timeout/API-envelope failures
            last_error = ScoringError("scoring model call failed")
            last_error.__cause__ = exc
    raise ScoringError("scoring model did not return a valid result after retry") from last_error
