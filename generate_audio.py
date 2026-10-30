import asyncio
import os
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
from google import genai
import edge_tts

# Inicializar cliente con el nuevo SDK oficial
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Configuración de voz para edge-tts
VOICE = "es-ES-AlvaroNeural"  # Opciones: "es-ES-ElviraNeural", "es-MX-JorgeNeural", etc.
AUDIO_FILE = "noticias.mp3"
RSS_FILE = "rss.xml"


def obtener_noticias_rss(url):
    """Obtiene y extrae los títulos de un feed RSS de forma segura."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)

            titulares = []
            for item in root.findall(".//item")[:5]:
                title = item.find("title")
                if title is not None and title.text:
                    titulares.append(title.text.strip())

            return "\n".join(f"- {t}" for t in titulares)
    except urllib.error.HTTPError as e:
        print(f"Error HTTP cargando fuente ({url}): {e}")
        return "No se pudieron obtener titulares de esta fuente."
    except Exception as e:
        print(f"Error cargando fuente ({url}): {e}")
        return "No se pudieron obtener titulares de esta fuente."


def obtener_briefing():
    """Recopila titulares y genera el resumen diario utilizando Gemini."""
    rss_suiza = "https://www.swissinfo.ch/spa/rss"
    titulares_suiza = obtener_noticias_rss(rss_suiza)

    prompt = f"""
    Eres un locutor de radio profesional. Sintetiza las siguientes noticias en un guion breve y fluido 
    listo para ser leído en un podcast informativo diario de 2 minutos.

    Titulares destacados de la región:
    {titulares_suiza}

    Redacta el texto de forma clara, natural y concisa en español.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"Error generando contenido con Gemini: {e}")
        raise e


async def generar_audio(texto):
    """Convierte el texto del briefing a un archivo MP3 usando edge-tts."""
    print("Generando archivo de audio MP3...")
    communicate = edge_tts.Communicate(texto, VOICE)
    await communicate.save(AUDIO_FILE)
    print(f"Audio guardado exitosamente en: {AUDIO_FILE}")


def actualizar_rss(texto_briefing):
    """Genera o actualiza el archivo
