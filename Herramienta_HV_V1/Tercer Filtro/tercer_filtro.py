"""
tercer_filtro.py
================
Tercera fase del pipeline de filtrado de HVs.

Lee los JSON de:
  - Resultados Segundo Filtro/  → datos estructurados del CV (experiencia, educacion, etc.)
  - Resultados Primer Filtro/<vacante>/descripcion_<vacante>.json → descripcion de la vacante
                                                                     + pesos exp/academico

Para cada candidato llama a la IA (OpenAI gpt-4o-mini) y genera un score 0-100 ponderado por los pesos
ingresados por el usuario. Clasifica en:
  - Opcionados           (score >= UMBRAL_OPCIONADO)
  - Probablemente Opcionados (score >= UMBRAL_PROBABLE)
  - Descartados          (score < UMBRAL_PROBABLE)

Copia el PDF/DOCX original a la carpeta de clasificacion con el nombre del candidato.
Genera un Excel resumen al final.

Dependencias adicionales:
    pip install openai python-dotenv openpyxl
"""

import os
import json
import re
import shutil
import glob
from pathlib import Path
from datetime import datetime

import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from token_tracker import registrar

# Por:
import sys
sys.path.append(str(Path(__file__).parent.parent / "Segundo Filtro"))
from token_tracker import registrar

# ─────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────

load_dotenv()
client = OpenAI(api_key="" + os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"

# Carpetas de entrada
DIR_PRIMER_FILTRO  = Path("Resultados Primer Filtro")
DIR_SEGUNDO_FILTRO = Path("Resultados Segundo Filtro")

# Carpeta raíz de salida para JSONs intermedios
DIR_TERCER_FILTRO  = Path("Resultados Tercer Filtro")

# Carpeta de resultados finales (HVs clasificadas + Excel) — inyectada por primer_filtro.py
DIR_RESULTADOS     = Path("Resultados")

# Umbrales de clasificación
UMBRAL_OPCIONADO = 70   # score >= 70 → Opcionado
UMBRAL_PROBABLE  = 45   # score >= 45 → Probablemente Opcionado
                        # score < 45  → Descartado

# Subcarpetas de clasificación
CARPETA_OPCIONADO = "Opcionales"
CARPETA_PROBABLE  = "Probablemente Opcionados"
CARPETA_DESCARTADO = "Descartados"


# ─────────────────────────────────────────
# HELPERS JSON
# ─────────────────────────────────────────
import time

def retry_exponencial(func, *args, max_retries=5, base_delay=1, **kwargs):

    for intento in range(max_retries):

        try:
            return func(*args, **kwargs)

        except Exception as e:

            error = str(e).lower()

            if "429" in error or "rate limit" in error:

                if intento == max_retries - 1:
                    raise

                espera = base_delay * (2 ** intento)

                print(f"⚠️ Rate limit Groq — retry en {espera}s")

                time.sleep(espera)

            else:
                raise

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

# Carpeta donde están los PDFs descargados (Primer Filtro/)
# Inyectada por main.py con carpetas["primer_filtro"]
DIR_PDF_CANDIDATOS = None

# Inyectados por primer_filtro.py para el Excel unificado
CFG_PRIMER_FILTRO     = None   # dict con parámetros del filtro 1
RESUMEN_PRIMER_FILTRO = None   # lista de dicts con resultado de cada candidato
ARCHIVOS_NO_HV        = None   # lista de dicts {archivo, motivo} del segundo filtro

# Callbacks para la barra 3 de la GUI (inyectados por primer_filtro.py)
_progress_clas_cb: object = None   # callable(actual, total) o None
_total_clas_para_prog: int = 1     # total de JSONs a clasificar
_contador_clas: int = 0            # contador interno


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


def encontrar_pdf_candidato(nombre_candidato: str,
                            nombre_archivo_original: str = None) -> Path | None:
    """
    Busca el PDF o DOCX del candidato dentro de la carpeta de vacante activa.

    Estrategia en dos pasos:
    1. Matching por tokens normalizados del nombre del candidato (tolerante a tildes).
    2. Si falla (nombre inventado por IA), usa el nombre_archivo_original como fallback
       directo — así documentos como libros o manuales siempre se copian correctamente.
    """
    import unicodedata

    def _norm(s: str) -> str:
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9]", "", s.lower())

    # Usar DIR_PDF_CANDIDATOS si fue inyectada (ruta directa a los PDFs)
    # Si no, usar la raíz de la ejecución como fallback
    carpeta = DIR_PDF_CANDIDATOS if DIR_PDF_CANDIDATOS is not None else carpeta_vacante_activa()

    # ── Paso 1: matching por tokens del nombre del candidato ──────────
    tokens_cand = [_norm(t) for t in nombre_candidato.split() if len(t) > 2]
    mejor_archivo = None
    mejor_score   = 0

    for ext in ("*.pdf", "*.docx"):
        for f in carpeta.glob(ext):
            stem_norm = _norm(f.stem)
            coinciden = sum(1 for t in tokens_cand if t in stem_norm)
            if coinciden > mejor_score:
                mejor_score   = coinciden
                mejor_archivo = f

    if mejor_score >= 2:
        return mejor_archivo

    # ── Paso 2: fallback por nombre del archivo original ─────────────
    # Cuando la IA inventó un nombre (ej: "Vinicio Ramos" para OSCAR_Buitrago_gomez.pdf),
    # el matching por tokens falla. Usamos el nombre del archivo del JSON directamente.
    if nombre_archivo_original:
        candidato_norm = _norm(nombre_archivo_original)
        for ext in ("*.pdf", "*.docx"):
            for f in carpeta.glob(ext):
                if _norm(f.name) == candidato_norm:
                    print(f"  ℹ️  Archivo encontrado por nombre de fichero: {f.name}")
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
    Retorna un dict con: score_exp, score_aca, score_final, razones,
    bonus_keywords, keywords_encontradas.
    """
    peso_exp = vacante_data.get("peso_experiencia_laboral", "50 %")
    peso_aca = vacante_data.get("peso_formacion_academica", "50 %")

    # Extraer número del string "60 %"
    def _pct(s):
        m = re.search(r"\d+", str(s))
        return int(m.group()) if m else 50

    pexp = _pct(peso_exp)
    paca = _pct(peso_aca)

    # ── Palabras clave: preparar bloque de contexto compacto ─────────────
    # Se leen desde vacante_data (guardadas en el JSON de descripción).
    # Se limitan a 300 chars para no comprometer el límite de 6000 TPM.
    raw_kw = vacante_data.get("palabras_clave", "") or ""
    keywords_lista = [k.strip() for k in raw_kw.split(",") if k.strip()]
    bloque_kw = ""
    if keywords_lista:
        kw_str = ", ".join(keywords_lista)[:300]   # tope duro de 300 chars ≈ 75 tokens
        bloque_kw = f"""
=== CONTEXTO ADICIONAL — PALABRAS CLAVE DEL SECTOR ===
Las siguientes palabras clave describen el sector, área o empresas relevantes para esta vacante.
Tenlas en cuenta al evaluar la experiencia: si el candidato las menciona (explícita o implícitamente),
es señal de experiencia pertinente que debe subir el score.
Palabras clave: {kw_str}
"""

    # ── Serializar CV con límite para no exceder tokens ──────────────────
    # Presupuesto estimado: prompt base ~900 tokens + CV ~700 tokens + kw ~80 tokens < 1800 tokens
    # ── Reducir CV para enviar solo lo necesario a la IA ─────────────

    cv_reducido = {
        "perfil_resumen": cv_data.get("perfil_resumen"),
        "experiencia": (cv_data.get("experiencia") or [])[:5],
        "educacion": cv_data.get("educacion"),
        "cursos": cv_data.get("cursos")
    }

    cv_str = json.dumps(cv_reducido, ensure_ascii=False, indent=2)

    # limitar tamaño para evitar exceso de tokens
    if len(cv_str) > 2500:
        cv_str = cv_str[:2500] + "\n...(truncado)"
    prompt = f"""
Eres un evaluador experto de hojas de vida para el área de Recursos Humanos.

Tu tarea: evaluar qué tan bien el candidato se ajusta a la vacante.

=== VACANTE ===
Nombre: {vacante_data.get("vacante", "")}
Descripción de tareas:
{vacante_data.get("descripcion_tareas", "No disponible")}
{bloque_kw}
=== CV DEL CANDIDATO ===
{cv_str}

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
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=1000,
            response_format={"type": "json_object"},  # ✅ JSON garantizado
            timeout=45
        )
        registrar("tercer_filtro", resp.usage)

        data = json.loads(resp.choices[0].message.content)

        # Validar y redondear scores de la IA
        for k in ("score_experiencia", "score_academico", "score_final"):
            data[k] = max(0, min(100, round(float(data.get(k, 0)))))

        # ── Bonus por palabras clave (post-IA, sin gastar tokens extra) ──
        # Se detecta cuántas keywords aparecen en el texto del CV.
        # Bonus: +2 pts por keyword encontrada, máximo +10 pts,
        # nunca supera 100 en score_final.
        bonus = 0
        encontradas = []
        if keywords_lista:
            import unicodedata as _ud
            def _norm_kw(s):
                s = _ud.normalize("NFD", s.lower())
                return "".join(c for c in s if _ud.category(c) != "Mn")
            cv_texto_norm = _norm_kw(json.dumps(cv_data, ensure_ascii=False))
            for kw in keywords_lista:
                if _norm_kw(kw) in cv_texto_norm:
                    encontradas.append(kw)
            bonus = min(len(encontradas) * 2, 10)
            data["score_final"] = min(100, data["score_final"] + bonus)

        data["bonus_keywords"]       = bonus
        data["keywords_encontradas"] = encontradas

        return data

    except Exception as e:
        print(f"  ⚠️  Error en evaluación IA: {e}")
        return {
            "score_experiencia"   : 0,
            "score_academico"     : 0,
            "score_final"         : 0,
            "bonus_keywords"      : 0,
            "keywords_encontradas": [],
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
    global _contador_clas
    _contador_clas = 0

    # 1. Preparar carpetas de salida
    vacante_data = encontrar_json_vacante()
    if not vacante_data:
        return

    nombre_vacante = vacante_data.get("vacante", "vacante")
    nombre_limpio  = re.sub(r"[^\w\s-]", "", nombre_vacante).strip().replace(" ", "_")[:60]

    # Carpeta de intermedios: JSONs de evaluación por candidato
    dir_json_eval = DIR_TERCER_FILTRO
    dir_json_eval.mkdir(parents=True, exist_ok=True)

    # Carpeta de resultados finales: HVs clasificadas + Excel
    # DIR_RESULTADOS es inyectada por primer_filtro.py con la estructura:
    #   Ejecuciones/<vacante>_<ts>/Resultados/
    for sub in (CARPETA_OPCIONADO, CARPETA_PROBABLE, CARPETA_DESCARTADO):
        (DIR_RESULTADOS / sub).mkdir(parents=True, exist_ok=True)

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

        # Actualizar barra 3
        _contador_clas += 1
        if _progress_clas_cb:
            try:
                _progress_clas_cb(_contador_clas, _total_clas_para_prog)
            except Exception:
                pass

        try:
            with open(json_path, encoding="utf-8") as f:
                cv_data = json.load(f)
        except Exception as e:
            print(f"  ❌ No se pudo leer JSON: {e}")
            continue

        # ── Detectar documentos que NO son hojas de vida ─────────────────
        if cv_data.get("es_hoja_de_vida") is False:
            motivo_no_hv = cv_data.get("motivo_rechazo_hv", "Documento no identificado como hoja de vida.")
            nombre_archivo = cv_data.get("archivo_original", json_path.stem)
            nombre_candidato = (nombre_archivo
                                .replace(".pdf", "").replace(".docx", "")
                                .replace("_", " "))

            # ── Distinguir entre "no es HV" y "error de procesamiento" ──
            es_error = cv_data.get("es_error_procesamiento", False)
            if es_error:
                print(f"  ⚠️ ERROR DE PROCESAMIENTO — {nombre_candidato}: {motivo_no_hv}")
                clasificacion_label = CARPETA_DESCARTADO
                razon_label = (
                    f"⚠️ REVISAR MANUALMENTE — Error al procesar el archivo. "
                    f"El PDF fue movido a Descartados. Detalle: {motivo_no_hv}"
                )
                resumen_label = "⚠️ Revisar manualmente: hubo un error al procesar este archivo. Revise el PDF en la carpeta Descartados."
            else:
                print(f"  🚫 NO ES HV — {nombre_candidato}: {motivo_no_hv}")
                clasificacion_label = CARPETA_DESCARTADO
                razon_label = (
                    f"⚠️ DOCUMENTO NO CORRESPONDE A UNA HOJA DE VIDA. {motivo_no_hv} "
                    f"— Verifique manualmente si el archivo fue subido por error."
                )
                resumen_label = "⚠️ Revisar manualmente: el sistema detectó que este archivo no es una hoja de vida."

            # Copiar el archivo a Descartados si aún no fue movido
            archivo_original = encontrar_pdf_candidato(
                nombre_candidato,
                nombre_archivo_original=nombre_archivo
            )
            archivo_copiado = None
            if archivo_original:
                nombre_seguro = re.sub(r"[^\w\s-]", "", nombre_candidato).strip().replace(" ", "_")
                destino = DIR_RESULTADOS / CARPETA_DESCARTADO / f"{nombre_seguro}{archivo_original.suffix}"
                if not destino.exists():   # evitar duplicar si segundo_filtro ya lo movió
                    shutil.copy2(archivo_original, destino)
                archivo_copiado = str(destino)

            resumen.append({
                "Candidato"             : nombre_candidato,
                "Score Final (%)"       : 0,
                "Score Experiencia (%)": 0,
                "Score Académico (%)"  : 0,
                "Bonus Keywords (pts)" : 0,
                "Keywords encontradas" : "",
                "Clasificación"        : clasificacion_label,
                "Razón Experiencia"    : razon_label,
                "Razón Académica"      : "No analizado.",
                "Resumen"              : resumen_label,
                "Archivo"              : archivo_copiado or "No encontrado",
            })
            continue

        # Nombre del candidato desde el JSON del segundo filtro
        # El nombre_archivo_original permite el fallback cuando la IA inventó un nombre
        nombre_archivo_original = cv_data.get("archivo_original", json_path.name)
        nombre_candidato = (
            cv_data.get("contacto", {}).get("nombre")
            or json_path.stem.replace("_", " ").replace(".pdf", "").replace(".docx", "")
        )

        print(f"  👤 Candidato: {nombre_candidato}")

        # ── Regla de estabilidad laboral (descarte directo, sin llamar a la IA) ──
        inestable, motivo_estabilidad = verificar_estabilidad(cv_data)
        if inestable:
            print(f"  🚫 DESCARTADO por estabilidad — {motivo_estabilidad}")
            # Llamar a la IA igual para obtener el análisis ACADÉMICO completo
            evaluacion_ia = evaluar_candidato(cv_data, vacante_data)
            evaluacion = {
                "score_experiencia": 0,
                "score_academico":   evaluacion_ia.get("score_academico", 0),
                "score_final":       0,
                "razones": {
                    "experiencia": motivo_estabilidad,
                    "academico":   (evaluacion_ia.get("razones", {}).get("academico")
                                    or "Ver resumen general."),
                    "resumen":     "Descartado automáticamente por regla de estabilidad laboral.",
                },
            }
            score         = 0
            clasificacion = CARPETA_DESCARTADO
            razones       = evaluacion["razones"]
        else:
            # Evaluar con IA
            evaluacion    = evaluar_candidato(cv_data, vacante_data)
            score         = evaluacion["score_final"]
            clasificacion = clasificar(score)
            razones       = evaluacion.get("razones", {})

        # ── Garantizar que ninguna razón quede vacía ───────────────────────
        resumen_gral = razones.get("resumen") or ""
        if not razones.get("experiencia"):
            razones["experiencia"] = resumen_gral or "Sin información de experiencia disponible."

        # 🚨 Detectar experiencia en 0 SOLO cuando sí hubo evaluación real
        if evaluacion.get("score_experiencia", 0) == 0 and not inestable:
            
            # Evitar sobrescribir casos especiales como "no es HV"
            if "DOCUMENTO NO CORRESPONDE" not in razones.get("experiencia", ""):
                
                if not cv_data.get("experiencia"):
                    razones["experiencia"] = (
                        "⚠️ SIN EXPERIENCIA REGISTRADA. "
                        "El candidato no reporta historial laboral."
                    )
                else:
                    razones["experiencia"] = (
                        "⚠️ EXPERIENCIA NO EVALUABLE. "
                        "Revisar estabilidad laboral — sin fechas en la experiencia."
                    )

        if not razones.get("academico"):
            razones["academico"] = resumen_gral or "Sin información académica disponible."

        print(f"  📊 Score: {score:.0f}% → {clasificacion}")

        # Copiar PDF/DOCX a la carpeta de Resultados (entregable final)
        archivo_original = encontrar_pdf_candidato(
            nombre_candidato,
            nombre_archivo_original=nombre_archivo_original
        )
        archivo_copiado  = None

        if archivo_original:
            nombre_archivo = re.sub(r"[^\w\s-]", "", nombre_candidato).strip().replace(" ", "_")
            destino = DIR_RESULTADOS / clasificacion / f"{nombre_archivo}{archivo_original.suffix}"
            shutil.copy2(archivo_original, destino)
            archivo_copiado = str(destino)
            print(f"  📁 Copiado a: {destino}")
        else:
            print(f"  ⚠️  No se encontró archivo PDF/DOCX para: {nombre_candidato}")

        # Guardar JSON de evaluación en la carpeta de Intermedios/Tercer Filtro
        nombre_seguro  = re.sub(r'[^\w\s-]', '', nombre_candidato).strip().replace(' ', '_')
        eval_json_path = dir_json_eval / f"{nombre_seguro}_evaluacion.json"
        with open(eval_json_path, "w", encoding="utf-8") as f:
            json.dump({
                "candidato"           : nombre_candidato,
                "vacante"             : nombre_vacante,
                "score_experiencia"   : evaluacion["score_experiencia"],
                "score_academico"     : evaluacion["score_academico"],
                "score_final"         : score,
                "bonus_keywords"      : evaluacion.get("bonus_keywords", 0),
                "keywords_encontradas": evaluacion.get("keywords_encontradas", []),
                "clasificacion"       : clasificacion,
                "razon_experiencia"   : razones.get("experiencia", ""),
                "razon_academico"     : razones.get("academico", ""),
                "resumen"             : razones.get("resumen", ""),
                "peso_exp_usado"      : vacante_data.get("peso_experiencia_laboral", ""),
                "peso_aca_usado"      : vacante_data.get("peso_formacion_academica", ""),
                "fecha_evaluacion"    : datetime.now().strftime("%Y-%m-%d %H:%M"),
            }, f, ensure_ascii=False, indent=2)

        # ── Advertencia: experiencia con duración 0 meses ────────────────
        exp_en_cero = [
            e for e in (cv_data.get("experiencia") or [])
            if e.get("duracion_meses") == 0 and (e.get("empresa") or e.get("cargo"))
        ]
        nota_exp_cero = ""
        if exp_en_cero:
            empresas_cero = ", ".join(
                e.get("empresa") or e.get("cargo") or "?"
                for e in exp_en_cero
            )
            nota_exp_cero = (
                f" ⚠️ REVISAR MANUALMENTE — hay al menos una experiencia con duración 0 meses "
                f"({empresas_cero}). Puede indicar fechas mal registradas."
            )

        # Nota de bonus para mostrar en el resumen
        bonus_val = evaluacion.get("bonus_keywords", 0)
        kw_enc    = evaluacion.get("keywords_encontradas", [])
        nota_bonus = (f"  [+{bonus_val} pts bonus — keywords: {', '.join(kw_enc)}]"
                      if bonus_val > 0 else "")

        resumen.append({
            "Candidato"             : nombre_candidato,
            "Score Final (%)"       : score,
            "Score Experiencia (%)" : evaluacion["score_experiencia"],
            "Score Académico (%)"   : evaluacion["score_academico"],
            "Bonus Keywords (pts)"  : bonus_val,
            "Keywords encontradas"  : ", ".join(kw_enc) if kw_enc else "",
            "Clasificación"         : clasificacion,
            "Razón Experiencia"     : razones.get("experiencia", "") + nota_bonus + nota_exp_cero,
            "Razón Académica"       : razones.get("academico", ""),
            "Resumen"               : razones.get("resumen", "") + nota_exp_cero,
            "Archivo"               : archivo_copiado or "No encontrado",
        })

    # 3. Generar Excel UNIFICADO en la carpeta de Resultados (entregable final)
    if resumen:
        try:
            from generador_excel_unificado import generar_excel_unificado

            cfg_f1      = CFG_PRIMER_FILTRO     or {}
            resumen_f1  = RESUMEN_PRIMER_FILTRO or []
            no_hv_lista = ARCHIVOS_NO_HV        or []

            if not cfg_f1:
                cfg_f1 = {
                    "vacante"         : nombre_vacante,
                    "url_vacante"     : vacante_data.get("url_formulario", ""),
                    "peso_exp"        : re.sub(r"[^\d]", "", str(vacante_data.get("peso_experiencia_laboral", "50"))),
                    "peso_aca"        : re.sub(r"[^\d]", "", str(vacante_data.get("peso_formacion_academica", "50"))),
                    "edad_min": "", "edad_max": "", "sal_min": None,
                    "sal_max": None, "requiere_sabados": None,
                }

            excel_path = generar_excel_unificado(
                resumen_primer_filtro = resumen_f1,
                resumen_tercer_filtro = resumen,
                cfg_filtro1           = cfg_f1,
                vacante_data          = vacante_data,
                carpeta_salida        = DIR_RESULTADOS,
                umbral_opcionado      = UMBRAL_OPCIONADO,
                umbral_probable       = UMBRAL_PROBABLE,
                archivos_no_hv        = no_hv_lista,
            )
            print(f"\n✅ Excel unificado generado: {excel_path}")

        except Exception as e:
            import traceback
            print(f"  ⚠️  Error generando Excel unificado: {e}\n{traceback.format_exc()}")
            df_fb = pd.DataFrame(resumen).sort_values("Score Final (%)", ascending=False)
            excel_fallback = DIR_RESULTADOS / f"resumen_evaluacion_{nombre_limpio}.xlsx"
            with pd.ExcelWriter(excel_fallback, engine="openpyxl") as writer:
                df_fb.to_excel(writer, index=False, sheet_name="Evaluación Candidatos")
            print(f"  ℹ️  Excel de respaldo: {excel_fallback}")

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
    print(f"  Intermedios en           : {DIR_TERCER_FILTRO}")
    print(f"  Resultados en            : {DIR_RESULTADOS}")
    print("═" * 55)


if __name__ == "__main__":
    main()
