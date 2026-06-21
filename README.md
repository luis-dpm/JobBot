# JobBot — Resumen diario de empleo

Busca ofertas en Adzuna, las evalúa con Claude contra tu CV, y te envía un
email cada día a las 19:00 (hora de Madrid) con las que tengan buen match.

## Archivos

- `job_bot.py` — el script principal
- `.github/workflows/jobbot.yml` — programa la ejecución diaria en GitHub Actions
- `requirements.txt` — dependencias

## Instalación (una sola vez)

### 1. Sube estos archivos a tu repo `luis-dpm/JobBot`

Mantén la misma estructura de carpetas (la carpeta `.github/workflows/` es
importante, no la renombres).

### 2. Configura los "Secrets" del repo

Ve a tu repo en GitHub → **Settings** → **Secrets and variables** → **Actions**
→ **New repository secret**, y crea estos 6 secrets:

| Nombre              | Valor                                              |
|---------------------|-----------------------------------------------------|
| `ADZUNA_APP_ID`      | Tu app_id de Adzuna                                |
| `ADZUNA_APP_KEY`     | Tu app_key de Adzuna                               |
| `ANTHROPIC_API_KEY`  | Tu clave `sk-ant-...` de Anthropic                 |
| `GMAIL_ADDRESS`      | Tu email de Gmail (remitente)                      |
| `GMAIL_APP_PASSWORD` | La contraseña de aplicación de 16 caracteres        |
| `EMAIL_TO`           | El email donde quieres recibir el resumen (puede ser el mismo Gmail) |

### 3. Pruébalo manualmente

En GitHub, ve a la pestaña **Actions** de tu repo → selecciona "JobBot Daily
Run" → botón **Run workflow**. Así lo lanzas a mano sin esperar a las 19:00,
para comprobar que todo funciona y revisar tu email.

### 4. Listo

A partir de ahí correrá solo todos los días a las 19:00 (hora española de
verano; en invierno llegará sobre las 18:00 — si quieres precisión exacta
todo el año, dímelo y ajustamos el cron con la hora de invierno).

## Personalización

Abre `job_bot.py` y edita:
- `SEARCH_TERMS`: las palabras clave de búsqueda
- `CV_SUMMARY`: tu perfil — actualízalo cuando cambies tu CV
- `RESULTS_PER_SEARCH`: cuántas ofertas pedir por búsqueda

## Coste estimado

- Adzuna: gratis (hasta 1000 consultas/mes)
- GitHub Actions: gratis (muy por debajo del límite gratuito mensual)
- Anthropic API: pocos céntimos al mes con este volumen de uso diario
