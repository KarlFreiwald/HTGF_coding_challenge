"""Small provider boundary: interview code depends on text messages, not an SDK."""

import os
from dataclasses import dataclass, field
from typing import Protocol

import anthropic
from google import genai
# The pinned SDK's Interactions errors differ from google.genai.errors (used by
# generate_content). Keep this SDK-specific import inside the provider module.
from google.genai import _interactions_errors as gemini_errors
from google.genai import types as genai_types
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
    "claude-haiku-5-5": ModelOption("Claude Haiku 5.5", "anthropic", "claude-haiku-5-5", {
        "thinking": {"type": "disabled"}, "output_config": {"effort": "low"},
    }),
    "gemini-3.8-flash": ModelOption("Gemini 3.8 Flash", "gemini", "gemini-3.8-flash", {
        "generation_config": {"thinking_level": "low", "max_output_tokens": 1024},
    }),
    "gpt-5.4-mini": ModelOption("GPT-5.4 mini", "openai", "gpt-5.4-mini", {"reasoning": {"effort": "none"}}),
    "gpt-5.4": ModelOption("GPT-5.4", "openai", "gpt-5.4", {"reasoning": {"effort": "none"}}),
}
DEFAULT_MODEL = "claude-haiku-5-5"


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


class GeminiProvider:
    async def reply(self, model: ModelOption, instructions: str, messages: list[dict[str, str]]) -> str:
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise ReplyError("Add GEMINI_API_KEY to .env and recreate the container to enable Gemini replies.", 503)
        # Interactions accepts execution steps, rather than OpenAI-style roles.
        steps = [{
            "type": "user_input" if message["role"] == "user" else "model_output",
            "content": [{"type": "text", "text": message["content"]}],
        } for message in messages]
        try:
            with genai.Client(api_key=key, http_options=genai_types.HttpOptions(
                timeout=25000, retry_options=genai_types.HttpRetryOptions(attempts=1),
            )) as owner:
                async with owner.aio as client:
                    response = await client.interactions.create(
                        model=model.api_model,
                        input=steps,
                        system_instruction=instructions,
                        store=False,
                        automatic_continuation=False,
                        **model.options,
                    )
        except gemini_errors.APITimeoutError:
            raise ReplyError("Gemini took too long to respond. Try a new recording.", 504) from None
        except gemini_errors.APIConnectionError:
            raise ReplyError("Could not reach Gemini. Check the connection and try a new recording.") from None
        except gemini_errors.APIStatusError as error:
            if error.status_code in (401, 403):
                message = "Gemini rejected access. Check GEMINI_API_KEY and this API project's permissions."
            elif error.status_code == 404:
                message = "This Gemini model is unavailable to this API project. Check access or select another model."
            elif error.status_code == 429:
                message = "Gemini reported a quota or rate limit. Check API billing and usage limits."
            elif error.status_code == 400:
                message = "Gemini rejected the request. Check the API key and configured model parameters."
            else:
                message = "Gemini could not generate a reply. Try a new recording."
            raise ReplyError(message) from None
        except gemini_errors.APIError:
            raise ReplyError("Gemini returned an unexpected response. Try a new recording.") from None
        text = (response.output_text or "").strip()
        if response.status != "completed" or not text:
            raise ReplyError("Gemini returned an incomplete or empty reply. Try a new recording.")
        return text


class AnthropicProvider:
    async def reply(self, model: ModelOption, instructions: str, messages: list[dict[str, str]]) -> str:
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise ReplyError("Add ANTHROPIC_API_KEY to .env and recreate the container to enable Claude replies.", 503)
        try:
            async with anthropic.AsyncAnthropic(api_key=key, timeout=25.0, max_retries=0) as client:
                response = await client.messages.create(
                    model=model.api_model,
                    system=instructions,
                    messages=messages,
                    max_tokens=500,
                    **model.options,
                )
        except anthropic.APITimeoutError:
            raise ReplyError("Claude took too long to respond. Try a new recording.", 504) from None
        except anthropic.APIConnectionError:
            raise ReplyError("Could not reach Anthropic. Check the connection and try a new recording.") from None
        except anthropic.APIStatusError as error:
            if error.status_code in (401, 403):
                message = "Anthropic rejected access. Check ANTHROPIC_API_KEY and this API project's permissions."
            elif error.status_code == 404:
                message = "This Claude model is unavailable to this API project. Check access or select another model."
            elif error.status_code == 429:
                message = "Anthropic reported a quota or rate limit. Check API billing and usage limits."
            elif error.status_code == 400:
                message = "Anthropic rejected the request. Check API credits and the configured model parameters."
            else:
                message = "Anthropic could not generate a reply. Try a new recording."
            raise ReplyError(message) from None
        except anthropic.APIError:
            raise ReplyError("Anthropic returned an unexpected response. Try a new recording.") from None
        if response.stop_reason == "refusal":
            raise ReplyError("Claude declined this request. Try a new recording with a startup introduction.")
        text = "\n".join(block.text for block in response.content if block.type == "text").strip()
        if response.stop_reason != "end_turn" or not text:
            raise ReplyError("Claude returned an incomplete or empty reply. Try a new recording.")
        return text


PROVIDERS: dict[str, TextProvider] = {
    "openai": OpenAIProvider(), "gemini": GeminiProvider(), "anthropic": AnthropicProvider(),
}
