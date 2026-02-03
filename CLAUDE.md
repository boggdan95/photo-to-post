# photo-to-post - Contexto para Claude Code

## Qué es este proyecto
Sistema de automatización para publicar fotos de paisajes en Instagram. Flujo: Lightroom → clasificación GPS → carruseles → captions con IA → programación → publicación via Meta API.

## Estado actual
- **Flujo completo funcionando** — primera publicación real en Instagram el 2026-02-02
- **Credenciales configuradas**: Cloudinary, Meta Graph API (long-lived token ~60 días), Anthropic API
- **Captions con IA**: Claude API genera captions estilo informativo+personal + 3 hashtags contextuales
- **Hashtags**: 3 de IA (contextuales) + 3 base + 2 por país del JSON

## Estructura del proyecto
```
run.py                    ← CLI entry point (init, classify, create-posts, status, review, schedule, calendar, publish)
config/settings.json      ← Configuración general
config/hashtags.json      ← Grupos de hashtags (base, por país, rotation pool)
config/credentials.json   ← API keys (NO commitear, en .gitignore)
scripts/
  classifier.py           ← Lee EXIF GPS + Nominatim reverse geocoding
  post_creator.py         ← Agrupa fotos en carruseles, genera captions + hashtags
  caption_generator.py    ← Claude API para captions (fallback a template sin API key)
  scheduler.py            ← Asigna fechas con regla de diversidad de países
  publisher.py            ← Upload Cloudinary + publicación Meta Graph API
  utils.py                ← Folders, logging, config loading
web/
  app.py                  ← Flask: review/approve/reject posts, edit captions, reorder fotos
  templates/              ← HTML: base, index, review, approved, settings
```

## Entorno
- **Python 3.14** en Windows (pip global roto, usar venv)
- **Venv**: `D:/photo-to-post/venv/Scripts/python.exe`
- Ejecutar con: `D:/photo-to-post/venv/Scripts/python.exe run.py <comando>`
- Dependencias instaladas en venv: Pillow, exifread, requests, flask, anthropic, cloudinary
- **Lightroom export**: Long edge 2048px, quality 85%, limit 10MB (requisito de Cloudinary free tier)

## Flujo de carpetas
```
01_input/ → classify → 02_classified/{país}/{ciudad}/ → create-posts → 03_drafts/
→ review (web :5000) → 04_approved/ → schedule → 05_scheduled/ → publish → 06_published/{año}/{mes}/
```

## Credenciales (en config/credentials.json)
- **Cloudinary**: cloud_name, api_key, api_secret — hosting temporal de fotos para Meta API
- **Meta Graph API**: access_token (long-lived ~60 días, renovar antes de expirar), instagram_user_id
- **Anthropic**: api_key — para generar captions con Claude API

## Pendientes / próximos pasos
1. **Probar fix de reorder** — se corrigió el bug, falta verificar con un post nuevo
2. **Config desde la UI** — poder editar settings, hashtags desde la web
3. **Vista de calendario en la web**
4. **Clasificación por visión** (Claude API) cuando no hay GPS
5. **Mejorar UI** — hacer el flujo más visual y menos dependiente de terminal
6. **Flujo híbrido** — terminal para ejecutar (classify, schedule, publish), UI para revisar/editar/aprobar

## Para retomar
- Exportar fotos desde Lightroom: Long edge 2048px, quality 85%, limit 10MB
- Poner fotos en `01_input/` y correr flujo: classify → create-posts → review (web) → schedule → publish
- El servidor web se abre con `run.py review` (usar puerto alternativo si 5000 está ocupado)
- Meta token expira aprox. 2026-04-03 (60 días desde 2026-02-02), renovar antes

## Notas técnicas
- Meta access token expira en ~60 días, hay que renovarlo en Graph API Explorer y extenderlo a long-lived
- Cloudinary free tier: límite de 10MB por archivo
- Caption generator devuelve tupla (caption_text, ai_hashtags)
- Instagram API: carruseles máximo 10 fotos
- Credenciales en config/credentials.json (en .gitignore, nunca se commitean)
