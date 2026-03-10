"""
OpenAI-compatible LLM client.
Works with OpenAI, Groq, OpenRouter, or any compatible endpoint.
Includes retry logic and both JSON and text modes.
"""

import json
import asyncio
import re
from openai import AsyncOpenAI
from backend.config import config


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    json_mode: bool = False,
) -> str:
    """Make a call to the configured LLM provider with retry logic."""

    if not config.is_configured():
        raise ValueError("LLM API key not configured. Please set it in the Settings panel.")

    client = AsyncOpenAI(
        api_key=config.openai_api_key,
        base_url=config.openai_base_url,
    )

    kwargs = {
        "model": config.openai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    # Retry up to 3 times
    last_error = None
    for attempt in range(3):
        try:
            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as e:
            last_error = e
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)

    raise last_error


async def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.4,
    max_tokens: int = 4096,
) -> dict:
    """Make a call to the LLM and parse the response as JSON."""
    raw = await call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
    )
    # Try to parse JSON, handling markdown code blocks
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON in the text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


async def call_llm_text(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.5,
    max_tokens: int = 8192,
) -> str:
    """Make a call to the LLM and return plain text (no JSON parsing).
    Used for longer content like reports where JSON often breaks."""
    return await call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=False,
    )


async def call_llm_chat(
    messages: list[dict],
    temperature: float = 0.6,
    max_tokens: int = 2048,
) -> str:
    """Multi-turn chat with the LLM. Used for notebook chat."""

    if not config.is_configured():
        raise ValueError("LLM API key not configured.")

    client = AsyncOpenAI(
        api_key=config.openai_api_key,
        base_url=config.openai_base_url,
    )

    response = await client.chat.completions.create(
        model=config.openai_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""
