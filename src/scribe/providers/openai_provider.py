"""
OpenAI provider implementation.
"""

import base64
from typing import Any, cast

from openai import OpenAI

from scribe.providers.base import AIProvider, ProviderConfig
from scribe.providers.openai_models import (
    IMAGE_MODEL,
    TRANSCRIBE_MODEL,
    VISION_MODEL,
    audio_transcription_fields,
    ensure_usable,
)
from scribe.utils.network import download_public_image


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a chat completion using OpenAI."""

        params: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
        }
        params.update(kwargs)
        family = str(params["model"]).lower()
        # GPT-5 and GPT-6 reject max_tokens and custom temperature.
        if "gpt-5" in family or "gpt-6" in family:
            params.pop("max_tokens", None)
            params.pop("temperature", None)
            if max_tokens:
                params["max_completion_tokens"] = max_tokens
        else:
            if max_tokens:
                params["max_tokens"] = max_tokens
            if temperature is not None:
                params["temperature"] = temperature

        response = cast(Any, self.client.chat.completions).create(**params)

        # A content filter or an all-reasoning-budget GPT-5 response can return no
        # choices; guard so it surfaces as a clean provider error, not IndexError.
        if not getattr(response, "choices", None):
            raise ValueError("OpenAI returned no choices (possibly filtered or truncated)")

        usage = getattr(response, "usage", None)
        return {
            "content": response.choices[0].message.content or "",
            "usage": {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            },
            "model": response.model,
        }

    def transcribe_audio(self, audio_path: str, language: str | None = None, **kwargs: Any) -> str:
        """Transcribe audio with the current OpenAI file model."""
        model = str(kwargs.pop("model", None) or self.config.model or TRANSCRIBE_MODEL)
        prompt = kwargs.pop("prompt", None)
        prompt_text = prompt if isinstance(prompt, str) else None

        with open(audio_path, "rb") as audio_file:
            params: dict[str, Any] = {"model": model, "file": audio_file}
            params.update(
                audio_transcription_fields(
                    model,
                    language=language,
                    prompt=prompt_text,
                    include_chunking=False,
                )
            )
            params.update(kwargs)

            transcript = cast(Any, self.client.audio.transcriptions).create(**params)
            return str(getattr(transcript, "text", ""))

    def generate_image(self, prompt: str, size: str = "1024x1024", **kwargs: Any) -> bytes:
        """Generate an image with GPT Image."""
        model = kwargs.get("model", IMAGE_MODEL)
        ensure_usable(str(model))

        quality = kwargs.get("quality", "standard")
        if str(model).startswith("gpt-image-"):
            if quality == "hd":
                quality = "high"
            elif quality == "standard":
                quality = "auto"
        else:
            if quality in ["low", "medium"]:
                quality = "standard"
            elif quality == "high":
                quality = "hd"

        response = self.client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
        )

        data = response.data or []
        if not data:
            raise ValueError("OpenAI image generation returned no data")

        first_image = data[0]
        b64_json = getattr(first_image, "b64_json", None)
        if b64_json:
            return base64.b64decode(b64_json)
        image_url = getattr(first_image, "url", None)
        if not image_url:
            raise ValueError("OpenAI image generation returned no image URL")
        return download_public_image(image_url)

    def analyze_image(self, image_data: bytes, prompt: str, **kwargs: Any) -> str:
        """Analyze an image. A retired or GPT-4o vision id uses the current default."""

        # Encode image to base64
        image_b64 = base64.b64encode(image_data).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            }
        ]

        replaced_vision = {
            "gpt-4",
            "gpt-4-0613",
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-4o-2024-08-06",
            "gpt-4o-2024-11-20",
        }
        if "model" not in kwargs and self.config.model in replaced_vision:
            kwargs = {**kwargs, "model": VISION_MODEL}
        response = self.chat_completion(messages, **kwargs)
        return str(response["content"])
