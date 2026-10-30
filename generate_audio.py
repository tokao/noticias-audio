import os
import asyncio
import edge_tts
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import urllib.request
import google.generativeai as genai

# Fuentes de noticias para nutrir a la IA
FUENTES_RSS = {
    "España y Mundo": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
    "Economía": "https://cincodias.elpais.com/rss/cincodias/portada.xml",
    "Suiza y Ginebra": "https://www.swissinfo.ch/spa/rss/index.xml"
}

def recolectar_noticias():
    texto_noticias = ""
    for categoria, url in FUENTES_RSS.items():
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            xml_data = urllib.request.urlopen(req, timeout=10).read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')[:4]
            texto_noticias += f"\n--- {categoria.upper()} ---\n"
            for item in items:
                title = item.find('title')
                if title is not None and title.text:
                    texto_noticias += f"- {title.text.strip()}\n"
        except Exception as e:
            print(f"Error cargando {categoria}: {e}")
    return texto_noticias

def obtener_briefing():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("No se encontró la clave GEMINI_API_KEY en las variables de entorno de GitHub.")

    noticias = recolectar_noticias()
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")

    prompt = f"""
Actúa como un locutor de radio profesional. Redacta un boletín diario de noticias extenso y fluido en español para ser leído en voz alta.

Utiliza como base estos titulares de hoy ({fecha_hoy}):
{noticias}

REQUISITO DE LONGITUD: El texto debe tener entre 600 y 800 palabras (duración de 3 a 5 minutos hablados).

ESTRUCTURA DEL BOLETÍN:
1. INTRODUCCIÓN: Saludo inicial y fecha.
2. RESUMEN EJECUTIVO: 4 puntos clave desarrollados.
3. ESPAÑA Y MUNDO: Noticias internacionales y de España detalladas.
4. ACTUALIDAD LOCAL:
   - Barcelona y Bilbao: Estado y noticias de ambas regiones.
   - Ginebra y Pays de Gex: Actualidad suiza e incluye una recomendación de agenda cultural para los próximos días.
5. MERCADOS FINANCIEROS: Situación económica, EUR/USD, EUR/CHF y bolsas.
6. CIERRE: Despedida profesional.

REGLAS DE AUDIO:
- No uses Markdown (#, *, -), ni caracteres especiales, ni URLs.
- Escribe los números con palabras para facilitar la lectura.
- Redacta párrafos naturales con puntuación clara.
"""

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    
    texto = response.text.strip()
    print(f"Texto generado con éxito: {len(texto)} caracteres.")
    return texto

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
    <itunes:image href="https://tokao.github.io/noticias-audio/cover.png"/>
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
