"""
tercer_filtro.py
================
Tercera fase del pipeline de filtrado de HVs.

Lee los JSON de:
  - Resultados Segundo Filtro/  → datos estructurados del CV (experiencia, educacion, etc.)
  - Resultados Primer Filtro/<vacante>/descripcion_<vacante>.json → descripcion de la vacante
                                                                     + pesos exp/academico

Para cada candidato llama a la IA (Groq) y genera un score 0-100 ponderado por los pesos
ingresados por el usuario. Clasifica en:
  - Opcionados           (score >= UMBRAL_OPCIONADO)
  - Probablemente Opcionados (score >= UMBRAL_PROBABLE)
  - Descartados          (score < UMBRAL_PROBABLE)

Copia el PDF/DOCX original a la carpeta de clasificacion con el nombre del candidato.
Genera un Excel resumen al final.

Dependencias adicionales:
    pip install groq python-dotenv openpyxl
"""

import os
import json
import re
import shutil
import glob
from pathlib import Path
from datetime import datetime

import pandas as pd
from groq import Groq
from dotenv import load_dotenv

# ─────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Carpetas de entrada
DIR_PRIMER_FILTRO  = Path("Resultados Primer Filtro")
DIR_SEGUNDO_FILTRO = Path("Resultados Segundo Filtro")

# Carpeta raíz de salida
DIR_TERCER_FILTRO  = Path("Resultados Tercer Filtro")

# Umbrales de clasificación
UMBRAL_OPCIONADO = 70   # score >= 70 → Opcionado
UMBRAL_PROBABLE  = 45   # score >= 45 → Probablemente Opcionado
                        # score < 45  → Descartado

# Subcarpetas de clasificación
CARPETA_OPCIONADO = "Opcionados"
CARPETA_PROBABLE  = "Probablemente Opcionados"
CARPETA_DESCARTADO = "Descartados"


# ─────────────────────────────────────────
# HELPERS JSON
# ─────────────────────────────────────────

def limpiar_json(texto: str) -> str:
    """Extrae el primer objeto JSON válido de una respuesta de IA."""
    if not texto:
        return "{}"
    texto = texto.replace("```json", "").replace("```", "")
    stack = []
    inicio = None
    for i, c in enumerate(texto):
        if c == "{":
            if inicio is None:
                inicio = i
            stack.append(c)
        elif c == "}":
            if stack:
                stack.pop()
            if not stack and inicio is not None:
                return texto[inicio:i+1]
    return "{}"


# ─────────────────────────────────────────
# LOCALIZAR ARCHIVOS DE ENTRADA
# ─────────────────────────────────────────

# Puede ser inyectada por primer_filtro.py para evitar ambigüedad entre vacantes
CARPETA_VACANTE_ACTIVA = None


def subcarpeta_mas_reciente(raiz: Path) -> Path:
    """Retorna la subcarpeta más reciente (por mtime) dentro de raiz."""
    subcarpetas = [p for p in raiz.iterdir() if p.is_dir()]
    if not subcarpetas:
        raise FileNotFoundError(
            f"No se encontraron subcarpetas en '{raiz}'. "
            "Ejecuta primero el filtrador de HVs."
        )
    return max(subcarpetas, key=lambda p: p.stat().st_mtime)


def carpeta_vacante_activa() -> Path:
    """
    Devuelve la carpeta del primer filtro del proceso en curso.
    - Si primer_filtro.py inyectó CARPETA_VACANTE_ACTIVA, la usa directamente.
    - Si no (ejecución independiente), toma la subcarpeta más reciente.
    """
    if CARPETA_VACANTE_ACTIVA is not None:
        return CARPETA_VACANTE_ACTIVA
    carpeta = subcarpeta_mas_reciente(DIR_PRIMER_FILTRO)
    print(f"📂 Carpeta de vacante detectada automáticamente: {carpeta}")
    return carpeta


def encontrar_json_vacante() -> dict | None:
    """
    Busca descripcion_*.json dentro de la carpeta de vacante activa.
    Retorna el dict parseado o None.
    """
    carpeta = carpeta_vacante_activa()
    archivos = list(carpeta.glob("descripcion_*.json"))
    if not archivos:
        print(f"⚠️  No se encontró descripcion_*.json en {carpeta}")
        return None
    ruta = max(archivos, key=lambda p: p.stat().st_mtime)
    print(f"📄 Vacante leída desde: {ruta}")
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def encontrar_pdf_candidato(nombre_candidato: str) -> Path | None:
    """
    Busca el PDF o DOCX del candidato SOLO dentro de la carpeta de vacante activa,
    así nunca confunde archivos de procesos anteriores.
    """
    carpeta = carpeta_vacante_activa()
    nombre_norm = re.sub(r"\s+", "_", nombre_candidato.strip())
    for ext in ("*.pdf", "*.docx"):
        for f in carpeta.glob(ext):
            stem = f.stem
            if stem.lower() == nombre_norm.lower():
                return f
            if nombre_candidato.split()[0].lower() in stem.lower():
                return f
    return None



# ─────────────────────────────────────────
# REGLA DE ESTABILIDAD LABORAL
# ─────────────────────────────────────────

def verificar_estabilidad(cv_data: dict) -> tuple:
    """
    Regla: si en las ultimas 3 experiencias, 2 o mas tuvieron duracion < 12 meses
    el candidato es DESCARTADO por inestabilidad laboral.
    Retorna (descartado: bool, motivo: str).
    """
    experiencias = cv_data.get("experiencia", [])
    if not experiencias:
        return False, ""

    # Ordenar por fecha_inicio_norm descendente (mas recientes primero)
    def _sort_key(e):
        return e.get("fecha_inicio_norm") or e.get("fecha_inicio") or ""

    ordenadas = sorted(experiencias, key=_sort_key, reverse=True)
    ultimas_3 = ordenadas[:3]

    if len(ultimas_3) < 2:
        return False, ""

    menos_de_un_anio = [
        e for e in ultimas_3
        if (e.get("duracion_meses") or 0) < 12 and not e.get("es_actual", False)
    ]

    if len(menos_de_un_anio) >= 2:
        detalles = " | ".join(
            f"{e.get('empresa','?')} ({e.get('duracion_meses', 0)} meses)"
            for e in menos_de_un_anio
        )
        motivo = (
            "Inestabilidad laboral: 2 o mas de las ultimas 3 experiencias "
            f"duraron menos de 1 anio ({detalles})"
        )
        return True, motivo

    return False, ""

# ─────────────────────────────────────────
# SCORING CON IA
# ─────────────────────────────────────────

def evaluar_candidato(cv_data: dict, vacante_data: dict) -> dict:
    """
    Llama a Groq para evaluar el match entre el CV y la vacante.
    Retorna un dict con: score_exp, score_aca, score_final, razones.
    """
    peso_exp = vacante_data.get("peso_experiencia_laboral", "50 %")
    peso_aca = vacante_data.get("peso_formacion_academica", "50 %")

    # Extraer número del string "60 %"
    def _pct(s):
        m = re.search(r"\d+", str(s))
        return int(m.group()) if m else 50

    pexp = _pct(peso_exp)
    paca = _pct(peso_aca)

    prompt = f"""
Eres un evaluador experto de hojas de vida para el área de Recursos Humanos.

Tu tarea: evaluar qué tan bien el candidato se ajusta a la vacante.

=== VACANTE ===
Nombre: {vacante_data.get("vacante", "")}
Descripción de tareas:
{vacante_data.get("descripcion_tareas", "No disponible")}

=== CV DEL CANDIDATO ===
{json.dumps(cv_data, ensure_ascii=False, indent=2)}

=== INSTRUCCIONES DE EVALUACIÓN ===
Genera una puntuación del 0 al 100 para dos dimensiones:

1. score_experiencia (0-100): qué tan relevante y suficiente es la experiencia laboral
   para esta vacante. Considera: cargos anteriores, sector, años de experiencia,
   responsabilidades, estabilidad laboral.

2. score_academico (0-100): qué tan adecuada es la formación académica para esta vacante.
   Considera: nivel educativo, carrera/programa, institución, cursos o certificaciones.

Luego calcula el score_final ponderado:
  score_final = (score_experiencia × {pexp} + score_academico × {paca}) / 100

Responde ÚNICAMENTE con este JSON (sin texto adicional, sin markdown):

{{
  "score_experiencia": <número 0-100>,
  "score_academico": <número 0-100>,
  "score_final": <número 0-100>,
  "razones": {{
    "experiencia": "<2-3 frases explicando el score de experiencia>",
    "academico": "<2-3 frases explicando el score académico>",
    "resumen": "<1-2 frases de resumen general del candidato>"
  }}
}}
"""

    try:
        r = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        contenido = limpiar_json(r.choices[0].message.content)
        data = json.loads(contenido)

        # Validar y redondear scores
        for k in ("score_experiencia", "score_academico", "score_final"):
            data[k] = max(0, min(100, round(float(data.get(k, 0)))))

        return data

    except Exception as e:
        print(f"  ⚠️  Error en evaluación IA: {e}")
        return {
            "score_experiencia": 0,
            "score_academico":   0,
            "score_final":       0,
            "razones": {
                "experiencia": "No se pudo evaluar.",
                "academico":   "No se pudo evaluar.",
                "resumen":     f"Error: {e}",
            },
        }


# ─────────────────────────────────────────
# CLASIFICACIÓN
# ─────────────────────────────────────────

def clasificar(score: float) -> str:
    if score >= UMBRAL_OPCIONADO:
        return CARPETA_OPCIONADO
    if score >= UMBRAL_PROBABLE:
        return CARPETA_PROBABLE
    return CARPETA_DESCARTADO


# ─────────────────────────────────────────
# PROCESO PRINCIPAL
# ─────────────────────────────────────────

def main():

    # 1. Preparar carpetas de salida
    vacante_data = encontrar_json_vacante()
    if not vacante_data:
        return

    nombre_vacante = vacante_data.get("vacante", "vacante")
    nombre_limpio  = re.sub(r"[^\w\s-]", "", nombre_vacante).strip().replace(" ", "_")[:60]
    ts             = datetime.now().strftime("%Y-%m")
    carpeta_base   = DIR_TERCER_FILTRO / f"{nombre_limpio}_{ts}"

    for sub in (CARPETA_OPCIONADO, CARPETA_PROBABLE, CARPETA_DESCARTADO):
        (carpeta_base / sub).mkdir(parents=True, exist_ok=True)

    # 2. Listar JSONs del segundo filtro
    jsons = list(DIR_SEGUNDO_FILTRO.glob("*.json"))
    if not jsons:
        print("⚠️  No hay JSONs en", DIR_SEGUNDO_FILTRO)
        return

    print(f"\n🔍 Evaluando {len(jsons)} candidato(s) para: {nombre_vacante}")
    print(f"   Peso experiencia : {vacante_data.get('peso_experiencia_laboral', '?')}")
    print(f"   Peso académico   : {vacante_data.get('peso_formacion_academica', '?')}")
    print(f"   Umbrales         : Opcionado ≥ {UMBRAL_OPCIONADO}  |  Probable ≥ {UMBRAL_PROBABLE}\n")

    resumen = []

    for json_path in jsons:

        print(f"📋 Procesando: {json_path.name}")

        try:
            with open(json_path, encoding="utf-8") as f:
                cv_data = json.load(f)
        except Exception as e:
            print(f"  ❌ No se pudo leer JSON: {e}")
            continue

        # Nombre del candidato desde el JSON del segundo filtro
        nombre_candidato = (
            cv_data.get("contacto", {}).get("nombre")
            or json_path.stem.replace("_", " ").replace(".pdf", "").replace(".docx", "")
        )

        print(f"  👤 Candidato: {nombre_candidato}")

        # ── Regla de estabilidad laboral (descarte directo, sin llamar a la IA) ──
        inestable, motivo_estabilidad = verificar_estabilidad(cv_data)
        if inestable:
            print(f"  🚫 DESCARTADO por estabilidad — {motivo_estabilidad}")
            evaluacion = {
                "score_experiencia": 0,
                "score_academico":   0,
                "score_final":       0,
                "razones": {
                    "experiencia": motivo_estabilidad,
                    "academico":   "",
                    "resumen":     "Descartado automáticamente por regla de estabilidad laboral.",
                },
            }
            score         = 0
            clasificacion = CARPETA_DESCARTADO
            razones       = evaluacion["razones"]
        else:
            # Evaluar con IA
            evaluacion = evaluar_candidato(cv_data, vacante_data)
            score         = evaluacion["score_final"]
            clasificacion = clasificar(score)
            razones       = evaluacion.get("razones", {})

        print(f"  📊 Score: {score:.0f}% → {clasificacion}")

        # Copiar archivo original a la carpeta de clasificación
        archivo_original = encontrar_pdf_candidato(nombre_candidato)
        archivo_copiado  = None

        if archivo_original:
            nombre_archivo = re.sub(r"[^\w\s-]", "", nombre_candidato).strip().replace(" ", "_")
            destino = carpeta_base / clasificacion / f"{nombre_archivo}{archivo_original.suffix}"
            shutil.copy2(archivo_original, destino)
            archivo_copiado = str(destino)
            print(f"  📁 Copiado a: {destino.relative_to(DIR_TERCER_FILTRO)}")
        else:
            print(f"  ⚠️  No se encontró archivo PDF/DOCX para: {nombre_candidato}")

        # Guardar JSON de evaluación junto al archivo
        nombre_seguro = re.sub(r'[^\w\s-]', '', nombre_candidato).strip().replace(' ', '_')
        eval_json_path = carpeta_base / clasificacion / f"{nombre_seguro}_evaluacion.json"
        with open(eval_json_path, "w", encoding="utf-8") as f:
            json.dump({
                "candidato"           : nombre_candidato,
                "vacante"             : nombre_vacante,
                "score_experiencia"   : evaluacion["score_experiencia"],
                "score_academico"     : evaluacion["score_academico"],
                "score_final"         : score,
                "clasificacion"       : clasificacion,
                "razon_experiencia"   : razones.get("experiencia", ""),
                "razon_academico"     : razones.get("academico", ""),
                "resumen"             : razones.get("resumen", ""),
                "peso_exp_usado"      : vacante_data.get("peso_experiencia_laboral", ""),
                "peso_aca_usado"      : vacante_data.get("peso_formacion_academica", ""),
                "fecha_evaluacion"    : datetime.now().strftime("%Y-%m-%d %H:%M"),
            }, f, ensure_ascii=False, indent=2)

        resumen.append({
            "Candidato"           : nombre_candidato,
            "Score Final (%)"     : score,
            "Score Experiencia (%)": evaluacion["score_experiencia"],
            "Score Académico (%)" : evaluacion["score_academico"],
            "Clasificación"       : clasificacion,
            "Razón Experiencia"   : razones.get("experiencia", ""),
            "Razón Académica"     : razones.get("academico", ""),
            "Resumen"             : razones.get("resumen", ""),
            "Archivo"             : archivo_copiado or "No encontrado",
        })

    # 3. Generar Excel resumen
    if resumen:
        df = pd.DataFrame(resumen)

        # Ordenar por score descendente
        df = df.sort_values("Score Final (%)", ascending=False).reset_index(drop=True)

        excel_path = carpeta_base / f"resumen_evaluacion_{nombre_limpio}.xlsx"

        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:

            df.to_excel(writer, index=False, sheet_name="Evaluación Candidatos")

            # Hoja de parámetros
            params = pd.DataFrame([
                {"Parámetro": "Vacante",                  "Valor": nombre_vacante},
                {"Parámetro": "Peso experiencia laboral", "Valor": vacante_data.get("peso_experiencia_laboral", "")},
                {"Parámetro": "Peso formación académica", "Valor": vacante_data.get("peso_formacion_academica", "")},
                {"Parámetro": "Umbral Opcionado",         "Valor": f"{UMBRAL_OPCIONADO} %"},
                {"Parámetro": "Umbral Probable",          "Valor": f"{UMBRAL_PROBABLE} %"},
                {"Parámetro": "Total evaluados",          "Valor": len(resumen)},
                {"Parámetro": "Opcionados",               "Valor": sum(1 for r in resumen if r["Clasificación"] == CARPETA_OPCIONADO)},
                {"Parámetro": "Probablemente opcionados", "Valor": sum(1 for r in resumen if r["Clasificación"] == CARPETA_PROBABLE)},
                {"Parámetro": "Descartados",              "Valor": sum(1 for r in resumen if r["Clasificación"] == CARPETA_DESCARTADO)},
                {"Parámetro": "Fecha ejecución",          "Valor": datetime.now().strftime("%Y-%m-%d %H:%M")},
            ])
            params.to_excel(writer, index=False, sheet_name="Parámetros")

        print(f"\n✅ Excel generado: {excel_path}")

    # 4. Resumen en consola
    print("\n" + "═" * 55)
    print(f"  RESUMEN FINAL — {nombre_vacante}")
    print("═" * 55)
    total = len(resumen)
    opc   = sum(1 for r in resumen if r["Clasificación"] == CARPETA_OPCIONADO)
    prob  = sum(1 for r in resumen if r["Clasificación"] == CARPETA_PROBABLE)
    desc  = sum(1 for r in resumen if r["Clasificación"] == CARPETA_DESCARTADO)
    print(f"  Total evaluados          : {total}")
    print(f"  Opcionados               : {opc}")
    print(f"  Probablemente Opcionados : {prob}")
    print(f"  Descartados              : {desc}")
    print(f"  Resultados en            : {carpeta_base}")
    print("═" * 55)


if __name__ == "__main__":
    main()
