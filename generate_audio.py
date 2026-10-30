import asyncio
import edge_tts

# Texto del boletín
TEXTO = """
Hola, este es tu boletín diario. 
Aquí tienes el resumen con las noticias de hoy en Mundo, España, Barcelona, Bilbao y Ginebra.
"""

async def main():
    # Usamos una voz neutra y clara en español ('es-ES-AlvaroNeural')
    communicate = edge_tts.Communicate(TEXTO, "es-ES-AlvaroNeural")
    await communicate.save("boletin_diario.mp3")

if __name__ == "__main__":
    asyncio.run(main())
