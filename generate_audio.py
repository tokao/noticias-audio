import os
import asyncio
import edge_tts
from google import genai
from datetime import datetime, timezone

# Tu instrucción personalizada (Prompt) para controlar el brief
PROMPT_BOLETIN = """
Busca las noticias más importantes de las últimas 24 horas y redacta un boletín diario en español optimizado para ser leído en voz alta.
Estructura el texto en las siguientes secciones claras y concisas:
1. Resumen ejecutivo (3 a 5 puntos clave).
2. España y Mundo.
3. Barcelona y Bilbao.
4. Ginebra y Pays de Gex (incluye un pincelada cultural relevante para hoy o los próximos días).
5. Breve resumen de Mercados (EUR/USD, EUR/CHF, bolsas).

Notas de estilo:
- Usa un tono divulgativo, fluido y profesional pero natural para ser escuchado en audio.
- Evita incluir enlaces HTTP, caracteres extraños o símbolos como '#' o '*'.
- Longitud total aproximada: 3 a 5 minutos de lectura.
"""

def obtener_briefing_ia():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Hola. No se encontró la clave de la API de Gemini."

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=PROMPT_BOLETIN,
    )
    return response.text

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
    <description>Boletín diario personalizado generado por IA.</description>
{nuevo_item}
  </channel>
</rss>"""
        with open(rss_file, "w", encoding="utf-8") as f:
            f.write(full_rss)

async def main():
    texto = obtener_briefing_ia()
    
    fecha_hoy_str = datetime.now().strftime("%Y-%m-%d")
    filename_mp3 = f"boletin_{fecha_hoy_str}.mp3"
    
    # Generar el audio
    communicate = edge_tts.Communicate(texto, "es-ES-AlvaroNeural")
    await communicate.save(filename_mp3)
    
    actualizar_rss(filename_mp3, fecha_hoy_str)

if __name__ == "__main__":
    asyncio.run(main())
