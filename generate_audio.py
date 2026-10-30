import asyncio
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

import edge_tts

# --- Configuración ---------------------------------------------------------
# URL pública donde se sirve el repo (GitHub Pages). Sin barra final.
BASE_URL = os.environ.get("BASE_URL", "https://tokao.github.io/noticias-audio").rstrip("/")
GITHUB_MODEL = os.environ.get("GITHUB_MODEL", "openai/gpt-4o-mini")
VOICE = "es-ES-AlvaroNeural"

EPISODES_DIR = "episodes"        # aquí van los mp3, uno por día
EPISODES_JSON = "episodes.json"  # historial de episodios (para regenerar el feed)
RSS_FILE = "rss.xml"
MAX_EPISODES = 30                # se borran los más antiguos para no inflar el repo

PODCAST_TITLE = "Boletín Diario de Noticias"
PODCAST_DESC = "Boletín diario personalizado generado automáticamente."
PODCAST_AUTHOR = "tokao"


# --- Noticias y guion ------------------------------------------------------
def obtener_noticias_rss(url):
    """Obtiene y extrae los títulos de un feed RSS."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            root = ET.fromstring(response.read())
        titulares = [
            item.findtext("title").strip()
            for item in root.findall(".//item")[:5]
            if item.findtext("title")
        ]
        return "\n".join(f"- {t}" for t in titulares)
    except Exception as e:
        print(f"Advertencia cargando fuente ({url}): {e}")
        return "Noticias destacadas del día no disponibles en este momento."


def obtener_briefing():
    titulares = obtener_noticias_rss("https://feeds.bbci.co.uk/mundo/rss.xml")
    prompt = f"""
Eres un locutor de radio profesional. Sintetiza las siguientes noticias en un guion breve y fluido
listo para ser leído en un podcast informativo diario de 2 minutos.

Titulares destacados:
{titulares}

Redacta el texto de forma clara, natural y concisa en español.
Devuelve SOLO el texto que se va a leer en voz alta: sin markdown, sin asteriscos,
sin títulos y sin acotaciones como [música] o (pausa).
"""
    # 1) GitHub Models (gratis en Actions con el GITHUB_TOKEN)
    if os.environ.get("GITHUB_TOKEN"):
        try:
            texto = generar_con_github_models(prompt)
            print("Guion generado con GitHub Models.")
            return limpiar_texto(texto)
        except Exception as e:
            print(f"GitHub Models no disponible: {str(e)[:200]}")

    # 2) Último recurso: leer los titulares tal cual
    print("Usando titulares sin resumir.")
    return "Buenos días. Estos son los titulares de hoy.\n" + titulares.replace("- ", "")


def generar_con_github_models(prompt):
    body = json.dumps({
        "model": GITHUB_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://models.github.ai/inference/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def limpiar_texto(texto):
    """Quita restos de markdown/acotaciones que el TTS leería en voz alta."""
    texto = re.sub(r"\[[^\]]*\]|\([^)]*(música|pausa|sonido)[^)]*\)", "", texto, flags=re.I)
    texto = re.sub(r"[*#_`>]+", "", texto)
    return re.sub(r"[ \t]+", " ", texto).strip()


async def generar_audio(texto, ruta):
    print(f"Generando {ruta}...")
    await edge_tts.Communicate(texto, VOICE).save(ruta)


# --- Episodios y feed ------------------------------------------------------
def cargar_episodios():
    if os.path.exists(EPISODES_JSON):
        with open(EPISODES_JSON, encoding="utf-8") as f:
            return json.load(f)
    return []


def guardar_episodios(episodios):
    with open(EPISODES_JSON, "w", encoding="utf-8") as f:
        json.dump(episodios, f, ensure_ascii=False, indent=2)


def podar_episodios(episodios):
    """Mantiene solo los últimos MAX_EPISODES y borra los mp3 sobrantes."""
    episodios = episodios[:MAX_EPISODES]
    vigentes = {e["file"] for e in episodios}
    for nombre in os.listdir(EPISODES_DIR):
        if nombre.endswith(".mp3") and nombre not in vigentes:
            os.remove(os.path.join(EPISODES_DIR, nombre))
            print(f"Borrado episodio antiguo: {nombre}")
    return episodios


def generar_rss(episodios):
    ahora = format_datetime(datetime.now(timezone.utc), usegmt=True)
    imagen = ""
    if os.path.exists("cover.png"):
        imagen = f'\n    <itunes:image href="{BASE_URL}/cover.png"/>'

    items = []
    for e in episodios:
        url = f"{BASE_URL}/{EPISODES_DIR}/{e['file']}"
        items.append(f"""    <item>
      <title>{escape(e['title'])}</title>
      <description>{escape(e['description'])}</description>
      <pubDate>{e['pubDate']}</pubDate>
      <guid isPermaLink="false">{e['guid']}</guid>
      <enclosure url="{url}" length="{e['length']}" type="audio/mpeg"/>
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
    ahora = datetime.now(timezone.utc)
    fecha = ahora.strftime("%Y-%m-%d")
    archivo = f"boletin_{fecha}.mp3"
    ruta = os.path.join(EPISODES_DIR, archivo)

    print("Obteniendo texto del briefing...")
    texto = obtener_briefing()
    print("-" * 40, texto, "-" * 40, sep="\n")

    await generar_audio(texto, ruta)

    episodio = {
        "guid": f"boletin-{fecha}",
        "file": archivo,
        "title": f"Boletín {fecha}",
        "description": texto[:300] + ("..." if len(texto) > 300 else ""),
        "pubDate": format_datetime(ahora, usegmt=True),
        "length": os.path.getsize(ruta),
    }

    # Si se ejecuta dos veces el mismo día, sustituye el episodio de ese día
    episodios = [e for e in cargar_episodios() if e["guid"] != episodio["guid"]]
    episodios.insert(0, episodio)
    episodios = podar_episodios(episodios)

    guardar_episodios(episodios)
    generar_rss(episodios)


if __name__ == "__main__":
    asyncio.run(main())
