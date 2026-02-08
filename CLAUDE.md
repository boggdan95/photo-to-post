# photo-to-post - Contexto para Claude Code

## Qué es este proyecto
Sistema de automatización para publicar fotos de paisajes en Instagram. Flujo: Lightroom → clasificación GPS → carruseles → captions con IA → programación → publicación via Meta API.

## Estado actual
- **Flujo completo funcionando** — publicaciones reales en Instagram desde 2026-02-02
- **UI web completa** — review, aprobados, programación, config, todo editable desde el navegador
- **Lanzador de escritorio** — doble clic para abrir la app, sin necesidad de terminal
- **Credenciales configuradas**: Cloudinary, Meta Graph API (long-lived token ~60 días), Anthropic API
- **Captions con IA**: Claude API genera captions estilo informativo+personal + 3 hashtags contextuales
- **Clasificación por visión**: Si una foto no tiene GPS, usa Claude Haiku para identificar el lugar
- **Grid mode**: Agrupa posts de 3 en 3 por país para filas coherentes en el perfil de Instagram (considera posts ya publicados)
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
    index.html            ← Dashboard con pipeline visual
    classified.html       ← Ver/mover fotos clasificadas antes de crear posts
    review.html           ← Review drafts: reorder, eliminar, dividir, aprobar
    approved.html         ← Posts aprobados: carrusel, publicar ahora
    schedule.html         ← Programación: preview, calendario, grid de Instagram
    published.html        ← Historial de posts publicados
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
→ review (web :5001) → 04_approved/ → schedule → 05_scheduled/ → publish/auto-publish → 06_published/{año}/{mes}/
```

## UI Web (http://localhost:5001)
- **/classified** — Ver fotos clasificadas por ubicación, mover/merge ubicaciones con pocas fotos
- **/review** — Revisar borradores: vista expandida, reordenar, eliminar, dividir (selector visual), aprobar/rechazar
- **/approved** — Posts aprobados: publicar ahora o regresar a Review con "Editar"
- **/schedule** — Programación: preview de fechas, calendario mensual, preview del grid de Instagram
- **/published** — Historial de posts publicados con fecha e ID de Instagram
- **/settings** — Configuración: editar todo sin tocar JSON (idioma, posts/semana, horarios, grid_mode, cloud_mode, hashtags)

## Settings importantes
| Setting | Descripción |
|---------|-------------|
| `timezone` | Zona horaria para comparar fechas (ej: "America/Guatemala") |
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
run.py auto-publish   # Publicar automáticamente posts que ya toca
run.py sync           # Git pull + sincronizar fotos locales con GitHub
```

## GitHub Actions (Auto-publish en la nube)
El workflow `.github/workflows/auto-publish.yml` corre cada 30 minutos y publica posts programados.

**Requisitos para que funcione:**
1. **cloud_mode: true** en settings.json (fotos se suben a Cloudinary al programar)
2. **timezone configurado** en settings.json (ej: "America/Guatemala")
3. **Secrets en GitHub**: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, META_ACCESS_TOKEN, INSTAGRAM_USER_ID
4. **post.json en GitHub**: Los posts programados deben estar commiteados (no en .gitignore)

**Archivos en GitHub:**
- `05_scheduled/*/post.json` — posts pendientes (sin carpeta photos/, las fotos están en Cloudinary)
- `06_published/*/post.json` — posts ya publicados

**Después de que la Action publique:**
```bash
run.py sync   # Hace git pull y mueve las fotos locales a published
```

También hay botón "Sync GitHub" en el dashboard de la UI.

## Auto-publish local (alternativa)
Para publicación automática sin GitHub:
1. Crear tarea en Task Scheduler de Windows
2. Ejecutar cada hora: `D:/photo-to-post/venv/Scripts/python.exe D:/photo-to-post/run.py auto-publish`
3. El script revisa posts en 05_scheduled/ y publica los que ya pasaron su fecha/hora

## Credenciales (en config/credentials.json)
- **Cloudinary**: cloud_name, api_key, api_secret — hosting temporal de fotos para Meta API
- **Meta Graph API**: access_token (long-lived ~60 días, renovar antes de expirar), instagram_user_id
- **Anthropic**: api_key — para generar captions con Claude API

## Pendientes / próximos pasos
1. **Verificar auto-publish** — el 10 Feb 12:00 debería publicarse Guatemala automáticamente
2. **Analytics** — considerar agregar métricas de engagement post-publicación

## Errores comunes y soluciones
| Error | Causa | Solución |
|-------|-------|----------|
| "No scheduled posts folder found" | posts no están en GitHub | Verificar .gitignore, commitear los post.json |
| Action corre pero no publica | Timezone incorrecto | Configurar `timezone` en settings.json |
| Permission denied en Action | Falta permiso de escritura | Añadir `permissions: contents: write` al workflow |
| Fotos no se mueven localmente | Desincronización con GitHub | Ejecutar `run.py sync` después de git pull |

## Para retomar
- Exportar fotos desde Lightroom: Long edge 2048px, quality 85%, limit 10MB
- Poner fotos en `01_input/` y correr flujo: classify → create-posts → review (web) → aprobar → schedule/publicar
- El servidor web se abre con `run.py review`
- Meta token expira aprox. 2026-04-03 (60 días desde 2026-02-02), renovar antes

## Lanzador de escritorio
- **photo-to-post.bat** — Abre el servidor y el navegador automáticamente
- Acceso directo en el escritorio apunta al .bat
- Puerto 5001 (evita conflicto con otras apps en 5000)

## Comportamiento importante
- **min_photos**: Ubicaciones con menos de 3 fotos NO generan posts (configurable en `carousel.min_photos`)
- **Fotos no se pierden**: Al eliminar foto de carrusel o rechazar post, las fotos regresan a `02_classified`
- **Dividir posts**: Posts con 6+ fotos pueden dividirse con selector visual (click en fotos a mover)
- **Merge ubicaciones**: En /classified puedes fusionar ubicaciones pequeñas con otras cercanas
- **Regresar a Review**: Posts aprobados pueden volver a Review con botón "Editar" para modificarlos
- **Vista expandida**: En Review, botón "Ver" abre modal con fotos grandes y edición de caption
- **Regenerar caption**: Botón "🔄 IA" permite regenerar caption con contexto opcional (ej: "pirámides, amanecer, drone")

## Grid mode inteligente
El grid mode considera los posts ya publicados en Instagram para mantener filas coherentes:
- Si hay 2 posts de un país publicados (fila incompleta), primero programa 1 más del mismo país para completar la fila de 3
- Luego programa los demás posts en grupos de 3 por país
- Lee el historial de `06_published/{año}/{mes}/` para detectar el estado actual del grid

## Notas técnicas
- Meta access token expira en ~60 días, renovar en Graph API Explorer y extender a long-lived
- Cloudinary free tier: 25GB/mes, más que suficiente para ~60 fotos/mes
- Instagram API: carruseles máximo 10 fotos
- **Carruseles**: El publisher espera a que Meta procese cada imagen (status FINISHED) antes de publicar
- Si cloud_mode=true, las URLs de Cloudinary se guardan en post.json al programar
- El publisher usa URLs existentes si ya están en post.json, evita subir duplicados
- **Modelos Claude**: Sonnet para captions (económico), Haiku para clasificación por visión (más barato aún)
- **Captions**: NO analiza fotos, usa ubicación + fecha + contexto opcional del usuario
