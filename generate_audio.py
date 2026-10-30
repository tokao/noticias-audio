import os
import asyncio
import edge_tts
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import urllib.request

# Texto o prompt para la IA
PROMPT_BOLETIN = """
Redacta un boletín diario de noticias en español para ser leído en voz alta.
Estructura clara:
1. Resumen ejecutivo (3-4 puntos).
2. Noticias principales de España, Barcelona, Bilbao y Ginebra.
3. Resumen de mercados financieros (EUR/USD, EUR/CHF).
4. Un apunte de la agenda cultural en Ginebra.

Nota: No uses caracteres raros, ni símbolos Markdown como '#', '*', ni URLs HTTP. Tono fluido y directo para audio.
"""

def obtener_titulares_rss():
    """Respaldo gratuito sin API key en caso de que falle Gemini"""
    titulares = ["Hola, este es tu boletín diario de noticias."]
    urls = [
        ("España y Mundo", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"),
        ("Ginebra y Suiza", "https://www.swissinfo.ch/spa/rss/index.xml")
    ]
    for cat, url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            xml_data = urllib.request.urlopen(req, timeout=10).read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')[:3]
            titulares.append(f"Noticias de {cat}:")
            for item in items:
                t = item.find('title')
                if t is not None and t.text:
                    titulares.append(f"- {t.text.strip()}")
        except Exception as e:
            print(f"Error cargando RSS {cat}: {e}")
    return "\n".join(titulares)

def obtener_briefing():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY no encontrada. Generando resumen con RSS...")
        return obtener_titulares_rss()

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=PROMPT_BOLETIN,
        )
        return response.text
    except Exception as e:
        print(f"Error llamando a la API de Gemini: {e}")
        print("Usando fuente RSS de respaldo...")
        return obtener_titulares_rss()

def actualizar_rss(filename_mp3, fecha_str):
    rss_file = "rss.xml"
    now_utc = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    mp3_url = f"https://tokao.github.io/noticias-audio/{filename_mp3}"
    
    nuevo_item = f"""    <item>
      <title>Boletín {fecha_str}</title>
      <description>Resumen diario de noticias e información cultural.</description>
      <pubDate>{now_utc}</pubDate>
      <enclosure url="{mp3_url}" length="1000000" type="audio/mpeg"/>
      <guid>{mp3_url}</guid>
    </item>"""

    if os.path.exists(rss_file):
        with open(rss_file, "r", encoding="utf-8") as f:
            content = f.read()
        if "<channel>" in content:
            content = content.replace("<channel>", f"<channel>\n{nuevo_item}")
        with open(rss_file, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        full_rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Boletín Diario de Noticias</title>
    <link>https://tokao.github.io/noticias-audio/</link>
    <language>es</language>
    <description>Boletín diario personalizado generado automáticamente.</description>
{nuevo_item}
  </channel>
</rss>"""
        with open(rss_file, "w", encoding="utf-8") as f:
            f.write(full_rss)

async def main():
    texto = obtener_briefing()
    fecha_hoy_str = datetime.now().strftime("%Y-%m-%d")
    filename_mp3 = f"boletin_{fecha_hoy_str}.mp3"
    
    communicate = edge_tts.Communicate(texto, "es-ES-AlvaroNeural")
    await communicate.save(filename_mp3)
    
    actualizar_rss(filename_mp3, fecha_hoy_str)

if __name__ == "__main__":
    asyncio.run(main())
