import os
import asyncio
import edge_tts
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import urllib.request
import google.generativeai as genai

# Fuentes de noticias en vivo para alimentar a Gemini
FUENTES_RSS = {
    "España y Mundo": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
    "Economía y Mercados": "https://cincodias.elpais.com/rss/cincodias/portada.xml",
    "Suiza y Ginebra": "https://www.swissinfo.ch/spa/rss/index.xml"
}

def recolectar_noticias_frescas():
    """Descarga los titulares reales del día para dárselos a Gemini."""
    texto_noticias = ""
    for categoria, url in FUENTES_RSS.items():
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            xml_data = urllib.request.urlopen(req, timeout=10).read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')[:5]
            
            texto_noticias += f"\n--- TITULARES DE {categoria.upper()} ---\n"
            for item in items:
                title = item.find('title')
                desc = item.find('description')
                t_text = title.text.strip() if title is not None and title.text else ""
                d_text = desc.text.strip() if desc is not None and desc.text else ""
                texto_noticias += f"- {t_text}: {d_text}\n"
        except Exception as e:
            print(f"Error descargando {categoria}: {e}")
            
    return texto_noticias

def obtener_briefing_ia():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Error: La variable GEMINI_API_KEY no está configurada en los Secrets de GitHub.")

    # 1. Obtenemos la información en tiempo real
    noticias_contexto = recolectar_noticias_frescas()
    fecha_hoy = datetime.now().strftime("%d de %B de %Y")

    # 2. Construimos el prompt con los datos reales incluidos
    prompt = f"""
Actúa como un locutor de radio profesional. Tu tarea es redactar un boletín diario de noticias en español largo, fluido y detallado para ser leído en voz alta.

Utiliza la siguiente información de última hora recopilada hoy ({fecha_hoy}):

{noticias_contexto}

ESTRUCTURA OBLIGATORIA DEL BOLETÍN (debe tener una longitud total de entre 600 y 800 palabras para durar entre 3 y 5 minutos hablados):
1. INTRODUCCIÓN: Saludo cordial de buenos días y presentación del boletín del {fecha_hoy}.
2. RESUMEN EJECUTIVO: Analiza y desarrolla los 4 titulares más importantes extraídos de los datos anteriores.
3. ESPAÑA Y MUNDO: Desarrolla las noticias internacionales y nacionales con contexto periodístico amplio.
4. ACTUALIDAD LOCAL:
   - Barcelona y Bilbao: Comenta la actualidad y noticias relevantes de ambas regiones.
   - Ginebra y Pays de Gex: Resume las novedades de Suiza/Ginebra e incluye una sugerencia cultural o de agenda local para hoy o los próximos días.
5. ECONOMÍA Y MERCADOS: Estado general de los mercados (menciona la evolución del Euro, Franco Suizo y Bolsas).
6. CIERRE: Despedida breve y profesional deseando un buen día a los oyentes.

REGLAS DE FORMATO PARA SÍNTESIS DE VOZ:
- No uses caracteres Markdown como '#', '*', '-', ni enlaces o URLs.
- Escribe todos los números largos o símbolos con letras (ejemplo: "cincuenta por ciento" en vez de "50%", "euros" en vez de "€").
- Escribe en párrafos continuos y con puntuación clara para favorecer las pausas naturales de lectura.
"""

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    response = model.generate_content(prompt)
    texto_final = response.text.strip()
    
    print(f"ÉXITO: Generado boletín con {len(texto_final)} caracteres.")
    return texto_final

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
    texto = obtener_briefing_ia()
    fecha_hoy_str = datetime.now().strftime("%Y-%m-%d")
    filename_mp3 = f"boletin_{fecha_hoy_str}.mp3"
    
    communicate = edge_tts.Communicate(texto, "es-ES-AlvaroNeural")
    await communicate.save(filename_mp3)
    
    actualizar_rss(filename_mp3, fecha_hoy_str)

if __name__ == "__main__":
    asyncio.run(main())
