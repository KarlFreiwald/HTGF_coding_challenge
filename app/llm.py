"""Small provider boundary: interview code depends on text messages, not an SDK."""

import os
from dataclasses import dataclass, field
from typing import Protocol

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI


@dataclass(frozen=True)
class ModelOption:
    label: str
    provider: str
    api_model: str
    options: dict = field(default_factory=dict)


# This allowlist is also the source of the UI dropdown. Check parameter support
# and account access before adding a model; never silently substitute one.
MODELS = {
    "gpt-5.4-mini": ModelOption("GPT-5.4 mini", "openai", "gpt-5.4-mini", {"reasoning": {"effort": "none"}}),
    "gpt-5.4": ModelOption("GPT-5.4", "openai", "gpt-5.4", {"reasoning": {"effort": "none"}}),
}
DEFAULT_MODEL = "gpt-5.4-mini"


class ReplyError(Exception):
    """Safe, actionable text that can be shown in the browser."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class TextProvider(Protocol):
    async def reply(self, model: ModelOption, instructions: str, messages: list[dict[str, str]]) -> str: ...


class OpenAIProvider:
    async def reply(self, model: ModelOption, instructions: str, messages: list[dict[str, str]]) -> str:
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise ReplyError("Add OPENAI_API_KEY to .env and recreate the container to enable interview replies.", 503)
        try:
            # No automatic retries: avoid hidden delays and repeat paid requests.
            async with AsyncOpenAI(api_key=key, timeout=25.0, max_retries=0) as client:
                response = await client.responses.create(
                    model=model.api_model,
                    instructions=instructions,
                    input=messages,
                    store=False,
                    max_output_tokens=500,
                    **model.options,
                )
        except APITimeoutError:
            raise ReplyError("The model took too long to respond. Start a new recording to try again.", 504) from None
        except APIConnectionError:
            raise ReplyError("Could not reach OpenAI. Check the connection and try a new recording.") from None
        except APIStatusError as error:
            if error.status_code == 401:
                message = "OpenAI rejected the API key. Check OPENAI_API_KEY in .env."
            elif error.status_code in (403, 404):
                message = "This OpenAI model is unavailable to this API project. Check access or select another model."
            elif error.status_code == 429:
                message = "OpenAI reported a quota or rate limit. Check API credits and usage limits."
            else:
                message = "OpenAI could not generate a reply. Try a new recording."
            raise ReplyError(message) from None
        text = response.output_text.strip()
        if response.status != "completed" or not text:
            raise ReplyError("The model returned an incomplete or empty reply. Try a new recording.")
        return text


PROVIDERS: dict[str, TextProvider] = {"openai": OpenAIProvider()}
