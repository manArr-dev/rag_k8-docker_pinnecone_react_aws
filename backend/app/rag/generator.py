import logging
from collections.abc import AsyncIterator

import anthropic

from .types import Finished, TextDelta

logger = logging.getLogger(__name__)

_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class GenerationError(Exception):
    """Generation failed; the message is safe to show to the end user."""


class ClaudeGenerator:
    def __init__(
        self,
        *,
        model: str,
        max_tokens: int,
        effort: str,
        refusal_fallback: bool,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        # Credentials come from the environment (ANTHROPIC_API_KEY).
        self._client = client or anthropic.AsyncAnthropic()
        self._model = model
        self._max_tokens = max_tokens
        self._effort = effort
        self._refusal_fallback = refusal_fallback

    async def stream(
        self, system: str, messages: list[dict[str, str]]
    ) -> AsyncIterator[TextDelta | Finished]:
        params = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": messages,
            "output_config": {"effort": self._effort},
        }
        if self._refusal_fallback:
            manager = self._client.beta.messages.stream(
                **params, betas=[_FALLBACK_BETA], fallbacks="default"
            )
        else:
            manager = self._client.messages.stream(**params)

        try:
            async with manager as stream:
                async for text in stream.text_stream:
                    yield TextDelta(text)
                final = await stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            logger.error("Anthropic authentication failed: %s", exc)
            raise GenerationError("The language model is not configured correctly.") from exc
        except anthropic.RateLimitError as exc:
            raise GenerationError("The service is busy. Please try again in a moment.") from exc
        except anthropic.APIStatusError as exc:
            logger.error(
                "Anthropic API error %s (request %s): %s",
                exc.status_code,
                exc.request_id,
                exc.message,
            )
            if exc.status_code >= 500:
                raise GenerationError(
                    "The language model is temporarily unavailable. Please try again."
                ) from exc
            raise GenerationError("The language model rejected the request.") from exc
        except anthropic.APIConnectionError as exc:
            raise GenerationError("Could not reach the language model. Please try again.") from exc

        yield Finished(
            stop_reason=final.stop_reason,
            model=final.model,
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
        )
