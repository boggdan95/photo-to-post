# photo-to-post

Sistema de automatización para publicación de fotos de paisajes en Instagram.

## Setup

```bash
pip install -r requirements.txt
python run.py init
```

## Uso

```bash
python run.py classify      # Clasificar fotos por ubicación GPS
python run.py status        # Ver estado del sistema
python run.py create-posts  # Crear borradores (Phase 2)
python run.py review        # Interfaz web (Phase 3)
python run.py schedule      # Programar posts (Phase 4)
python run.py publish --post-id <id>  # Publicar (Phase 4)
```
