"""Caption generator - uses Claude API to generate Instagram captions."""

import json
import logging
import os

from scripts.utils import load_settings

logger = logging.getLogger("photo-to-post")


def _get_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    creds_path = "D:/photo-to-post/config/credentials.json"
    try:
        with open(creds_path, "r", encoding="utf-8") as f:
            creds = json.load(f)
        return creds.get("anthropic_api_key")
    except FileNotFoundError:
        return None


def generate_caption(country, city, photo_count, date_taken=None):
    """Generate an Instagram caption using Claude API.

    Returns a string with the caption text (without hashtags).
    Falls back to a template if API key is not configured.
    """
    api_key = _get_api_key()
    settings = load_settings()
    style = settings.get("caption_style", {})

    if not api_key:
        logger.warning("No Anthropic API key found. Using template caption.")
        return _template_caption(country, city, photo_count)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        prompt = (
            f"Genera un caption para Instagram sobre un post de fotos de paisajes.\n"
            f"- Lugar: {city}, {country}\n"
            f"- Número de fotos en el carrusel: {photo_count}\n"
            f"- Tono: {style.get('tone', 'inspirador, reflexivo, cercano')}\n"
            f"- Longitud: {style.get('length', 'medio (2-3 oraciones)')}\n"
            f"- Incluir emoji: {'sí' if style.get('include_emoji', True) else 'no'}\n"
            f"- Incluir call to action: {'sí' if style.get('include_call_to_action', False) else 'no'}\n"
            f"- Idioma: español\n"
            f"\nResponde SOLO con el texto del caption, sin hashtags, sin comillas."
        )

        if date_taken:
            prompt += f"\n- Fecha de las fotos: {date_taken}"

        model = settings.get("apis", {}).get("anthropic_model", "claude-sonnet-4-20250514")
        message = client.messages.create(
            model=model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        caption = message.content[0].text.strip()
        logger.info(f"Caption generated via Claude API for {city}, {country}")
        return caption

    except Exception as e:
        logger.warning(f"Claude API error: {e}. Using template caption.")
        return _template_caption(country, city, photo_count)


def _template_caption(country, city, photo_count):
    """Fallback template when API is not available."""
    if country == "_unknown" or city == "_unknown":
        return f"Momentos capturados en el camino 📸"
    return f"Explorando {city}, {country} 🌍✨"
