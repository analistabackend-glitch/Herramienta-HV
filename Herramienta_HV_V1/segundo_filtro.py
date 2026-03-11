import os
import re
import json
from pathlib import Path

from extractor import extraer_texto
from ai_parser import parsear_cv, es_hoja_de_vida
from pos_procesamiento import procesar as postprocesar
from detector_formato import detectar_formato


DIR_PRIMER_FILTRO = Path("Resultados Primer Filtro")
OUTPUT = "Resultados Segundo Filtro"   # sobreescrito por primer_filtro.py como str(dir_segundo)

# INPUT puede ser inyectado externamente por primer_filtro.py
INPUT = None

# Lista de archivos que NO son HV, inyectada al tercer filtro / Excel unificado
ARCHIVOS_NO_HV: list = []

# Callbacks para la barra 2 de la GUI (inyectados por primer_filtro.py)
_progress_ia_cb: object = None       # callable(actual, total) o None
_total_ia_para_prog: int = 1         # total de archivos a procesar
_contador_ia: int = 0                # contador interno

# Una HV real raramente supera 15.000 caracteres extraídos.
# Si el texto es más largo, es casi seguro un libro, manual o documento masivo.
# Se descarta SIN gastar ningún token de IA.
UMBRAL_MAX_CHARS_HV = 15_000


def _cv_es_vacio(data: dict, nombre_archivo: str) -> tuple[bool, str]:
    """
    Detecta si el JSON generado por la IA es sospechosamente vacío,
    lo que indica que el documento NO era una HV real (ej: libro, manual, contrato largo).

    Criterios de alerta (basta con 2 de los 4):
      1. El nombre extraído NO aparece en el nombre del archivo
      2. Sin experiencia laboral (lista vacía o entradas sin empresa ni cargo)
      3. Sin educación
      4. Sin email ni teléfono en contacto
    """
    import unicodedata

    def _norm(s):
        s = unicodedata.normalize("NFD", str(s))
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9]", "", s.lower())

    alertas = []

    # 1. Nombre extraído vs nombre del archivo
    nombre_cv    = _norm(data.get("contacto", {}).get("nombre", ""))
    nombre_file  = _norm(nombre_archivo)
    tokens_cv    = [t for t in nombre_cv.split() if len(t) > 2] if nombre_cv else []
    # Si el nombre tiene tokens y NINGUNO aparece en el nombre del archivo → sospechoso
    if tokens_cv and not any(t in nombre_file for t in tokens_cv):
        alertas.append(
            f"El nombre extraído por la IA ('{data.get('contacto',{}).get('nombre','')}') "
            f"no coincide con el nombre del archivo '{nombre_archivo}'"
        )

    # 2. Experiencia laboral vacía o sin datos reales
    experiencias = data.get("experiencia", [])
    exp_reales = [
        e for e in experiencias
        if (e.get("empresa") or "").strip() or (e.get("cargo") or "").strip()
    ]
    if not exp_reales:
        alertas.append("Sin experiencia laboral registrada")

    # 3. Sin educación
    if not data.get("educacion"):
        alertas.append("Sin información de educación registrada")

    # 4. Sin email ni teléfono
    contacto = data.get("contacto", {})
    if not (contacto.get("email") or "").strip() and \
       not (contacto.get("telefono") or "").strip():
        alertas.append("Sin email ni teléfono de contacto")

    # Se marca como sospechoso si cumple 3 o más criterios
    # (3 de 4 para ser más conservadores y no descartar HVs incompletas)
    if len(alertas) >= 3:
        motivo = "Posible documento no HV (contenido insuficiente): " + " | ".join(alertas)
        return True, motivo

    return False, ""


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
    global _contador_ia

    print("Procesando:", path)

    # Actualizar barra 2 al comenzar cada archivo
    _contador_ia += 1
    if _progress_ia_cb:
        try:
            _progress_ia_cb(_contador_ia, _total_ia_para_prog)
        except Exception:
            pass

    try:

        texto = extraer_texto(path)

        if not texto.strip():
            print("⚠️ No se pudo extraer texto:", path)
            return

        # ── Detección por longitud excesiva (libro, manual, documento masivo) ──
        # Sin gastar ningún token de IA: si el texto es demasiado largo para
        # ser una HV, se descarta directamente.
        if len(texto) > UMBRAL_MAX_CHARS_HV:
            nombre = os.path.basename(path)
            motivo = (
                f"Documento demasiado extenso para ser una HV "
                f"({len(texto):,} caracteres extraídos, máximo esperado {UMBRAL_MAX_CHARS_HV:,}). "
                f"Posible libro, manual o documento masivo subido por error."
            )
            print(f"  🚫 Documento muy extenso, no es HV — {nombre}")
            data_no_hv = {
                "es_hoja_de_vida"  : False,
                "motivo_rechazo_hv": motivo,
                "archivo_original" : nombre,
                "contacto"         : {
                    "nombre": nombre.replace(".pdf","").replace(".docx","").replace("_"," ")
                },
                "experiencia": [], "educacion": [], "habilidades": [], "cursos": [],
            }
            salida = str(Path(OUTPUT) / (nombre + ".json"))
            with open(salida, "w", encoding="utf8") as f:
                json.dump(data_no_hv, f, indent=2, ensure_ascii=False)
            ARCHIVOS_NO_HV.append({"archivo": nombre, "motivo": motivo})
            return

        # ── Validar si el documento es una hoja de vida ────────────────────
        es_hv, motivo_validacion = es_hoja_de_vida(texto)

        if not es_hv:
            print(f"  🚫 Documento NO es una HV — {motivo_validacion}")
            nombre = os.path.basename(path)

            # Guardar un JSON marcador para que el tercer filtro lo clasifique
            # correctamente sin gastar tokens del parseo completo
            data_no_hv = {
                "es_hoja_de_vida"   : False,
                "motivo_rechazo_hv" : motivo_validacion,
                "archivo_original"  : nombre,
                "contacto"          : {"nombre": nombre.replace("_", " ").replace(".pdf","").replace(".docx","")},
                "experiencia"       : [],
                "educacion"         : [],
                "habilidades"       : [],
                "cursos"            : [],
            }

            salida = str(Path(OUTPUT) / (nombre + ".json"))
            with open(salida, "w", encoding="utf8") as f:
                json.dump(data_no_hv, f, indent=2, ensure_ascii=False)

            # Registrar en la lista global para el Excel unificado
            ARCHIVOS_NO_HV.append({
                "archivo" : nombre,
                "motivo"  : motivo_validacion,
            })
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

        # ── Detectar si el documento parsado es sospechosamente vacío ─────
        # (p.ej. un libro o manual que pasó el filtro de HV por su longitud)
        nombre_base = os.path.basename(path)
        es_vacio, motivo_vacio = _cv_es_vacio(data, nombre_base)
        if es_vacio:
            print(f"  ⚠️  CV sospechoso (posible no-HV): {motivo_vacio}")
            data_no_hv = {
                "es_hoja_de_vida"   : False,
                "motivo_rechazo_hv" : motivo_vacio,
                "archivo_original"  : nombre_base,
                # Usar el nombre del ARCHIVO (no el que inventó la IA) como nombre del candidato
                "contacto"          : {
                    "nombre": nombre_base.replace(".pdf","").replace(".docx","").replace("_"," ")
                },
                "experiencia": [], "educacion": [], "habilidades": [], "cursos": [],
            }
            salida = str(Path(OUTPUT) / (nombre_base + ".json"))
            with open(salida, "w", encoding="utf8") as f:
                json.dump(data_no_hv, f, indent=2, ensure_ascii=False)
            ARCHIVOS_NO_HV.append({"archivo": nombre_base, "motivo": motivo_vacio})
            return

        # agregar tipo de formato y nombre del archivo original (fallback para matching)
        data["tipo_formato"]      = tipo_formato
        data["archivo_original"]  = os.path.basename(path)

        # postprocesamiento
        data = postprocesar(data)

        nombre = os.path.basename(path)

        salida = str(Path(OUTPUT) / (nombre + ".json"))

        with open(salida, "w", encoding="utf8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print("✅ Procesado:", nombre)

    except Exception as e:

        print("❌ Error procesando:", path)
        print(e)


def main():
    global _contador_ia
    _contador_ia = 0

    input_dir = resolver_input()

    # OUTPUT puede ser str o Path inyectado por primer_filtro.py
    output_dir = Path(OUTPUT)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Limpiar JSONs previos en la carpeta de salida de esta ejecución
    for f in output_dir.glob("*.json"):
        f.unlink()

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
