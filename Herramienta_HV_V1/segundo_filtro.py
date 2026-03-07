import os
import json
from pathlib import Path

from extractor import extraer_texto
from ai_parser import parsear_cv
from pos_procesamiento import procesar as postprocesar
from detector_formato import detectar_formato


DIR_PRIMER_FILTRO = Path("Resultados Primer Filtro")
OUTPUT = "Resultados Segundo Filtro"

# INPUT puede ser inyectado externamente por primer_filtro.py
# Si es None, se resuelve automáticamente en main()
INPUT = None


def resolver_input() -> str:
    """
    Si INPUT fue inyectado por primer_filtro.py, lo usa directamente.
    Si no, busca la subcarpeta más reciente dentro de 'Resultados Primer Filtro'
    para evitar procesar vacantes anteriores por error.
    """
    if INPUT is not None:
        return INPUT

    if not DIR_PRIMER_FILTRO.exists():
        raise FileNotFoundError(
            f"No existe la carpeta '{DIR_PRIMER_FILTRO}'. "
            "Ejecuta primero el filtrador de HVs."
        )

    subcarpetas = [p for p in DIR_PRIMER_FILTRO.iterdir() if p.is_dir()]

    if not subcarpetas:
        raise FileNotFoundError(
            f"No se encontraron subcarpetas en '{DIR_PRIMER_FILTRO}'. "
            "Ejecuta primero el filtrador de HVs."
        )

    mas_reciente = max(subcarpetas, key=lambda p: p.stat().st_mtime)
    print(f"📂 Carpeta detectada automáticamente: {mas_reciente}")
    return str(mas_reciente)


def procesar(path):

    print("Procesando:", path)

    try:

        texto = extraer_texto(path)

        if not texto.strip():
            print("⚠️ No se pudo extraer texto:", path)
            return

        # detectar tipo de formato
        tipo_formato = detectar_formato(texto)

        if tipo_formato == "funcion_publica":
            print("⚠️ Formato Función Pública detectado. Omitiendo:", path)
            return

        # parsear con IA
        data = parsear_cv(texto)

        # asegurar estructura mínima
        if not isinstance(data, dict):
            print("⚠️ JSON inválido generado por IA:", path)
            return

        # agregar tipo de formato
        data["tipo_formato"] = tipo_formato

        # postprocesamiento
        data = postprocesar(data)

        nombre = os.path.basename(path)

        salida = os.path.join(
            OUTPUT,
            nombre + ".json"
        )

        with open(salida, "w", encoding="utf8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print("✅ Procesado:", nombre)

    except Exception as e:

        print("❌ Error procesando:", path)
        print(e)


def main():

    input_dir = resolver_input()

    # Limpiar carpeta output antes de cada corrida para no mezclar
    # JSONs de vacantes anteriores con los de la corrida actual
    if os.path.exists(OUTPUT):
        for f in os.listdir(OUTPUT):
            if f.endswith(".json"):
                os.remove(os.path.join(OUTPUT, f))
    os.makedirs(OUTPUT, exist_ok=True)

    if not os.path.exists(input_dir):
        print(f"⚠️ Carpeta input no existe: {input_dir}")
        return

    archivos = os.listdir(input_dir)

    if not archivos:
        print("⚠️ No hay archivos en la carpeta input")
        return

    for file in archivos:

        # ignorar archivos temporales de Word
        if file.startswith("~$"):
            continue

        if file.lower().endswith((".pdf", ".docx")):

            path = os.path.join(input_dir, file)

            procesar(path)

if __name__ == "__main__":
    main()
