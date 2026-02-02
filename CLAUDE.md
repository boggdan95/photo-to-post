# photo-to-post - Contexto para Claude Code

## Qué es este proyecto
Sistema de automatización para publicar fotos de paisajes en Instagram. Flujo: Lightroom → clasificación GPS → carruseles → captions con IA → programación → publicación via Meta API.

## Estado actual
- **Fases 1-4 implementadas y probadas** (classify, create-posts, review web, schedule, publish)
- **Fase 5 pendiente**: backup automático (lo demás de fase 5 ya está cubierto)
- **Flujo probado de punta a punta** con 6 fotos reales de Ciudad de México (pasos 1-5)

## Estructura del proyecto
```
run.py                    ← CLI entry point (init, classify, create-posts, status, review, schedule, calendar, publish)
config/settings.json      ← Configuración general
config/hashtags.json      ← Grupos de hashtags
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

## Flujo de carpetas
```
01_input/ → classify → 02_classified/{país}/{ciudad}/ → create-posts → 03_drafts/
→ review (web :5000) → 04_approved/ → schedule → 05_scheduled/ → publish → 06_published/{año}/{mes}/
```

## Pendientes / próximos pasos
1. **Configurar credenciales** para publicar en Instagram:
   - Anthropic API key (para captions con IA, opcional)
   - Cloudinary (cloud_name, api_key, api_secret)
   - Meta Graph API (access_token, instagram_user_id)
   - Van en `config/credentials.json` o variables de entorno
2. **Fase 5**: backup automático
3. **Mejoras posibles**:
   - Clasificación por visión (Claude API) cuando no hay GPS
   - Selección inteligente de hashtags por tipo de foto (actualmente random)
   - Edición de settings desde la web (actualmente solo vista)
   - Vista de calendario en la web

## Commits
```
9513d47 Fix: encoding de emojis en consola Windows para calendario
93fd245 Fase 4: Scheduling, Cloudinary upload y publicación via Meta API
2adee5c Fase 3: Interfaz web Flask para revisión y aprobación de posts
db0b005 Fase 2: Generación de posts con captions y hashtags
200bfaf Fase 1: Setup inicial, clasificador GPS y CLI básico
```
