import asyncio
import os
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from google import genai

# Inicializar cliente con el nuevo SDK oficial
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


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
            # Soporte estándar para elementos RSS <item><title>
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

    # Ejemplo de fuentes RSS (Asegúrate de verificar que las URLs respondan 200 OK)
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
        # Generar contenido usando el modelo Gemini 2.5 Flash
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"Error generando contenido con Gemini: {e}")
        raise e


async def main():
    print("Obteniendo texto del briefing...")
    texto = obtener_briefing()
