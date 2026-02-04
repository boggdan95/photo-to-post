# photo-to-post - Contexto para Claude Code

## Qué es este proyecto
Sistema de automatización para publicar fotos de paisajes en Instagram. Flujo: Lightroom → clasificación GPS → carruseles → captions con IA → programación → publicación via Meta API.

## Estado actual
- **Flujo completo funcionando** — publicaciones reales en Instagram desde 2026-02-02
- **UI web completa** — review, aprobados, programación, config, todo editable desde el navegador
- **Credenciales configuradas**: Cloudinary, Meta Graph API (long-lived token ~60 días), Anthropic API
- **Captions con IA**: Claude API genera captions estilo informativo+personal + 3 hashtags contextuales
- **Grid mode**: Agrupa posts de 3 en 3 por país para filas coherentes en el perfil de Instagram
- **Auto-publish**: Comando para publicación automática de posts programados

## Estructura del proyecto
```
run.py                    ← CLI entry point (init, classify, create-posts, status, review, schedule, calendar, publish, auto-publish)
config/settings.json      ← Configuración general (posts/semana, horarios, grid_mode, cloud_mode)
config/hashtags.json      ← Grupos de hashtags (base, por país, rotation pool)
config/credentials.json   ← API keys (NO commitear, en .gitignore)
scripts/
  classifier.py           ← Lee EXIF GPS + Nominatim reverse geocoding
  post_creator.py         ← Agrupa fotos en carruseles, genera captions + hashtags
  caption_generator.py    ← Claude API para captions (fallback a template sin API key)
  scheduler.py            ← Asigna fechas con grid_mode o diversidad, sube a Cloudinary si cloud_mode
  publisher.py            ← Upload Cloudinary + publicación Meta Graph API
  utils.py                ← Folders, logging, config loading
web/
  app.py                  ← Flask API: settings, fotos, publicación, programación
  templates/
    base.html             ← Layout con navegación
    index.html            ← Página de inicio
    review.html           ← Review drafts: reorder, eliminar fotos, editar caption
    approved.html         ← Posts aprobados: carrusel, publicar ahora
    schedule.html         ← Programación: preview, calendario, grid de Instagram
    settings.html         ← Config editable: todos los settings y hashtags
.github/workflows/
  auto-publish.yml        ← GitHub Action para auto-publish (requiere cloud_mode)
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
→ review (web :5000) → 04_approved/ → schedule → 05_scheduled/ → publish/auto-publish → 06_published/{año}/{mes}/
```

## UI Web (http://localhost:5000)
- **/review** — Revisar borradores: arrastrar para reordenar, X para eliminar foto, editar caption/hashtags, aprobar/rechazar
- **/approved** — Posts aprobados: ver carrusel con orden final, botón "Publicar ahora"
- **/schedule** — Programación: preview de fechas, calendario mensual, preview del grid de Instagram
- **/settings** — Configuración: editar todo sin tocar JSON (idioma, posts/semana, horarios, grid_mode, cloud_mode, hashtags)

## Settings importantes
| Setting | Descripción |
|---------|-------------|
| `posts_per_week` | Cuántos posts por semana (default: 3) |
| `preferred_times` | Horarios de publicación (default: 07:00, 12:00, 19:00) |
| `grid_mode` | Si true, agrupa de 3 en 3 por país para filas coherentes en Instagram |
| `cloud_mode` | Si true, sube fotos a Cloudinary al programar (permite GitHub Actions) |
| `max_consecutive_same_country` | Máx posts seguidos del mismo país si grid_mode=false |

## Comandos CLI
```bash
run.py init           # Crear estructura de carpetas
run.py classify       # Clasificar fotos por GPS
run.py create-posts   # Crear borradores de carruseles
run.py status         # Ver estado del pipeline
run.py review         # Abrir UI web en :5000
run.py schedule       # Programar posts aprobados
run.py calendar       # Ver calendario en terminal
run.py publish --post-id ID  # Publicar un post específico
run.py auto-publish   # Publicar automáticamente posts que ya toca (para Task Scheduler)
```

## Auto-publish
Para publicación automática local:
1. Crear tarea en Task Scheduler de Windows
2. Ejecutar cada hora: `D:/photo-to-post/venv/Scripts/python.exe D:/photo-to-post/run.py auto-publish`
3. El script revisa posts en 05_scheduled/ y publica los que ya pasaron su fecha/hora

## Credenciales (en config/credentials.json)
- **Cloudinary**: cloud_name, api_key, api_secret — hosting temporal de fotos para Meta API
- **Meta Graph API**: access_token (long-lived ~60 días, renovar antes de expirar), instagram_user_id
- **Anthropic**: api_key — para generar captions con Claude API

## Pendientes / próximos pasos
1. **Clasificación por visión** (Claude API) cuando no hay GPS
2. **Probar grid mode** con múltiples países para verificar agrupación
3. **GitHub Actions** — activar cloud_mode y configurar secrets para auto-publish en la nube

## Para retomar
- Exportar fotos desde Lightroom: Long edge 2048px, quality 85%, limit 10MB
- Poner fotos en `01_input/` y correr flujo: classify → create-posts → review (web) → aprobar → schedule/publicar
- El servidor web se abre con `run.py review`
- Meta token expira aprox. 2026-04-03 (60 días desde 2026-02-02), renovar antes

## Notas técnicas
- Meta access token expira en ~60 días, renovar en Graph API Explorer y extender a long-lived
- Cloudinary free tier: 25GB/mes, más que suficiente para ~60 fotos/mes
- Instagram API: carruseles máximo 10 fotos
- Si cloud_mode=true, las URLs de Cloudinary se guardan en post.json al programar
- El publisher usa URLs existentes si ya están en post.json, evita subir duplicados
