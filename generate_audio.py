import asyncio
import edge_tts
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import urllib.request
import os

# Fuentes de noticias públicas para extraer titulares reales
FEEDS_NOTICIAS = {
    "España y Mundo": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
    "Ginebra y Suiza": "https://www.swissinfo.ch/spa/rss/index.xml"
}

def obtener_titulares():
    titulares = []
    for categoria, url in FEEDS_NOTICIAS.items():
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            xml_data = urllib.request.urlopen(req, timeout=10).read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')[:4] # Extrae los 4 titulares principales
            
            titulares.append(f"Noticias de {categoria}:")
            for item in items:
                title = item.find('title')
                if title is not None and title.text:
                    titulares.append(f"- {title.text.strip()}")
        except Exception as e:
            print(f"Error obteniendo noticias de {categoria}: {e}")
            
    if not titulares:
        return "Hola. No se pudieron recuperar los titulares del día de hoy."
        
    fecha_hoy = datetime.now().strftime("%d de %m de %Y")
    texto_final = f"Hola, este es tu boletín diario de noticias del {fecha_hoy}.\n\n" + "\n".join(titulares)
    return texto_final

def actualizar_rss(filename_mp3, fecha_str):
    rss_file = "rss.xml"
    now_utc = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    mp3_url = f"https://tokao.github.io/noticias-audio/{filename_mp3}"
    
    nuevo_item = f"""    <item>
      <title>Boletín {fecha_str}</title>
      <description>Resumen diario de noticias del {fecha_str}</description>
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
    <description>Boletín de noticias en audio diario.</description>
{nuevo_item}
  </channel>
</rss>"""
        with open(rss_file, "w", encoding="utf-8") as f:
            f.write(full_rss)

async def main():
    texto = obtener_titulares()
    
    # Nombre del archivo con la fecha de hoy
    fecha_hoy_str = datetime.now().strftime("%Y-%m-%d")
    filename_mp3 = f"boletin_{fecha_hoy_str}.mp3"
    
    # Generar el archivo de audio con Microsoft Edge TTS
    communicate = edge_tts.Communicate(texto, "es-ES-AlvaroNeural")
    await communicate.save(filename_mp3)
    
    # Actualizar la lista RSS del podcast
    actualizar_rss(filename_mp3, fecha_hoy_str)

if __name__ == "__main__":
    asyncio.run(main())
