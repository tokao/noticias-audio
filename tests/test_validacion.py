import copy
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

# El paquete real se instala en GitHub Actions; en las pruebas locales no se genera audio.
edge = types.ModuleType("edge_tts")
edge.Communicate = object
sys.modules.setdefault("edge_tts", edge)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate_audio as g


SECCIONES = [
    ("S1", "Mundo"),
    ("S2", "España"),
    ("S3", "Barcelona"),
    ("S4", "Bilbao y Bizkaia"),
    ("S5", "Ginebra y alrededores"),
    ("S6", "Mercados"),
    ("S7", "Tiempo"),
]
FRASES = {
    "S1": "La autoridad internacional confirmó hoy una medida de alto impacto global y explicó alcance, calendario y responsables con datos actualizados durante la jornada",
    "S2": "El Gobierno español anunció hoy una decisión con efectos inmediatos",
    "S3": "Barcelona confirmó hoy un cambio importante en la movilidad urbana",
    "S4": "Bilbao y Bizkaia registraron hoy una incidencia relevante en servicios públicos",
    "S5": "Ginebra informó hoy de una alteración importante en el transporte público",
    "S6": "Los principales índices cerraron ayer con movimientos moderados según la fuente",
    "S7": "La previsión oficial indica lluvia débil y temperaturas suaves para hoy",
}
EVIDENCIAS = {
    sid: (
        f"{FRASES[sid]}. La fuente explica que la información fue actualizada durante la jornada "
        "y añade datos verificables sobre alcance, calendario y responsables."
    )
    for sid, _ in SECCIONES
}
RELLENO = " ".join([
    "La redacción ofrece contexto adicional sobre antecedentes, reacciones, calendario y próximos pasos."
] * 5)
PAGINAS = {
    f"https://fuente.test/{sid}": (
        '<html><head><meta property="article:published_time" content="2026-10-31T07:00:00+01:00"></head>'
        f"<body><article>{EVIDENCIAS[sid]} {RELLENO}</article></body></html>"
    )
    for sid, _ in SECCIONES
}


def fuentes_prueba():
    return [
        {
            "id": sid,
            "seccion": seccion,
            "frase": FRASES[sid],
            "medio": "Medio de prueba",
            "url": f"https://fuente.test/{sid}",
            "fecha": "2026-10-31",
            "evidencia": EVIDENCIAS[sid],
            "traduccion": EVIDENCIAS[sid],
            "raw": sid,
        }
        for sid, seccion in SECCIONES
    ]


def guion_prueba():
    guion = "Buenos días. Este es un guion de prueba.\n\n"
    for sid, seccion in SECCIONES:
        guion += f"{seccion}:\n{FRASES[sid]}. [{sid}]\n\n"
    return guion + "Cierre:\nFin del resumen."


class ValidacionTest(unittest.TestCase):
    def setUp(self):
        self.ahora = datetime(2026, 10, 31, 5, 30, tzinfo=ZoneInfo("Europe/Zurich"))
        self.guion = guion_prueba()
        self.fuentes = fuentes_prueba()

    def validar(self, fuentes=None):
        with patch.object(g, "descargar_fuente", side_effect=lambda url: PAGINAS[url]):
            return g.validar_guion(self.guion, fuentes or self.fuentes, self.ahora, self.guion)

    def test_fuente_con_evidencia_y_fecha_pasa(self):
        errores, _, informes = self.validar()
        self.assertEqual(errores, [])
        self.assertEqual(len(informes), 7)

    def test_afirmacion_inventada_con_url_valida_falla(self):
        fuentes = copy.deepcopy(self.fuentes)
        fuentes[0]["evidencia"] = (
            "La autoridad internacional confirmó hoy una medida falsa de alto impacto global "
            "con datos inventados y alcance mundial."
        )
        fuentes[0]["traduccion"] = fuentes[0]["evidencia"]
        errores, _, _ = self.validar(fuentes)
        self.assertTrue(any("evidencia no aparece" in e for e in errores), errores)

    def test_titular_no_vinculado_al_guion_falla(self):
        fuentes = copy.deepcopy(self.fuentes)
        fuentes[1]["frase"] = "Este titular no aparece en el guion y no puede vincularse con la noticia"
        errores, _, _ = self.validar(fuentes)
        self.assertTrue(any("frase de enlace" in e for e in errores), errores)


    def test_evidencia_real_pero_no_relacionada_con_el_titular_falla(self):
        fuentes = copy.deepcopy(self.fuentes)
        fuentes[0]["evidencia"] = (
            "El club local presentó una exposición fotográfica sobre barrios antiguos "
            "con entrada gratuita durante el fin de semana."
        )
        fuentes[0]["traduccion"] = fuentes[0]["evidencia"]
        paginas = dict(PAGINAS)
        paginas[fuentes[0]["url"]] = (
            '<html><head><meta property="article:published_time" content="2026-10-31T07:00:00+01:00"></head>'
            f"<body><article>{fuentes[0]['evidencia']} {RELLENO}</article></body></html>"
        )
        with patch.object(g, "descargar_fuente", side_effect=lambda url: paginas[url]):
            errores, _, _ = g.validar_guion(self.guion, fuentes, self.ahora, self.guion)
        self.assertTrue(any("no parece respaldar" in e for e in errores), errores)


    def test_parrafo_mezcla_frase_verificada_con_afirmacion_inventada(self):
        guion = self.guion.replace(
            FRASES["S1"] + ". [S1]",
            FRASES["S1"] + ". Además, una autoridad distinta prohibió todos los vuelos nocturnos durante un mes. [S1]",
        )
        with patch.object(g, "descargar_fuente", side_effect=lambda url: PAGINAS[url]):
            errores, _, _ = g.validar_guion(guion, self.fuentes, self.ahora, guion)
        self.assertTrue(any("contenido no cubierto" in e for e in errores), errores)

    def test_negacion_invertida_falla(self):
        fuentes = copy.deepcopy(self.fuentes)
        fuentes[0]["evidencia"] = (
            "La autoridad internacional no confirmó hoy una medida de alto impacto global "
            "y explicó alcance, calendario y responsables con datos actualizados durante la jornada."
        )
        fuentes[0]["traduccion"] = fuentes[0]["evidencia"]
        paginas = dict(PAGINAS)
        paginas[fuentes[0]["url"]] = (
            '<html><head><meta property="article:published_time" content="2026-10-31T07:00:00+01:00"></head>'
            f"<body><article>{fuentes[0]['evidencia']} {RELLENO}</article></body></html>"
        )
        with patch.object(g, "descargar_fuente", side_effect=lambda url: paginas[url]):
            errores, _, _ = g.validar_guion(self.guion, fuentes, self.ahora, self.guion)
        self.assertTrue(any("polaridad" in e for e in errores), errores)

    def test_cifra_alterada_falla(self):
        fuentes = copy.deepcopy(self.fuentes)
        fuentes[0]["frase"] = "La autoridad internacional confirmó hoy una medida con 5 medidas de alto impacto global"
        fuentes[0]["evidencia"] = "La autoridad internacional confirmó hoy una medida con 9 medidas de alto impacto global"
        fuentes[0]["traduccion"] = fuentes[0]["evidencia"]
        guion = self.guion.replace(FRASES["S1"], fuentes[0]["frase"])
        paginas = dict(PAGINAS)
        paginas[fuentes[0]["url"]] = (
            '<html><head><meta property="article:published_time" content="2026-10-31T07:00:00+01:00"></head>'
            f"<body><article>{fuentes[0]['evidencia']} {RELLENO}</article></body></html>"
        )
        with patch.object(g, "descargar_fuente", side_effect=lambda url: paginas[url]):
            errores, _, _ = g.validar_guion(guion, fuentes, self.ahora, guion)
        self.assertTrue(any("cifras" in e for e in errores), errores)

    def test_fecha_futura_falla(self):
        fuentes = copy.deepcopy(self.fuentes)
        fuentes[0]["fecha"] = "2026-11-01"
        paginas = dict(PAGINAS)
        paginas[fuentes[0]["url"]] = paginas[fuentes[0]["url"]].replace("2026-10-31", "2026-11-01")
        with patch.object(g, "descargar_fuente", side_effect=lambda url: paginas[url]):
            errores, _, _ = g.validar_guion(self.guion, fuentes, self.ahora, self.guion)
        self.assertTrue(any("fecha futura" in e for e in errores), errores)

    def test_texto_seccion_no_incluye_cierre(self):
        guion = """Tiempo:
Previsión breve. [S7]

Cierre:
Un párrafo largo de cierre sin fuente """ + " ".join(["extra"] * 30)
        self.assertNotIn("Un párrafo largo", g.texto_seccion(guion, "Tiempo"))


    def test_fuente_inaccesible_obliga_a_omitir(self):
        with patch.object(g, "descargar_fuente", side_effect=g.FuenteNoVerificable("HTTP 404")):
            errores, _, _ = g.validar_guion(self.guion, self.fuentes, self.ahora, self.guion)
        self.assertTrue(any("fuente inaccesible" in e for e in errores), errores)




    def test_evidencia_en_ingles_con_traduccion_controlada_pasa(self):
        evidencia = (
            "Geneva transport authorities confirmed today that the tram service will change "
            "during next week and published the official timetable update."
        )
        traduccion = (
            "Las autoridades de transporte de Ginebra confirmaron hoy que el servicio de tranvía "
            "cambiará durante la próxima semana y publicaron la actualización oficial de horarios."
        )
        frase = (
            "Las autoridades de transporte de Ginebra confirmaron hoy que el servicio de tranvía "
            "cambiará durante la próxima semana."
        )
        fuentes = copy.deepcopy(self.fuentes)
        fuentes[4]["frase"] = frase
        fuentes[4]["evidencia"] = evidencia
        fuentes[4]["traduccion"] = traduccion
        guion = self.guion.replace(FRASES["S5"], frase)
        paginas = dict(PAGINAS)
        paginas[fuentes[4]["url"]] = (
            '<html><head><meta property="article:published_time" content="2026-10-31T07:00:00+01:00"></head>'
            f"<body><article>{evidencia} {RELLENO}</article></body></html>"
        )
        with patch.object(g, "descargar_fuente", side_effect=lambda url: paginas[url]):
            errores, _, _ = g.validar_guion(guion, fuentes, self.ahora, guion)
        self.assertEqual(errores, [])

    def test_secciones_tranquilas_pueden_quedar_sin_fuentes(self):
        guion = "Buenos días.\n\n"
        for _, seccion in SECCIONES:
            guion += f"{seccion}:\nSin novedades verificadas.\n\n"
        guion += "Cierre:\nFin."
        errores, _, informes = g.validar_guion(guion, [], self.ahora, guion)
        self.assertEqual(errores, [])
        self.assertEqual(informes, [])


    def test_prompt_mercados_no_usa_hora_fija_de_cierre(self):
        prompt = g.construir_prompt(datetime(2026, 10, 30, 5, 30, tzinfo=ZoneInfo("Europe/Zurich")))
        self.assertNotIn("22:00", prompt)
        self.assertNotIn("17:30", prompt)
        self.assertIn("Nueva York", prompt)
        self.assertIn("fecha del último cierre", prompt)

    def test_separar_respuesta_quita_marcas_y_estructura_fuentes(self):
        respuesta = (
            "GUION:\nMundo:\n" + FRASES["S1"] + ". [S1]\n\nFUENTES:\n"
            + f"S1 | Mundo | {FRASES['S1']} | Medio | https://fuente.test/S1 | 2026-10-31 | {EVIDENCIAS['S1']} | {EVIDENCIAS['S1']}"
        )
        guion, fuentes, marcado = g.separar_respuesta(respuesta)
        self.assertNotIn("[S1]", guion)
        self.assertIn("[S1]", marcado)
        self.assertEqual(fuentes[0]["url"], "https://fuente.test/S1")
        self.assertEqual(fuentes[0]["evidencia"], EVIDENCIAS["S1"])
        self.assertEqual(fuentes[0]["traduccion"], EVIDENCIAS["S1"])


if __name__ == "__main__":
    unittest.main()
