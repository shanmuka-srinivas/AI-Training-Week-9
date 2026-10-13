"""
One place that talks to the AI model. Both the agent and the fixed workflow use
it, so the race compares the two approaches rather than two ways of calling a model.

TWO BACKENDS, chosen with the AGENT_LLM environment variable:

    AGENT_LLM=local    (default) Qwen2.5-3B-Instruct (quantised) on this computer's
                       CPU. Free, offline, no quota. Slower, and a smaller model.
    AGENT_LLM=gemini   Google's gemini-2.5-flash-lite. Fast and sharper, but the
                       free tier allows only 20 calls a day, so a full race needs
                       a paid key.

Both return exactly the same thing, so nothing else in the project changes.

Every call is measured: seconds, input tokens, output tokens and dollars. Those
numbers are the "speed" and "cost" columns of the race.
"""

import json
import os
import time

BACKEND = os.environ.get("AGENT_LLM", "local").lower()

GEMINI_MODEL = "gemini-2.5-flash-lite"

# Price per 1 million tokens, in US dollars. These are the published list prices
# for this model at the time of writing. If Google changes them, change these two
# numbers and the cost column updates; nothing else depends on them.
PRICE_PER_M_INPUT = 0.10
PRICE_PER_M_OUTPUT = 0.40

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client()
    return _client


class LLMError(Exception):
    pass


def call_json(prompt, temperature=0.0):
    """Send one prompt to whichever backend is selected."""
    if BACKEND == "local":
        from . import llm_local

        return llm_local.call_json(prompt, temperature)
    return _call_gemini(prompt, temperature)


def model_name():
    if BACKEND == "local":
        from . import llm_local

        return llm_local.MODEL_NAME
    return GEMINI_MODEL


def _call_gemini(prompt, temperature=0.0):
    """
    Send one prompt, get back one JSON object plus the call's measurements.

    Returns (parsed_json_or_None, raw_text, usage) where usage is
    {"seconds", "input_tokens", "output_tokens", "cost_usd"}.
    A reply that isn't valid JSON comes back as parsed=None rather than
    crashing, so the caller can decide what to do (the agent tells the model
    and lets it try again, within its budget).
    """
    from google.genai import types

    if isinstance(prompt, list):
        prompt = "\n\n".join(f"[{m['role']}] {m['content']}" for m in prompt)
    client = _get_client()
    started = time.perf_counter()
    for attempt in range(4):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            break
        except Exception as error:
            text = str(error)
            if "free_tier" in text and "PerDay" in text:
                raise LLMError(
                    "Gemini free-tier daily limit reached. Billing does not seem to be enabled "
                    "for this API key's Google project yet."
                ) from error
            if attempt == 3:
                raise LLMError(text[:300]) from error
            time.sleep(3 * (attempt + 1))

    seconds = time.perf_counter() - started
    meta = response.usage_metadata
    input_tokens = meta.prompt_token_count or 0
    output_tokens = (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
    usage = {
        "seconds": seconds,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": input_tokens / 1e6 * PRICE_PER_M_INPUT + output_tokens / 1e6 * PRICE_PER_M_OUTPUT,
    }

    raw = response.text or ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            parsed = parsed[0]   # the model occasionally wraps the object in a list
        if not isinstance(parsed, dict):
            parsed = None
    except json.JSONDecodeError:
        parsed = None
    return parsed, raw, usage
