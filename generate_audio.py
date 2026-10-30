"""
Briefing diario en audio (podcast) generado en GitHub Actions.

La IA busca las noticias en internet y redacta el guion:
  1) Groq "compound" (búsqueda web incluida)  -> secreto GROQ_API_KEY
  2) Gemini con Búsqueda de Google            -> secreto GEMINI_API_KEY
Se usa el primero que funcione. Voz: edge-tts. Feed: rss.xml en GitHub Pages.
"""
import asyncio
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape as html_escape
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import edge_tts

# --- Configuración ---------------------------------------------------------
BASE_URL = os.environ.get("BASE_URL", "https://tokao.github.io/noticias-audio").rstrip("/")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "groq/compound")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
VOICE = os.environ.get("VOICE", "es-ES-ElviraNeural")
RATE = os.environ.get("RATE", "-5%")
TZ = ZoneInfo("Europe/Zurich")

EPISODES_DIR = "episodes"
EPISODES_JSON = "episodes.json"
RSS_FILE = "rss.xml"
GUION_FILE = "guion_ultimo.txt"   # último guion, para revisar qué se ha leído
MAX_EPISODES = 30

PODCAST_TITLE = "Boletín Diario de Noticias"
PODCAST_DESC = "Boletín diario personalizado generado automáticamente."
PODCAST_AUTHOR = "tokao"

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


# --- Prompt ----------------------------------------------------------------
def construir_prompt(ahora):
    fecha = f"{DIAS[ahora.weekday()]} {ahora.day} de {MESES[ahora.month - 1]} de {ahora.year}"
    hora = ahora.strftime("%H:%M")
    return f"""
Hoy es {fecha} y son las {hora} en Ginebra (Europe/Zurich).

Busca en internet las noticias más importantes de hoy y redacta un briefing diario en español
de España. El texto se convertirá directamente a voz para un podcast de entre 6 y 10 minutos,
así que el guion debe tener entre 900 y 1.400 palabras.

OBJETIVO Y PRIORIDADES
Selección rigurosa y útil de las noticias del día, priorizando:
- Política internacional y nacional de alto impacto.
- Tecnología, inteligencia artificial, ciberseguridad, internet, gadgets y grandes tecnológicas.
- Economía, mercados financieros, bolsa, empresas y energía.
- Sociedad y asuntos de especial relevancia pública.
- Transporte, movilidad, meteorología, servicios públicos y cambios locales que afecten a la vida cotidiana.

ESTRUCTURA DEL GUION (en este orden)
1. Apertura: «Buenos días. Este es el briefing del {fecha}, actualizado a las {hora}, hora de Ginebra.»
2. Resumen ejecutivo: entre 5 y 8 puntos, de mayor a menor impacto, incluyendo las novedades
   locales que requieran atención práctica.
3. Noticias por región, cada una introducida con una transición hablada («Pasamos a España»):
   Mundo; España; Barcelona; Bilbao y Bizkaia; Ginebra y alrededores (ciudad y cantón,
   Grand Genève, Pays de Gex y localidades próximas).
   Dentro de cada región, ordena por importancia, destaca tecnología y economía cuando haya
   novedades significativas y no repitas noticias entre secciones.
   Para cada noticia: qué ha ocurrido con los datos esenciales, por qué importa, y la fuente
   citada de forma hablada («según Reuters»).
   En Ginebra y alrededores presta especial atención a: transporte público, tráfico, obras y
   cierres; frontera franco-suiza y trabajadores transfronterizos; aeropuerto y conexiones
   ferroviarias; decisiones locales, servicios públicos, energía y cambios administrativos;
   meteorología y alertas oficiales con zona y periodo de validez; CERN, organizaciones
   internacionales y ecosistema tecnológico local.
4. Mercados: S&P 500, Nasdaq Composite, Dow Jones, IBEX 35, Euro Stoxx 50, CAC 40 y SMI;
   tecnológicas y otras empresas con movimientos destacados (con el motivo solo si está
   confirmado); EUR/USD y EUR/CHF; tipos, deuda, petróleo, gas y oro cuando ayuden a entender
   la jornada; macro y bancos centrales. Para cada cotización indica nivel, variación y si es
   sesión abierta, último cierre (con su fecha) o futuros, y que los datos pueden tener retraso.
   No mezcles momentos distintos sin advertirlo ni atribuyas causas no respaldadas.
5. Cierre breve.

CRITERIOS EDITORIALES
- Prioriza noticias publicadas o actualizadas hoy; si usas algo de las últimas 24-48 horas, di la fecha.
- Fuentes fiables: agencias, medios de referencia, organismos públicos y fuentes oficiales.
  Para alertas e incidencias de transporte, prioriza la fuente oficial.
- Marca las noticias en desarrollo, los datos provisionales y lo no confirmado.
- Separa hechos, declaraciones y análisis.
- Sin duplicados, sensacionalismo ni relleno. Si una sección no tiene novedades verificadas,
  dilo en una frase.
- No inventes datos, citas, cotizaciones ni enlaces. Si no puedes verificar algo, omítelo.

ESTILO PARA AUDIO
- Sin markdown, viñetas, asteriscos, encabezados con símbolos ni URLs dentro del guion.
- Párrafos breves y frases claras, pensadas para el oído.
- Cifras en formato español (1.234,5) y porcentajes como «un 1,2 por ciento».

FORMATO DE RESPUESTA (exacto)
GUION:
(el texto completo para leer en voz alta)
FUENTES:
(una línea por noticia citada: Sección | Titular | Medio | URL directa a la noticia)
"""


# --- Proveedores de IA con búsqueda web ------------------------------------
def post_json(url, body, headers, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]!r}") from None


def con_groq(prompt):
    data = post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        {"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3},
        {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"})
    return data["choices"][0]["message"]["content"], []


def con_gemini(prompt):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
           f"?key={os.environ['GEMINI_API_KEY']}")
    data = post_json(url, {"contents": [{"parts": [{"text": prompt}]}],
                           "tools": [{"google_search": {}}],
                           "generationConfig": {"temperature": 0.3}}, {})
    cand = data["candidates"][0]
    texto = "".join(p.get("text", "") for p in cand["content"]["parts"])
    # Enlaces que Google ha usado realmente para fundamentar la respuesta
    chunks = cand.get("groundingMetadata", {}).get("groundingChunks", [])
    extra = [(c["web"].get("title", "Fuente"), c["web"]["uri"]) for c in chunks if "web" in c]
    return texto, extra


PROVEEDORES = [("Groq", "GROQ_API_KEY", con_groq), ("Gemini", "GEMINI_API_KEY", con_gemini)]


def generar_con_ia(prompt):
    errores = []
    for nombre, clave, funcion in PROVEEDORES:
        if not os.environ.get(clave):
            continue
        for intento in range(2):
            try:
                print(f"Preparando el briefing con {nombre}...")
                texto, extra = funcion(prompt)
                if len(texto.split()) < 300:
                    raise RuntimeError(f"respuesta demasiado corta ({len(texto.split())} palabras)")
                print(f"Briefing generado con {nombre}.")
                return texto, extra
            except Exception as e:
                errores.append(f"{nombre}: {e}")
                print(f"  ! {nombre} falló: {e}")
                time.sleep(20)
    raise SystemExit("Ninguna IA ha funcionado. Revisa los secretos GROQ_API_KEY / GEMINI_API_KEY.\n"
                     + "\n".join(errores))


def separar_respuesta(texto):
    partes = re.split(r"\n\s*\**FUENTES\**\s*:?\s*\n", texto, maxsplit=1)
    guion = re.sub(r"^\s*\**GUION\**\s*:\s*", "", partes[0], flags=re.I)
    fuentes = []
    if len(partes) > 1:
        for linea in partes[1].splitlines():
            url = re.search(r"https?://\S+", linea)
            if url:
                desc = linea[:url.start()].strip(" |-*•\t")
                fuentes.append((desc or url.group(0), url.group(0).rstrip(").,")))
    return limpiar_texto(guion), fuentes


def limpiar_texto(texto):
    """Quita restos que el TTS leería en voz alta (markdown, URLs, acotaciones)."""
    texto = re.sub(r"https?://\S+", "", texto)
    texto = re.sub(r"\[[^\]]*\]|\([^)]*(música|pausa|sonido)[^)]*\)", "", texto, flags=re.I)
    texto = re.sub(r"^\s*[-•*]\s+", "", texto, flags=re.M)
    texto = re.sub(r"[*#_`>]+", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def notas_html(guion, fuentes):
    """Notas del episodio para Pocket Casts: inicio del guion + enlaces a las fuentes."""
    parrafos = [p for p in guion.split("\n\n") if p.strip()][:3]
    html = "".join(f"<p>{html_escape(p)}</p>" for p in parrafos)
    if fuentes:
        html += "<h3>Fuentes</h3><ul>" + "".join(
            f'<li><a href="{html_escape(u)}">{html_escape(d)}</a></li>' for d, u in fuentes) + "</ul>"
    return html


# --- Audio, episodios y feed -----------------------------------------------
async def generar_audio(texto, ruta):
    print(f"Generando {ruta} con {VOICE}...")
    await edge_tts.Communicate(texto, VOICE, rate=RATE).save(ruta)


def cargar_episodios():
    if os.path.exists(EPISODES_JSON):
        with open(EPISODES_JSON, encoding="utf-8") as f:
            return json.load(f)
    return []


def podar_episodios(episodios):
    episodios = episodios[:MAX_EPISODES]
    vigentes = {e["file"] for e in episodios}
    for nombre in os.listdir(EPISODES_DIR):
        if nombre.endswith(".mp3") and nombre not in vigentes:
            os.remove(os.path.join(EPISODES_DIR, nombre))
    return episodios


def generar_rss(episodios):
    ahora = format_datetime(datetime.now(timezone.utc), usegmt=True)
    imagen = f'\n    <itunes:image href="{BASE_URL}/cover.png"/>' if os.path.exists("cover.png") else ""
    items = []
    for e in episodios:
        desc = e["description"].replace("]]>", "]]&gt;")
        dur = f"\n      <itunes:duration>{e['duration']}</itunes:duration>" if e.get("duration") else ""
        items.append(f"""    <item>
      <title>{escape(e['title'])}</title>
      <description><![CDATA[{desc}]]></description>
      <pubDate>{e['pubDate']}</pubDate>
      <guid isPermaLink="false">{e['guid']}</guid>
      <enclosure url="{BASE_URL}/{EPISODES_DIR}/{e['file']}" length="{e['length']}" type="audio/mpeg"/>{dur}
    </item>""")
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(PODCAST_TITLE)}</title>
    <link>{BASE_URL}/</link>
    <atom:link href="{BASE_URL}/{RSS_FILE}" rel="self" type="application/rss+xml"/>
    <description>{escape(PODCAST_DESC)}</description>
    <language>es-es</language>
    <itunes:author>{escape(PODCAST_AUTHOR)}</itunes:author>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="News"/>{imagen}
    <lastBuildDate>{ahora}</lastBuildDate>
{chr(10).join(items)}
  </channel>
</rss>
"""
    with open(RSS_FILE, "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"RSS actualizado con {len(episodios)} episodios.")


async def main():
    os.makedirs(EPISODES_DIR, exist_ok=True)
    ahora_local = datetime.now(TZ)

    respuesta, enlaces_extra = generar_con_ia(construir_prompt(ahora_local))
    guion, fuentes = separar_respuesta(respuesta)
    vistos = {u for _, u in fuentes}
    fuentes += [(d, u) for d, u in enlaces_extra if u not in vistos]

    palabras = len(guion.split())
    print(f"Guion: {palabras} palabras (~{palabras / 140:.1f} min)")
    with open(GUION_FILE, "w", encoding="utf-8") as f:
        f.write(guion + "\n\nFUENTES:\n" + "\n".join(f"{d} | {u}" for d, u in fuentes))

    fecha = ahora_local.strftime("%Y-%m-%d")
    archivo = f"boletin_{fecha}.mp3"
    ruta = os.path.join(EPISODES_DIR, archivo)
    await generar_audio(guion, ruta)

    tam = os.path.getsize(ruta)
    segundos = int(tam * 8 / 48000)   # edge-tts genera MP3 a 48 kbps
    ahora = datetime.now(timezone.utc)
    episodio = {
        "guid": f"boletin-{fecha}",
        "file": archivo,
        "title": f"Boletín {fecha}",
        "description": notas_html(guion, fuentes),
        "pubDate": format_datetime(ahora, usegmt=True),
        "length": tam,
        "duration": f"{segundos // 60}:{segundos % 60:02d}",
    }
    print(f"Duración aproximada: {episodio['duration']}")

    episodios = [e for e in cargar_episodios() if e["guid"] != episodio["guid"]]
    episodios.insert(0, episodio)
    episodios = podar_episodios(episodios)
    with open(EPISODES_JSON, "w", encoding="utf-8") as f:
        json.dump(episodios, f, ensure_ascii=False, indent=2)
    generar_rss(episodios)


if __name__ == "__main__":
    asyncio.run(main())
