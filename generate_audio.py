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
from collections import Counter
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from html import escape as html_escape, unescape
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
VALIDACION_FILE = "validacion_ultima.txt"
MAX_EPISODES = 30

PODCAST_TITLE = "Boletín Diario de Noticias"
PODCAST_DESC = "Boletín diario personalizado generado automáticamente."
PODCAST_AUTHOR = "tokao"

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


# --- Prompt ----------------------------------------------------------------
def contexto_mercados(ahora):
    ny = ahora.astimezone(ZoneInfo("America/New_York"))
    apertura = datetime.strptime("09:30", "%H:%M").time()
    cierre = datetime.strptime("16:00", "%H:%M").time()
    sesion_ny = ny.weekday() < 5 and apertura <= ny.time() < cierre
    estado_ny = "sesión regular probablemente abierta" if sesion_ny else "sesión regular cerrada o no celebrada; exige fecha del último cierre"
    return f"Ahora en Nueva York son las {ny.strftime('%H:%M')} del {ny.date()}; estado orientativo de Wall Street: {estado_ny}."


def construir_prompt(ahora):
    fecha = f"{DIAS[ahora.weekday()]} {ahora.day} de {MESES[ahora.month - 1]} de {ahora.year}"
    hora = ahora.strftime("%H:%M")
    es_viernes = ahora.weekday() == 4
    instrucciones_viernes = """
6. Agenda cultural y musical cerca de Ginebra, solo porque hoy es viernes: programa de hoy primero
   y después los próximos 6 días. Revisa siempre Grand Théâtre de Genève y Palexpo, aunque no haya
   música. Añade cuando tengan interés: Comédie de Genève, Théâtre de Carouge, Forum Meyrin,
   Victoria Hall, AMR, L'Usine/PTR/Le Rez, Chat Noir, Alhambra, BFM, Grütli, MAH, Musée Ariana,
   MAMCO, Museo Internacional de la Cruz Roja, CERN, Château Rouge Annemasse, Ferney-Voltaire,
   Gex y Saint-Genis-Pouilly. Para cada evento: fecha y hora, lugar, tipo/género, descripción breve,
   precio si aparece sin búsqueda adicional y fuente directa. Evita relleno de baja relevancia.
""" if es_viernes else """
6. Hoy no es viernes: no incluyas agenda cultural ni una frase para decir que la omites.
"""
    return f"""
Hoy es {fecha} y son las {hora} en Ginebra (Europe/Zurich).
{contexto_mercados(ahora)}

Busca en internet las noticias más importantes de hoy y redacta un briefing diario en español
de España. El texto se convertirá directamente a voz para un podcast de entre 5 y 10 minutos.
Apunta a 700-1.400 palabras, sin rellenar: un día tranquilo puede quedar más corto y un día
cargado puede usar mejor el margen.

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
   sesión abierta, último cierre (con su fecha de sesión) o futuros, y que los datos pueden tener retraso.
   No mezcles momentos distintos sin advertirlo ni atribuyas causas no respaldadas. No uses una
   regla horaria fija para afirmar un cierre: calcula la fecha de sesión por la zona horaria real
   y exige una fuente directa que diga el cierre y su fecha. Si no la tienes, di que son datos
   en curso o del último cierre confirmado, sin convertirlos en cierre actual.
5. Tiempo: previsión útil para hoy en Barcelona, Bilbao/Bizkaia y Ginebra/Pays de Gex, con
   temperaturas, lluvia o alertas, periodo de validez y fuente fiable.
{instrucciones_viernes}
7. Cierre breve.

CRITERIOS EDITORIALES
- Prioriza noticias publicadas o actualizadas hoy; si usas algo de las últimas 24-48 horas, di la fecha.
- Fuentes fiables: agencias, medios de referencia, organismos públicos y fuentes oficiales.
  Para alertas e incidencias de transporte, prioriza la fuente oficial.
- Cada noticia concreta necesita una fuente directa y específica en FUENTES. Una portada genérica
  (por ejemplo ge.ch, una página principal de un medio o de una institución) no vale como prueba.
- Cada fuente debe incluir una evidencia literal copiada del contenido de la página, no del titular
  ni del resultado de búsqueda, que respalde la noticia. Si la página no es legible o no contiene
  evidencia para una afirmación, omite la afirmación o di expresamente que faltan datos verificados.
- Si no tienes una fuente directa para una afirmación local concreta, omítela. No rellenes con
  datos plausibles sobre aeropuertos, controles fronterizos, red eléctrica o CERN.
- Marca las noticias en desarrollo, los datos provisionales y lo no confirmado.
- Separa hechos, declaraciones y análisis.
- Sin duplicados, sensacionalismo ni relleno. Si una sección no tiene novedades verificadas,
  escribe exactamente: «Sin novedades verificadas.»
- No inventes datos, citas, cotizaciones, enlaces, alertas, comunicados ni eventos.

ESTILO PARA AUDIO
- Sin markdown, viñetas, asteriscos, encabezados con símbolos ni URLs dentro del guion.
- Al final de cada párrafo con una noticia concreta añade su marca de fuente `[S#]`; el código la quitará antes de leerlo. Cada párrafo debe contener solo afirmaciones cubiertas por sus marcas.
- Párrafos breves y frases claras, pensadas para el oído.
- Cifras en formato español (1.234,5) y porcentajes como «un 1,2 por ciento».

FORMATO DE RESPUESTA (exacto)
GUION:
(el texto completo para leer en voz alta)
FUENTES:
(una línea por noticia citada, con ocho campos separados por barras verticales)
S1 | Sección exacta | Frase exacta del guion de 8 a 80 palabras que identifica la noticia | Medio | URL directa | Fecha de publicación o actualización de la fuente en formato AAAA-MM-DD | Evidencia literal de 12 a 60 palabras copiada del contenido de esa página | Traducción española literal de la evidencia de 12 a 80 palabras
No uses barras verticales dentro de los campos. Cada afirmación concreta del guion debe quedar
vinculada a una línea S y cada S debe aparecer una vez como `[S#]` en el guion. No incluyas líneas
de fuente que no respalden una noticia del guion.
"""

# --- Proveedores de IA con búsqueda web ------------------------------------
def post_json(url, body, headers, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json",
                                          # Cloudflare (Groq) bloquea el User-Agent por defecto de Python
                                          "User-Agent": "noticias-audio/1.0 (GitHub Actions)",
                                          **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]!r}") from None


# Modelos de Groq con búsqueda web, por orden de preferencia.
#  - "compound": buscan en la web por sí mismos.
#  - "gpt-oss": necesitan activar la herramienta browser_search.
GROQ_CANDIDATOS = [
    (GROQ_MODEL, None),
    ("groq/compound-mini", None),
    ("compound-beta", None),
    ("compound-beta-mini", None),
    ("openai/gpt-oss-120b", "browser_search"),
    ("openai/gpt-oss-20b", "browser_search"),
]
GROQ_HEADERS = lambda: {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}",
                        "User-Agent": "noticias-audio/1.0 (GitHub Actions)"}


def modelos_groq():
    req = urllib.request.Request("https://api.groq.com/openai/v1/models", headers=GROQ_HEADERS())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ids = sorted(m["id"] for m in json.load(r)["data"])
        print("Modelos disponibles en tu cuenta de Groq:", ", ".join(ids))
        return set(ids)
    except Exception as e:
        print(f"  ! No se pudo listar los modelos de Groq: {e}")
        return None


def con_groq(prompt):
    disponibles = modelos_groq()
    errores = []
    for modelo, herramienta in dict.fromkeys(GROQ_CANDIDATOS):
        if disponibles is not None and modelo not in disponibles:
            continue
        body = {"model": modelo, "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3, "max_completion_tokens": 8000}
        if herramienta:
            body["tools"] = [{"type": herramienta}]
            body["tool_choice"] = "auto"
        try:
            print(f"  Probando {modelo}...")
            data = post_json("https://api.groq.com/openai/v1/chat/completions", body, GROQ_HEADERS())
            texto = data["choices"][0]["message"].get("content") or ""
            if len(texto.split()) < 300:
                raise RuntimeError(f"respuesta demasiado corta ({len(texto.split())} palabras)")
            print(f"  Usado el modelo {modelo}.")
            return texto, []
        except Exception as e:
            errores.append(f"{modelo}: {e}")
            print(f"  ! {modelo}: {str(e)[:300]}")
    raise RuntimeError("ningún modelo de Groq con búsqueda web ha funcionado")


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
    guion_marcado = re.sub(r"^\s*\**GUION\**\s*:\s*", "", partes[0], flags=re.I)
    fuentes = []
    if len(partes) > 1:
        for linea in partes[1].splitlines():
            linea = linea.strip()
            if not linea:
                continue
            campos = [p.strip() for p in linea.split("|")]
            if len(campos) >= 8:
                fuentes.append({
                    "id": campos[0],
                    "seccion": campos[1],
                    "frase": campos[2],
                    "medio": campos[3],
                    "url": campos[4],
                    "fecha": campos[5],
                    "evidencia": campos[6],
                    "traduccion": " | ".join(campos[7:]),
                    "raw": linea,
                })
            else:
                fuentes.append({"id": campos[0] if campos else "?", "raw": linea, "malformada": True})
    return limpiar_texto(guion_marcado), fuentes, guion_marcado.strip()


def limpiar_texto(texto):
    """Quita restos que el TTS leería en voz alta (markdown, URLs, acotaciones y marcas de fuente)."""
    texto = re.sub(r"\s*\[S\d+\]", "", texto)
    texto = re.sub(r"https?://\S+", "", texto)
    texto = re.sub(r"\[[^\]]*\]|\([^)]*(música|pausa|sonido)[^)]*\)", "", texto, flags=re.I)
    texto = re.sub(r"^\s*[-•*]\s+", "", texto, flags=re.M)
    texto = re.sub(r"[*#_`>]+", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


# --- Validación editorial y del paquete publicado ---------------------------
class FuenteNoVerificable(Exception):
    pass


def normalizar(texto):
    base = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def palabras_normalizadas(texto):
    return re.findall(r"[a-z0-9]+", normalizar(texto))


STOPWORDS_ES = {
    "a", "al", "con", "de", "del", "el", "en", "es", "la", "las", "los", "para",
    "por", "que", "se", "su", "sus", "una", "un", "y", "o", "hoy", "ayer", "segun",
    "este", "esta", "estos", "estas", "como", "mas", "muy", "tras", "sobre", "entre",
}
NEGACIONES = {"no", "nunca", "jamas", "tampoco", "sin", "ni"}


def relacion_textual(frase, evidencia):
    claves_frase = {p for p in palabras_normalizadas(frase) if (len(p) > 1 or p.isdigit()) and p not in STOPWORDS_ES}
    claves_evidencia = {p for p in palabras_normalizadas(evidencia) if (len(p) > 1 or p.isdigit()) and p not in STOPWORDS_ES}
    if not claves_frase:
        return 0.0
    return len(claves_frase & claves_evidencia) / len(claves_frase)




def numeros(texto):
    return Counter(re.findall(r"\d+(?:[.,]\d+)?", texto))


def negaciones(texto):
    return Counter(p for p in palabras_normalizadas(texto) if p in NEGACIONES)


def cobertura_secuencia(fragmento, texto, n=5):
    """Cobertura de n-gramas: 1.0 es literal; tolera cambios mínimos de puntuación o una palabra."""
    f = palabras_normalizadas(fragmento)
    t = palabras_normalizadas(texto)
    if not f or not t:
        return 0.0
    if len(f) < n or len(t) < n:
        return 1.0 if " ".join(f) in " ".join(t) else 0.0
    ngramas = {tuple(t[i:i+n]) for i in range(len(t)-n+1)}
    coincidentes = sum(1 for i in range(len(f)-n+1) if tuple(f[i:i+n]) in ngramas)
    return coincidentes / (len(f)-n+1)


def es_url_portada(url):
    try:
        partes = urllib.parse.urlparse(url)
    except Exception:
        return True
    ruta = (partes.path or "/").rstrip("/")
    return not partes.netloc or ruta in ("", "/index", "/home")


def descargar_fuente(url, max_bytes=1_500_000):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) noticias-audio/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status >= 400:
                raise FuenteNoVerificable(f"HTTP {r.status}")
            content_type = r.headers.get("content-type", "")
            datos = r.read(max_bytes + 1)
    except Exception as e:
        raise FuenteNoVerificable(str(e)) from None
    if any(t in content_type.lower() for t in ("application/pdf", "audio/", "video/", "image/")):
        raise FuenteNoVerificable(f"tipo no legible como artículo: {content_type}")
    charset = "utf-8"
    m = re.search(r"charset=([^;]+)", content_type, flags=re.I)
    if m:
        charset = m.group(1).strip()
    else:
        cabecera = datos[:5000].decode("ascii", errors="ignore")
        m = re.search(r'charset=["\']?([A-Za-z0-9_-]+)', cabecera, flags=re.I)
        if m:
            charset = m.group(1)
    return datos[:max_bytes].decode(charset, errors="replace")


def extraer_texto_html(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg|template)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    texto = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(texto)).strip()


def parse_fecha(valor):
    valor = valor.strip().strip('"\'')
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(valor)
        except Exception:
            return set()
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            return {dt.date(), dt.astimezone(TZ).date()}
        return {dt.date()}
    return set()


def extraer_fechas_html(html):
    candidatos = []
    for etiqueta in re.findall(r"(?is)<meta[^>]+>", html):
        nombre = " ".join(re.findall(r"(?:property|name)=[\"']([^\"']+)[\"']", etiqueta, flags=re.I)).lower()
        if not any(k in nombre for k in ("published", "modified", "date", "pubdate")):
            continue
        m = re.search(r"content=[\"']([^\"']+)[\"']", etiqueta, flags=re.I)
        if m:
            candidatos.append(m.group(1))
    for patron in (r'"datePublished"\s*:\s*"([^"]+)"', r'"dateModified"\s*:\s*"([^"]+)"', r'"startDate"\s*:\s*"([^"]+)"', r'"endDate"\s*:\s*"([^"]+)"'):
        candidatos += re.findall(patron, html, flags=re.I)
    candidatos += re.findall(r"(?is)<time[^>]+datetime=[\"']([^\"']+)[\"']", html)
    fechas = set().union(*(parse_fecha(v) for v in candidatos)) if candidatos else set()
    return sorted(fechas, reverse=True)


def extraer_fechas_texto(texto):
    fechas = set()
    for d, m, y in re.findall(r"\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b", texto):
        try:
            fechas.add(datetime(int(y), int(m), int(d)).date())
        except ValueError:
            pass
    meses = {
        "enero": 1, "janvier": 1, "febrero": 2, "fevrier": 2, "février": 2,
        "marzo": 3, "mars": 3, "abril": 4, "avril": 4, "mayo": 5, "mai": 5,
        "junio": 6, "juin": 6, "julio": 7, "juillet": 7, "agosto": 8, "aout": 8, "août": 8,
        "septiembre": 9, "septembre": 9, "octubre": 10, "octobre": 10,
        "noviembre": 11, "novembre": 11, "diciembre": 12, "decembre": 12, "décembre": 12,
    }
    for d, mes, y in re.findall(r"\b(\d{1,2})\s+(?:de\s+)?([A-Za-záéíóúûü]+)\s+(?:de\s+)?(20\d{2})\b", normalizar(texto), flags=re.I):
        numero = meses.get(mes.lower())
        if numero:
            try:
                fechas.add(datetime(int(y), numero, int(d)).date())
            except ValueError:
                pass
    return fechas


def seccion_fuente(seccion):
    s = normalizar(seccion)
    if "agenda" in s or "cultura" in s:
        return "agenda cultural"
    if "bilbao" in s or "bizkaia" in s or "vizcaya" in s:
        return "bilbao y bizkaia"
    if "ginebra" in s or "geneve" in s or "geneva" in s or "gex" in s:
        return "ginebra y alrededores"
    if "mercado" in s or "bolsa" in s or "economia" in s:
        return "mercados"
    if "tiempo" in s or "meteo" in s or "clima" in s:
        return "tiempo"
    if "barcelona" in s:
        return "barcelona"
    if "espana" in s:
        return "espana"
    if "mundo" in s or "internacional" in s:
        return "mundo"
    return s


def texto_seccion(guion, nombre):
    objetivo = normalizar(nombre)
    encabezados = [
        "resumen ejecutivo", "mundo", "espana", "barcelona", "bilbao y bizkaia",
        "ginebra y alrededores", "mercados", "tiempo", "agenda cultural", "cierre",
    ]

    def encabezado(linea):
        limpio = normalizar(linea.strip().rstrip(":"))
        for item in encabezados:
            if limpio == item or limpio.startswith(item + " "):
                return item
        return None

    dentro = False
    partes = []
    for linea in guion.splitlines():
        marca = encabezado(linea)
        if marca:
            if dentro and marca != objetivo:
                break
            if marca == objetivo:
                dentro = True
                continue
        if dentro:
            partes.append(linea)
    return "\n".join(partes).strip()


def validar_fuente(fuente, guion, ahora):
    errores, avisos = [], []
    identificador = fuente.get("id", "?")
    if fuente.get("malformada"):
        return [f"{identificador}: línea de fuente mal formada; debe tener 8 campos"], avisos, None
    obligatorios = ["seccion", "frase", "medio", "url", "fecha", "evidencia", "traduccion"]
    for campo in obligatorios:
        if not fuente.get(campo):
            errores.append(f"{identificador}: falta {campo}")
    if errores:
        return errores, avisos, None

    url = fuente["url"]
    if not re.match(r"^https://", url):
        errores.append(f"{identificador}: la URL no es HTTPS")
    if es_url_portada(url):
        errores.append(f"{identificador}: la URL es una portada genérica")

    frase_palabras = len(palabras_normalizadas(fuente["frase"]))
    if not 8 <= frase_palabras <= 80:
        errores.append(f"{identificador}: la frase del guion tiene {frase_palabras} palabras, fuera de 8-80")
    elif cobertura_secuencia(fuente["frase"], guion, n=3) < 0.90:
        errores.append(f"{identificador}: la frase de enlace no aparece de forma casi literal en el guion")

    evidencia_palabras = len(palabras_normalizadas(fuente["evidencia"]))
    if not 12 <= evidencia_palabras <= 80:
        errores.append(f"{identificador}: la evidencia tiene {evidencia_palabras} palabras, fuera de 12-80")
    else:
        traduccion_palabras = len(palabras_normalizadas(fuente["traduccion"]))
        if not 12 <= traduccion_palabras <= 80:
            errores.append(f"{identificador}: la traducción tiene {traduccion_palabras} palabras, fuera de 12-80")
        elif relacion_textual(fuente["frase"], fuente["traduccion"]) < 0.55:
            errores.append(f"{identificador}: la traducción de la evidencia no parece respaldar la frase del guion")
        faltan_numeros = numeros(fuente["frase"]) - numeros(fuente["traduccion"])
        if faltan_numeros:
            errores.append(f"{identificador}: la traducción no contiene las cifras de la frase: {sorted(faltan_numeros)}")
        if negaciones(fuente["frase"]) != negaciones(fuente["traduccion"]):
            errores.append(f"{identificador}: la traducción no conserva la negación/polaridad de la frase")

    try:
        fecha_declarada = datetime.strptime(fuente["fecha"], "%Y-%m-%d").date()
    except ValueError:
        errores.append(f"{identificador}: fecha '{fuente['fecha']}' no usa AAAA-MM-DD")
        fecha_declarada = None

    if errores:
        return errores, avisos, None

    try:
        html = descargar_fuente(url)
    except FuenteNoVerificable as e:
        return [f"{identificador}: fuente inaccesible o no legible; la afirmación debe omitirse ({e})"], avisos, None

    texto = extraer_texto_html(html)
    if len(texto) < 300:
        return [f"{identificador}: la página tiene demasiado poco texto legible"], avisos, None
    cobertura = cobertura_secuencia(fuente["evidencia"], texto, n=5)
    if cobertura < 0.75:
        errores.append(f"{identificador}: la evidencia no aparece en la página (cobertura {cobertura:.0%})")

    seccion_normalizada = seccion_fuente(fuente["seccion"])
    fechas = set(extraer_fechas_html(html))
    if seccion_normalizada in ("tiempo", "agenda cultural"):
        fechas |= extraer_fechas_texto(texto)
    fechas = sorted(fechas, reverse=True)
    if not fechas:
        errores.append(f"{identificador}: no se encontró fecha legible en la fuente")
    elif fecha_declarada and fecha_declarada not in fechas:
        errores.append(f"{identificador}: fecha declarada {fecha_declarada} no coincide con las de la página {fechas[:3]}")
    if fecha_declarada and fecha_declarada > ahora.date() and seccion_normalizada not in ("tiempo", "agenda cultural"):
        errores.append(f"{identificador}: la fuente declara una fecha futura ({fecha_declarada})")

    if fecha_declarada and seccion_normalizada != "agenda cultural":
        antiguedad = (ahora.date() - fecha_declarada).days
        if antiguedad > 3:
            avisos.append(f"{identificador}: fuente de hace {antiguedad} días; el guion debe dejar clara su fecha")

    if errores:
        return errores, avisos, None
    informe = {"id": identificador, "seccion": seccion_fuente(fuente["seccion"]),
               "url": url, "fecha": str(fecha_declarada), "evidencia": f"{cobertura:.0%}"}
    return [], avisos, informe


def validar_guion(guion, fuentes, ahora, guion_marcado):
    errores, avisos, informes = [], [], []
    palabras = len(guion.split())
    if palabras > 1800:
        errores.append(f"el guion tiene {palabras} palabras; supera el margen máximo prudente de 1800")

    if re.search(r"https?://", guion):
        errores.append("el guion hablado todavía contiene URLs")

    secciones = [
        ("Mundo", r"^\s*Mundo\s*:"),
        ("España", r"^\s*España\s*:"),
        ("Barcelona", r"^\s*Barcelona\s*:"),
        ("Bilbao y Bizkaia", r"^\s*Bilbao\s+y\s+Bizkaia\s*:"),
        ("Ginebra y alrededores", r"^\s*Ginebra\s+y\s+alrededores\s*:"),
        ("Mercados", r"^\s*Mercados\s*:"),
        ("Tiempo", r"^\s*Tiempo\s*:"),
    ]
    if ahora.weekday() == 4:
        secciones.append(("Agenda cultural", r"^\s*Agenda\s+cultural"))
    for nombre, patron in secciones:
        if not re.search(patron, guion, flags=re.I | re.M):
            errores.append(f"falta la sección {nombre}")

    ids = [f.get("id") for f in fuentes if f.get("id")]
    if len(ids) != len(set(ids)):
        errores.append("hay IDs de fuentes repetidos")
    urls = [f.get("url") for f in fuentes if f.get("url")]
    if len(urls) != len(set(urls)):
        errores.append("hay URLs de fuentes repetidas")

    fuentes_validas = {}
    for fuente in fuentes:
        e, a, informe = validar_fuente(fuente, guion, ahora)
        errores += e
        avisos += a
        if informe:
            informes.append(informe)
            fuentes_validas.setdefault(informe["seccion"], []).append(informe)

    for identificador in ids:
        marcas = re.findall(rf"\[{re.escape(identificador)}\]", guion_marcado)
        if len(marcas) != 1:
            errores.append(f"{identificador}: aparece {len(marcas)} veces como marca de fuente en el guion")
    for marca in sorted(set(re.findall(r"\[(S\d+)\]", guion_marcado))):
        if marca not in ids:
            errores.append(f"el guion usa la marca {marca} sin línea de fuente")

    sin_novedades = re.compile(r"sin (novedades|datos) (verificadas|suficientes)|no hay novedades verificadas", re.I)
    fuentes_por_id = {f.get("id"): f for f in fuentes if f.get("id")}
    for parrafo in [p.strip() for p in re.split(r"\n\s*\n", guion_marcado) if p.strip()]:
        if len(parrafo.split()) < 20 or sin_novedades.search(parrafo):
            continue
        if re.fullmatch(r"[^:\n]{1,80}:", parrafo):
            continue
        marcas = re.findall(r"\[(S\d+)\]", parrafo)
        if not marcas:
            errores.append("hay un párrafo informativo sin marca de fuente")
            continue
        parrafo_limpio = re.sub(r"\s*\[S\d+\]", "", parrafo)
        texto_fuentes = " ".join(fuentes_por_id[m].get("frase", "") for m in marcas if m in fuentes_por_id)
        if cobertura_secuencia(parrafo_limpio, texto_fuentes, n=3) < 0.75:
            errores.append("hay un párrafo con contenido no cubierto por la frase de su fuente")
    requisitos = ["mundo", "espana", "barcelona", "bilbao y bizkaia", "ginebra y alrededores", "mercados", "tiempo"]
    if ahora.weekday() == 4:
        requisitos.append("agenda cultural")
    for nombre in requisitos:
        patron = dict((normalizar(n), p) for n, p in secciones)[nombre]
        cuerpo = texto_seccion(guion, nombre)
        cuerpo_marcado = texto_seccion(guion_marcado, nombre)
        if not sin_novedades.search(cuerpo) and not fuentes_validas.get(nombre):
            errores.append(f"la sección {nombre} incluye contenido sin ninguna fuente verificada")
    return errores, avisos, informes


def generar_y_validar(prompt, ahora):
    respuesta, _enlaces_extra = generar_con_ia(prompt)
    guion, fuentes, guion_marcado = separar_respuesta(respuesta)
    errores, avisos, informes = validar_guion(guion, fuentes, ahora, guion_marcado)
    if not errores:
        return guion, fuentes, avisos, informes, 1

    print("La primera versión no superó la validación editorial:")
    for error in errores:
        print(f"  - {error}")
    correcciones = "\n".join(f"- {e}" for e in errores)
    prompt_corregido = prompt + f"""

CORRECCIONES OBLIGATORIAS
La versión anterior fue rechazada por comprobaciones deterministas de estructura, fecha y evidencia:
{correcciones}
Rehaz el guion y FUENTES cumpliendo todas las reglas. No expliques las correcciones.
"""
    respuesta, _enlaces_extra = generar_con_ia(prompt_corregido)
    guion, fuentes, guion_marcado = separar_respuesta(respuesta)
    errores_finales, avisos, informes = validar_guion(guion, fuentes, ahora, guion_marcado)
    if errores_finales:
        raise SystemExit("El guion no supera la validación; no se publica audio:\n"
                         + "\n".join(f"- {e}" for e in errores_finales))
    return guion, fuentes, avisos, informes, 2


def escribir_validacion(guion, fuentes, avisos, informes, intentos):
    with open(VALIDACION_FILE, "w", encoding="utf-8") as f:
        f.write(f"Guion validado en intento {intentos}.\n")
        f.write(f"Palabras: {len(guion.split())}.\n")
        f.write(f"Noticias con evidencia legible y fecha comprobada: {len(informes)}.\n")
        for informe in informes:
            f.write(f"- {informe['id']} | {informe['seccion']} | {informe['fecha']} | evidencia {informe['evidencia']} | {informe['url']}\n")
        if avisos:
            f.write("Avisos:\n")
            f.write("\n".join(f"- {a}" for a in avisos) + "\n")
        else:
            f.write("Sin avisos.\n")


def notas_html(guion, fuentes):
    """Notas del episodio para Pocket Casts: inicio del guion + enlaces a las fuentes."""
    parrafos = [p for p in guion.split("\n\n") if p.strip()][:3]
    html = "".join(f"<p>{html_escape(p)}</p>" for p in parrafos)
    if fuentes:
        html += "<h3>Fuentes</h3><ul>" + "".join(
            f'<li><a href="{html_escape(f.get("url", "#"))}">{html_escape(f.get("seccion", "Fuente") + " | " + f.get("medio", "") + " | " + f.get("fecha", ""))}</a></li>'
            for f in fuentes) + "</ul>"
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
    bloqueo = "\n    <itunes:block>Yes</itunes:block>"
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
    <itunes:explicit>false</itunes:explicit>{bloqueo}
    <itunes:category text="News"/>{imagen}
    <lastBuildDate>{ahora}</lastBuildDate>
{chr(10).join(items)}
  </channel>
</rss>
"""
    with open(RSS_FILE, "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"RSS actualizado con {len(episodios)} episodios.")


def validar_paquete(ruta_audio):
    if not os.path.exists(ruta_audio) or os.path.getsize(ruta_audio) < 10000:
        raise SystemExit("El MP3 no existe o es demasiado pequeño; no se publica.")
    tree = ET.parse(RSS_FILE)
    canal = tree.getroot().find("channel")
    if canal is None:
        raise SystemExit("El RSS no tiene channel; no se publica.")
    items = canal.findall("item")
    if not items:
        raise SystemExit("El RSS no tiene episodios; no se publica.")
    enclosure = items[0].find("enclosure")
    if enclosure is None:
        raise SystemExit("El último episodio no tiene enclosure; no se publica.")
    tam = os.path.getsize(ruta_audio)
    if int(enclosure.attrib.get("length", "0")) != tam:
        raise SystemExit("El length del RSS no coincide con el MP3; no se publica.")
    if not enclosure.attrib.get("url", "").startswith(BASE_URL + "/"):
        raise SystemExit("La URL del enclosure no apunta al sitio esperado; no se publica.")
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    if not (items[0].findtext("itunes:duration", namespaces=ns) or "").strip():
        raise SystemExit("El último episodio no tiene duración; no se publica.")
    if (canal.findtext("itunes:block", namespaces=ns) or "") != "Yes":
        raise SystemExit("El RSS no conserva itunes:block Yes; no se publica.")
    print("Paquete RSS/audio validado.")


async def main():
    os.makedirs(EPISODES_DIR, exist_ok=True)
    ahora_local = datetime.now(TZ)

    guion, fuentes, avisos, informes, intentos = generar_y_validar(construir_prompt(ahora_local), ahora_local)

    palabras = len(guion.split())
    print(f"Guion: {palabras} palabras (~{palabras / 140:.1f} min)")
    with open(GUION_FILE, "w", encoding="utf-8") as f:
        f.write(guion + "\n\nFUENTES:\n" + "\n".join(f["raw"] for f in fuentes))
    escribir_validacion(guion, fuentes, avisos, informes, intentos)

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
    validar_paquete(ruta)


if __name__ == "__main__":
    asyncio.run(main())
