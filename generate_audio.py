import asyncio
import edge_tts
from datetime import datetime, timezone

TEXTO = """
Hola, este es tu boletín diario. 
Aquí tienes el resumen con las noticias de hoy en Mundo, España, Barcelona, Bilbao y Ginebra.
"""

def generar_rss():
    ahora = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")
    
    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Boletín Diario de Noticias</title>
    <link>https://tokao.github.io/noticias-audio/</link>
    <language>es</language>
    <description>Boletín de noticias en audio generado automáticamente.</description>
    <item>
      <title>Boletín del {fecha_hoy}</title>
      <description>Noticias de hoy en Mundo, España, Barcelona, Bilbao y Ginebra.</description>
      <pubDate>{ahora}</pubDate>
      <enclosure url="https://tokao.github.io/noticias-audio/boletin_diario.mp3" length="1000000" type="audio/mpeg"/>
      <guid>https://tokao.github.io/noticias-audio/boletin_diario.mp3?v={datetime.now().timestamp()}</guid>
    </item>
  </channel>
</rss>"""

    with open("rss.xml", "w", encoding="utf-8") as f:
        f.write(rss_content)

async def main():
    communicate = edge_tts.Communicate(TEXTO, "es-ES-AlvaroNeural")
    await communicate.save("boletin_diario.mp3")
    generar_rss()

if __name__ == "__main__":
    asyncio.run(main())
