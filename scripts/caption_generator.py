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
        return _template_caption(country, city, photo_count), []

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        prompt = (
            f"Eres un fotógrafo de viajes que comparte sus fotos en Instagram.\n\n"
            f"Genera un caption para un post de fotos de paisajes y viaje.\n\n"
            f"Lugar: {city}, {country}\n"
            f"Fotos en el carrusel: {photo_count}\n"
        )

        if date_taken:
            prompt += f"Fecha de las fotos: {date_taken}\n"

        prompt += (
            f"\nReglas:\n"
            f"- 2-4 oraciones\n"
            f"- Primera oración: algo personal, una reflexión o sensación del momento\n"
            f"- Después: un dato interesante, contexto del lugar o algo que lo haga único\n"
            f"- Tono: cercano pero informativo, como contándole a un amigo\n"
            f"- 1-2 emojis máximo, no al inicio\n"
            f"- No uses frases cliché (\"no hay palabras\", \"foto no le hace justicia\", \"un lugar mágico\")\n"
            f"- No uses exclamaciones excesivas\n"
            f"- Idioma: español\n"
            f"- Al final del caption, agrega exactamente 3 hashtags relevantes al lugar y contenido específico de las fotos, todos en minúsculas\n"
            f"\nResponde SOLO con el texto del caption seguido de los 3 hashtags. Sin comillas."
        )

        model = settings.get("apis", {}).get("anthropic_model", "claude-sonnet-4-20250514")
        message = client.messages.create(
            model=model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()

        # Separate caption text from AI-generated hashtags
        lines = raw.split("\n")
        caption_lines = []
        ai_hashtags = []
        for line in lines:
            tags_in_line = [w for w in line.split() if w.startswith("#")]
            if tags_in_line and len(tags_in_line) == len(line.split()):
                ai_hashtags.extend(tags_in_line)
            else:
                caption_lines.append(line)

        caption = "\n".join(caption_lines).strip()
        logger.info(f"Caption generated via Claude API for {city}, {country}")
        return caption, ai_hashtags

    except Exception as e:
        logger.warning(f"Claude API error: {e}. Using template caption.")
        return _template_caption(country, city, photo_count), []


def _template_caption(country, city, photo_count):
    """Fallback template when API is not available."""
    if country == "_unknown" or city == "_unknown":
        return f"Momentos capturados en el camino 📸"
    return f"Explorando {city}, {country} 🌍✨"
