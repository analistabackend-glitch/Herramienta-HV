import os
import json

from extractor import extraer_texto
from ai_parser import parsear_cv
from pos_procesamiento import procesar as postprocesar
from detector_formato import detectar_formato


INPUT = "input"
OUTPUT = "output"


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

    # crear carpeta output si no existe
    os.makedirs(OUTPUT, exist_ok=True)

    archivos = os.listdir(INPUT)

    if not archivos:
        print("⚠️ No hay archivos en la carpeta input")
        return

    for file in archivos:

        if file.lower().endswith((".pdf", ".docx")):

            path = os.path.join(INPUT, file)

            procesar(path)


if __name__ == "__main__":
    main()