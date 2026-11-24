"""Provider capability and default-model catalog.

This module is intentionally dependency-light. Provider construction and live
health probes both depend on it, so keeping the catalog separate prevents those
two services from importing each other.
"""

from scribe.providers.openai_models import CHAT_MODEL, IMAGE_MODEL, TRANSCRIBE_MODEL
from scribe.utils.ollama_models import DEFAULT_OLLAMA_MODEL

# Checked 2026-11-14 against the provider model pages.
XAI_CHAT_MODEL = "grok-4.7"
XAI_IMAGE_MODEL = "grok-imagine-image-2.0"
ANTHROPIC_CHAT_MODEL = "claude-sonnet-5-5"
GEMINI_CHAT_MODEL = "gemini-3.8-flash"
GEMINI_IMAGE_MODEL = "gemini-nano-banana-2.1"
GEMINI_PRO_MODEL = "gemini-4-carbon"

_DEFAULT_MODELS: dict[str, dict[str, str | None]] = {
    "openai": {
        "joke": CHAT_MODEL,
        "meme": CHAT_MODEL,
        "meme_image": IMAGE_MODEL,
        "notes": CHAT_MODEL,
        "speakers": CHAT_MODEL,
        "transcribe": TRANSCRIBE_MODEL,
    },
    # OpenRouter's OpenAI-compatible chat endpoint; used for text features only.
    "openrouter": {
        "joke": None,
        "meme": None,
        "meme_image": None,
        "notes": f"google/{GEMINI_CHAT_MODEL}",
        "speakers": f"google/{GEMINI_CHAT_MODEL}",
        "transcribe": None,
    },
    "xai": {
        "joke": XAI_CHAT_MODEL,
        "meme": XAI_CHAT_MODEL,
        "meme_image": XAI_IMAGE_MODEL,
        "notes": XAI_CHAT_MODEL,
        "speakers": XAI_CHAT_MODEL,
        "transcribe": None,
    },
    "anthropic": {
        "joke": ANTHROPIC_CHAT_MODEL,
        "meme": ANTHROPIC_CHAT_MODEL,
        "meme_image": None,
        "notes": ANTHROPIC_CHAT_MODEL,
        "speakers": ANTHROPIC_CHAT_MODEL,
        "transcribe": None,
    },
    "gemini": {
        "joke": GEMINI_CHAT_MODEL,
        "meme": GEMINI_CHAT_MODEL,
        "meme_image": GEMINI_IMAGE_MODEL,
        "notes": GEMINI_CHAT_MODEL,
        "speakers": GEMINI_CHAT_MODEL,
        "transcribe": None,
    },
    # Ollama models are machine-dependent. These values are last-resort
    # fallbacks when runtime discovery cannot select an installed model.
    "ollama": {
        "joke": DEFAULT_OLLAMA_MODEL,
        "meme": DEFAULT_OLLAMA_MODEL,
        "meme_image": None,
        "notes": DEFAULT_OLLAMA_MODEL,
        "speakers": DEFAULT_OLLAMA_MODEL,
        "transcribe": None,
    },
}


def get_default_model(provider_name: str, feature: str) -> str:
    """Return the default model for a supported provider capability."""
    provider_defaults = _DEFAULT_MODELS.get(provider_name)
    model = provider_defaults.get(feature) if provider_defaults is not None else None
    if model is None:
        raise ValueError(f"Provider '{provider_name}' does not support feature '{feature}'")
    return model
