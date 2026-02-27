"""
Pipeline de procesamiento de HVs (Hojas de Vida) en PDF.

Flujo:
  PDF → extracción con manejo de columnas → detección de formato
      ├── Formato Único Función Pública → parser_funcion_publica.py
      └── CV libre → limpieza → secciones → estructuración JSON

El JSON resultante está pensado para ser usado directamente en ranking
automático y matching con vacantes.
"""

import json
import os

from extractor_texto import extraer_texto_pdf
from limpiar import limpiar_texto
from seccionesHV_nlp import dividir_secciones
from estructurar_cv import estructurar_cv
from parser_funcion_publica import es_formato_funcion_publica, parsear_cv_funcion_publica

INPUT_CARPETA = "input"
OUTPUT_CARPETA = "output"


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def limpiar_output():
    """Elimina archivos existentes en la carpeta de salida."""
    os.makedirs(OUTPUT_CARPETA, exist_ok=True)
    for archivo in os.listdir(OUTPUT_CARPETA):
        ruta = os.path.join(OUTPUT_CARPETA, archivo)
        if os.path.isfile(ruta):
            os.remove(ruta)


def guardar_json(nombre_archivo, datos):
    """Guarda el dict como JSON en la carpeta de salida."""
    nombre_sin_ext = os.path.splitext(nombre_archivo)[0]
    os.makedirs(OUTPUT_CARPETA, exist_ok=True)
    ruta_salida = os.path.join(OUTPUT_CARPETA, nombre_sin_ext + ".json")
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)
    print(f"Guardado en: {ruta_salida}")


# ---------------------------------------------------------------------------
# PIPELINE PRINCIPAL
# ---------------------------------------------------------------------------

def procesar_pdf(ruta_pdf, nombre_archivo):
    """Procesa un único PDF y retorna el dict estructurado."""

    print(f"\nProcesando: {nombre_archivo}")

    # 1. Extracción (maneja dos columnas)
    texto_crudo = extraer_texto_pdf(ruta_pdf)
    if not texto_crudo.strip():
        print("No se pudo extraer texto del archivo.")
        return None

    # 2. Detectar formato especial: Función Pública
    if es_formato_funcion_publica(texto_crudo):
        print("Formato Único Función Pública detectado → parser especializado")
        resultado = parsear_cv_funcion_publica(texto_crudo)
        n_empleos = resultado.get("cantidad_empleos", 0)
        años_exp = resultado.get("años_experiencia_total", 0)
        print(f"Empleos detectados: {n_empleos} | Experiencia total: {años_exp} años")
        return resultado

    # 3. CV libre: limpieza
    texto_limpio = limpiar_texto(texto_crudo)

    # 4. Detección de secciones por encabezados (máquina de estados)
    secciones = dividir_secciones(texto_limpio)
    print(f"Secciones detectadas: { {k: len(v) for k, v in secciones.items()} }")

    # 5. Estructuración en JSON para ranking/matching
    cv_estructurado = estructurar_cv(secciones, texto_crudo)

    n_empleos = cv_estructurado.get("cantidad_empleos", 0)
    años_exp = cv_estructurado.get("años_experiencia_total", 0)
    print(f"Empleos detectados: {n_empleos} | Experiencia total: {años_exp} años")

    return cv_estructurado


def procesar_carpeta():
    """Procesa todos los PDFs en la carpeta de entrada."""
    os.makedirs(INPUT_CARPETA, exist_ok=True)
    limpiar_output()

    archivos_pdf = [f for f in os.listdir(INPUT_CARPETA) if f.lower().endswith(".pdf")]

    if not archivos_pdf:
        print(f"No se encontraron PDFs en '{INPUT_CARPETA}/'")
        return

    print(f"Procesando {len(archivos_pdf)} archivo(s)...\n{'─'*50}")

    for archivo in archivos_pdf:
        ruta = os.path.join(INPUT_CARPETA, archivo)
        resultado = procesar_pdf(ruta, archivo)
        if resultado:
            guardar_json(archivo, resultado)

    print(f"\n{'─'*50}")
    print(f"Proceso completado. Resultados en '{OUTPUT_CARPETA}/'")


if __name__ == "__main__":
    procesar_carpeta()
