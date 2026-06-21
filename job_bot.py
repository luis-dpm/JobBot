"""
JobBot - Busca ofertas de empleo a diario, las evalúa contra tu CV con Claude,
y te envía un resumen por email con las mejores oportunidades.
"""

import os
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# ----------------------------------------------------------------------
# CONFIGURACIÓN — edita esta sección a tu gusto
# ----------------------------------------------------------------------

# Términos de búsqueda (uno o varios, se combinan resultados)
SEARCH_TERMS = [
    "financial analyst",
    "analyst",
    "M&A analyst",
    "investment analyst",
    "business development",
    "international trade",
    "business administration",
    "trade finance",
    "credit analyst",
    "strategy analyst",
    "financial planning analyst",
]

# Adzuna usa códigos de país. Suiza = "ch". Si no encuentra suficientes
# resultados en Lugano, ampliamos a toda Suiza.
ADZUNA_COUNTRY = "ch"
LOCATION_KEYWORDS = ["Lugano", "Ticino", "Switzerland", "Svizzera"]

# Cuántos resultados pedir como máximo por término de búsqueda
RESULTS_PER_SEARCH = 30

# Días hacia atrás desde hoy para considerar una oferta "nueva".
# La primera vez conviene una ventana más amplia (7 días) para no
# arrancar con la bandeja vacía; luego se puede bajar a 2-3 días
# para que el bot solo te avise de lo realmente nuevo cada día.
MAX_DAYS_OLD = 14

# Resumen de tu perfil — esto es lo que Claude usa para evaluar el match.
# Edítalo cuando actualices tu CV.
CV_SUMMARY = """
Luis de Pedro - Financial Analyst con 5+ años de experiencia.

EXPERIENCIA:
- Financial Management Analyst, Acciona (España, 2024-presente): análisis financiero
  de proyectos públicos/privados >50M€, modelos financieros, cash flow, KPIs de licitación.
- Financial Analyst, Powen Solar Energy (México, 2023-2024): modelos financieros para
  proyectos PPA (200+ instalaciones, 100+ MW), análisis de portafolio para M&A,
  due diligence, dashboards en Excel.
- International Trade & Investment Advisor, Oficina Comercial de España en Cuba (2022):
  apoyo a empresas españolas en entrada a mercado, estudios sectoriales, negociación
  de deuda con agencias públicas cubanas.
- Sales Engineering IoT, Telefónica (España, 2018-2019): herramienta de Power BI para
  pricing global.
- HR/Industrial Development, Repsol (España, 2018): evaluación de desempeño, planes
  de carrera.

EDUCACIÓN: MBA International Management (ICEX-CECO), BA Psicología (UOC),
BA Business Management (UAM).

IDIOMAS: Español (nativo), Inglés (C1).

OBJETIVO: roles de analista (financiero, M&A, relaciones internacionales con
enfoque analítico) en Lugano, Suiza. El italiano NO es un idioma que domine
actualmente — es un área de mejora, no asumir que lo habla.

ADICIONAL: si una oferta está en cualquier otra parte de Suiza (no solo
Lugano) pero requiere o valora el español como idioma de trabajo, también
es de interés — está abierto a mudarse dentro de Suiza para un puesto así.
Lugano es la ubicación preferida, pero cualquier ciudad suiza (Zúrich,
Basilea, Ginebra, Berna, etc.) es aceptable si el puesto encaja bien con
el perfil.
"""

# Email de destino y remitente (mismo Gmail en ambos campos normalmente)
EMAIL_FROM = os.environ["GMAIL_ADDRESS"]
EMAIL_TO = os.environ.get("EMAIL_TO", os.environ["GMAIL_ADDRESS"])
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

ADZUNA_APP_ID = os.environ["ADZUNA_APP_ID"]
ADZUNA_APP_KEY = os.environ["ADZUNA_APP_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")  # opcional, para JSearch (LinkedIn/Indeed/Glassdoor)

# ----------------------------------------------------------------------
# 1. BUSCAR OFERTAS EN ADZUNA
# ----------------------------------------------------------------------

def fetch_adzuna_jobs():
    all_jobs = []
    seen_ids = set()

    for term in SEARCH_TERMS:
        url = f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1"
        params = {
            "app_id": ADZUNA_APP_ID,
            "app_key": ADZUNA_APP_KEY,
            "results_per_page": RESULTS_PER_SEARCH,
            "what": term,
            "max_days_old": MAX_DAYS_OLD,  # ofertas recientes (ventana ajustable arriba)
            "content-type": "application/json",
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"Error buscando '{term}': {e}")
            continue

        for job in data.get("results", []):
            job_id = job.get("id")
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            all_jobs.append(job)

    return all_jobs


def fetch_jsearch_jobs():
    """JSearch agrega resultados de Google for Jobs, que SÍ incluye ofertas
    originalmente publicadas en LinkedIn, Indeed, Glassdoor y webs de empresas.
    Requiere RAPIDAPI_KEY (gratis hasta 200 consultas/mes)."""
    if not RAPIDAPI_KEY:
        print("  (RAPIDAPI_KEY no configurada, se omite JSearch)")
        return []

    jobs = []
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }

    for term in SEARCH_TERMS:
        query = f"{term} in Lugano, Switzerland"
        try:
            resp = requests.get(
                "https://jsearch.p.rapidapi.com/search",
                headers=headers,
                params={
                    "query": query,
                    "num_pages": "1",
                    "date_posted": "week" if MAX_DAYS_OLD > 3 else "3days",
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"Error en JSearch buscando '{term}': {e}")
            continue

        for job in data.get("data", []):
            jobs.append({
                "id": job.get("job_id"),
                "title": job.get("job_title", ""),
                "company": {"display_name": job.get("employer_name", "")},
                "location": {"display_name": f"{job.get('job_city', '')}, {job.get('job_country', '')}".strip(", ")},
                "description": job.get("job_description", "") or "",
                "redirect_url": job.get("job_apply_link", ""),
                "source": job.get("job_publisher", ""),  # ej. "LinkedIn", "Indeed", "Glassdoor"
            })

    return jobs


def filter_by_location(jobs):
    """Ya no restringimos por ciudad: Adzuna está configurado con país=Suiza
    (ADZUNA_COUNTRY) así que cualquier oferta que llegue aquí ya es de Suiza.
    Dejamos pasar todo (Lugano, Zúrich, Basilea, Ginebra...) y es Claude quien,
    en el siguiente paso, valora el match real con el perfil — incluyendo
    bonus si requiere español o si está cerca de Lugano."""
    return jobs


# ----------------------------------------------------------------------
# 2. EVALUAR MATCH CON CLAUDE
# ----------------------------------------------------------------------

def evaluate_jobs_with_claude(jobs):
    if not jobs:
        return []

    # Preparamos un listado compacto para no gastar tokens de más
    jobs_text = ""
    for i, job in enumerate(jobs):
        title = job.get("title", "")
        company = job.get("company", {}).get("display_name", "")
        location = job.get("location", {}).get("display_name", "")
        description = (job.get("description") or "")[:600]
        jobs_text += f"\n---\n[{i}] {title} | {company} | {location}\n{description}\n"

    prompt = f"""Eres un reclutador senior. Aquí tienes el perfil de un candidato y una
lista de ofertas de empleo numeradas. Para cada oferta, evalúa el match con el perfil
en una escala de 0-10, y si es 6 o más, escribe un motivo breve (1 frase) de por qué
encaja y qué destacar al aplicar.

PERFIL DEL CANDIDATO:
{CV_SUMMARY}

OFERTAS:
{jobs_text}

Responde ÚNICAMENTE con un JSON (sin texto adicional, sin markdown) con este formato:
{{"results": [{{"index": 0, "score": 8, "reason": "..."}}, ...]}}

Incluye en el JSON solo las ofertas con score >= 6. Si ninguna llega a 6, devuelve
{{"results": []}}.
"""

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    text = "".join(block.get("text", "") for block in data.get("content", []))
    text = text.strip().strip("```json").strip("```").strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        print("No se pudo parsear la respuesta de Claude:")
        print(text)
        return []

    scored_jobs = []
    for r in parsed.get("results", []):
        idx = r.get("index")
        if idx is None or idx >= len(jobs):
            continue
        job = jobs[idx]
        scored_jobs.append({
            "title": job.get("title", ""),
            "company": job.get("company", {}).get("display_name", ""),
            "location": job.get("location", {}).get("display_name", ""),
            "url": job.get("redirect_url", ""),
            "score": r.get("score", 0),
            "reason": r.get("reason", ""),
        })

    scored_jobs.sort(key=lambda j: j["score"], reverse=True)
    return scored_jobs


# ----------------------------------------------------------------------
# 3. ENVIAR EMAIL
# ----------------------------------------------------------------------

def build_email_html(scored_jobs):
    today = datetime.now().strftime("%d/%m/%Y")

    if not scored_jobs:
        body = "<p>Hoy no se han encontrado ofertas nuevas que encajen bien con tu perfil.</p>"
    else:
        items = ""
        for j in scored_jobs:
            items += f"""
            <div style="margin-bottom:20px;padding:15px;border:1px solid #ddd;border-radius:8px;">
                <h3 style="margin:0 0 5px 0;">{j['title']} — {j['company']}</h3>
                <p style="margin:0 0 5px 0;color:#666;">{j['location']} · Match: {j['score']}/10</p>
                <p style="margin:0 0 10px 0;">{j['reason']}</p>
                <a href="{j['url']}" style="color:#0066cc;">Ver oferta y aplicar →</a>
            </div>
            """
        body = items

    html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:650px;margin:0 auto;">
        <h2>Resumen de empleo — {today}</h2>
        <p>{len(scored_jobs)} oferta(s) encontrada(s) con buen match para Lugano/Suiza:</p>
        {body}
    </body>
    </html>
    """
    return html


def send_email(html_content, num_jobs):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"JobBot: {num_jobs} ofertas para ti hoy ({datetime.now().strftime('%d/%m')})"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

def main():
    print("Buscando ofertas en Adzuna...")
    adzuna_jobs = fetch_adzuna_jobs()
    print(f"  {len(adzuna_jobs)} ofertas encontradas en Adzuna")

    print("Buscando ofertas en JSearch (LinkedIn/Indeed/Glassdoor)...")
    jsearch_jobs = fetch_jsearch_jobs()
    print(f"  {len(jsearch_jobs)} ofertas encontradas en JSearch")

    jobs = adzuna_jobs + jsearch_jobs
    print(f"  {len(jobs)} ofertas en total (combinadas)")

    jobs = filter_by_location(jobs)
    print(f"  {len(jobs)} ofertas tras filtrar por ubicación")

    print("Evaluando match con Claude...")
    scored_jobs = evaluate_jobs_with_claude(jobs)
    print(f"  {len(scored_jobs)} ofertas con buen match (score >= 6)")

    print("Enviando email...")
    html = build_email_html(scored_jobs)
    send_email(html, len(scored_jobs))
    print("¡Listo!")


if __name__ == "__main__":
    main()
