import re
from datetime import datetime
from limpiar import limpiar_para_comparacion

# NLP spaCy — carga diferida, falla silenciosamente si no está instalado
try:
    from nlp_spacy import (
        cargar_modelo, enriquecer_trabajos_con_nlp,
        separar_empresa_cargo_guion, es_organizacion_spacy, spacy_disponible
    )
    cargar_modelo()
except ImportError:
    def spacy_disponible(): return False
    def enriquecer_trabajos_con_nlp(t, _): return t
    def separar_empresa_cargo_guion(_): return None, None
    def es_organizacion_spacy(_): return None

# ---------------------------------------------------------------------------
# PATRONES
# ---------------------------------------------------------------------------

# Fechas: "04-2025", "04/2025", "abril 2025", "2025"
PATRON_FECHA = r"(\d{2}[-/]\d{4}|\d{4})"
MESES_ES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
}

# Keywords de habilidades técnicas comunes en contabilidad/auditoría
SKILLS_TECNICAS = [
    "niif", "ifrs", "nia", "nias", "excel", "sap", "siigo", "world office",
    "contaplus", "sql", "power bi", "tableau", "iso 14001", "iso 9001",
    "coso", "cobit", "auditoria", "contabilidad", "tributaria", "nomina",
    "presupuesto", "tesoreria", "cartera", "costos", "gestion de riesgos"
]

SKILLS_BLANDAS = [
    "liderazgo", "comunicacion", "trabajo en equipo", "analitico", "etica",
    "proactividad", "organizacion", "resolucion de problemas", "adaptabilidad"
]


# ---------------------------------------------------------------------------
# FUNCIONES AUXILIARES
# ---------------------------------------------------------------------------

def normalizar_fecha(texto_fecha):
    """Convierte variantes de fecha a formato YYYY-MM o YYYY."""
    if not texto_fecha:
        return None
    texto = texto_fecha.strip().lower()

    # Reemplazar nombres de mes
    for mes_nombre, mes_num in MESES_ES.items():
        texto = texto.replace(mes_nombre, mes_num)

    # "04-2025" o "04/2025" → "2025-04"
    match = re.match(r"(\d{2})[-/](\d{4})", texto)
    if match:
        return f"{match.group(2)}-{match.group(1)}"

    # Solo año
    match = re.match(r"(\d{4})", texto)
    if match:
        return match.group(1)

    return texto


def calcular_duracion_meses(inicio, fin):
    """Calcula duración en meses entre dos fechas YYYY-MM."""
    try:
        fmt = "%Y-%m"
        d_inicio = datetime.strptime(inicio, fmt)
        d_fin = datetime.strptime(fin, fmt) if fin and fin.lower() != "presente" else datetime.now()
        delta = (d_fin.year - d_inicio.year) * 12 + (d_fin.month - d_inicio.month)
        return max(0, delta)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PARSERS DE SECCIÓN
# ---------------------------------------------------------------------------

def extraer_fechas_de_linea(linea):
    """
    Extrae pares de fechas de una línea en cualquier formato colombiano común.
    Retorna (lista_fechas_YYYY-MM, es_actual).
    Garantiza que fecha_inicio <= fecha_fin.

    Formatos soportados:
      - "04-2025" / "04/2025"          → mes/año
      - "01/07/2025"                    → dd/mm/yyyy
      - "Febrero 2025 – enero 2026"
      - "De 01/07/2025, 31/12/2025"
      - "2023 – 2024"
      - "Actual" / "Presente"
    """
    texto = linea.lower()
    fechas = []

    # Patrón 0: dd/mm/yyyy (David Dorado: "De 01/07/2025, 31/12/2025")
    for m in re.finditer(r"\b(\d{2})/(\d{2})/(\d{4})\b", linea):
        fechas.append(f"{m.group(3)}-{m.group(2).zfill(2)}")

    # Patrón 0b: YYYY-YYYY o YYYY – YYYY (Deimer: "2023-2025", "2022-2023")
    if not fechas:
        m = re.search(r"\b(20\d{2}|19\d{2})\s*[-–]\s*(20\d{2}|19\d{2})\b", linea)
        if m:
            fechas = [m.group(1), m.group(2)]

    # Patrón 1: mm-yyyy o mm/yyyy  (04-2025) — solo si no encontramos dd/mm/yyyy
    if not fechas:
        for m in re.finditer(r"\b(\d{2})\s*[-/]\s*(\d{4})\b", linea):
            fechas.append(f"{m.group(2)}-{m.group(1).zfill(2)}")

    # Patrón 2: nombre_mes año  (febrero 2025, Enero 2007)
    if not fechas:
        for mes_nombre, mes_num in sorted(MESES_ES.items(), key=lambda x: -len(x[0])):
            for m in re.finditer(rf"\b{mes_nombre}\b\s+(\d{{4}})\b", texto):
                fechas.append(f"{m.group(1)}-{mes_num}")

    # Patrón 3: solo año  (2023 – 2024)
    if not fechas:
        años = re.findall(r"\b(20\d{2}|19\d{2})\b", linea)
        fechas = list(dict.fromkeys(años))  # deduplicar manteniendo orden

    # Detectar "actual" / "presente"
    es_actual = bool(re.search(r"\b(actual|presente|la\s+fecha|vigente|hoy)\b", texto))

    # Garantizar orden cronológico
    if len(fechas) == 2 and re.match(r"\d{4}-\d{2}", fechas[0]) and re.match(r"\d{4}-\d{2}", fechas[1]):
        if fechas[0] > fechas[1]:
            fechas[0], fechas[1] = fechas[1], fechas[0]

    return fechas, es_actual


def es_linea_solo_fechas(linea):
    """Retorna True si la línea contiene principalmente fechas (sin mucho texto)."""
    linea_sin_fechas = re.sub(
        r"(\d{2}[-/]\d{4}|\b(20|19)\d{2}\b|"
        r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
        r"septiembre|octubre|noviembre|diciembre)\b|"
        r"\b(actual|presente|la\s+fecha|vigente)\b|"
        r"[–—\-/\s])", "", linea.lower()
    ).strip()
    return len(linea_sin_fechas) <= 5  # casi solo fechas


CARGOS_KEYWORDS = [
    "auditor", "coordinador", "gerente", "director", "analista",
    "contador", "contadora", "jefe", "supervisor", "lider", "líder",
    "asistente", "profesional", "asesor", "revisor", "subgerente",
    "tesorero", "auxiliar", "practicante", "pasante", "ingeniero",
    "administrador", "ejecutivo", "consultor", "socio", "representante"
]

EMPRESAS_SUFIJOS = ["sas", "sa", "s.a.s", "ltda", "s.a", "e.s.e", "e.i.c.e",
                    "epm", "grupo", "banco", "universidad", "corporacion",
                    "fundacion", "ministerio", "alcaldia", "gobernacion"]


def es_probable_cargo(linea):
    linea_l = linea.lower().strip()
    # Debe ser corto Y empezar o terminar con keyword de cargo, no estar en medio de una frase
    if len(linea) > 80 or es_linea_solo_fechas(linea):
        return False
    # No debe ser una oración (tiene verbo conjugado en primera persona = responsabilidad)
    if re.search(r"\b(particip[eé]|realic[eé]|apoy[eé]|desarroll[eé]|elabor[eé]|ejecut[eé]|"
                 r"gestion[eé]|coordin[eé]|supervis[eé]|implement[eé]|consolidé|me\s+desempeñ)\b", linea_l):
        return False
    # El keyword debe estar en posición prominente (primeras 3 palabras o es casi todo el texto)
    palabras = linea_l.split()
    primeras = " ".join(palabras[:4])
    return any(k in primeras or (k in linea_l and len(palabras) <= 5) for k in CARGOS_KEYWORDS)


def es_probable_empresa(linea):
    linea_l = linea.lower()
    return (
        any(s in linea_l for s in EMPRESAS_SUFIJOS) or
        (linea.isupper() and 3 < len(linea) < 80) or
        re.match(r"^[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s&.,]+$", linea.strip())
        and len(linea) < 80
    )


def parsear_experiencia(texto):
    """
    Extrae lista de trabajos con empresa, cargo, fechas, duración y responsabilidades.

    Soporta múltiples formatos de CV colombianos:
      - Empresa + fechas en misma línea: "SULICOR SAS  04-2025  12-2025"
      - Cargo primero, fechas en línea siguiente: "Auditor Especialista\\nFebrero 2025 – enero 2026"
      - Solo año en línea separada: "2023 – 2024"
      - Fechas con nombres de mes: "Enero 2007 - Octubre 2015"
    """
    trabajos = []
    if not texto.strip():
        return trabajos

    lineas = [l.strip() for l in texto.split("\n") if l.strip()]
    trabajo_actual = None
    responsabilidades = []
    linea_anterior = None

    def cerrar_trabajo():
        nonlocal trabajo_actual, responsabilidades
        if trabajo_actual:
            trabajo_actual["responsabilidades"] = responsabilidades
            # Calcular duración si tenemos ambas fechas en formato YYYY-MM
            ini = trabajo_actual.get("fecha_inicio")
            fin = trabajo_actual.get("fecha_fin")
            if ini and fin and re.match(r"\d{4}-\d{2}", ini) and re.match(r"\d{4}-\d{2}", fin):
                trabajo_actual["duracion_meses"] = calcular_duracion_meses(ini, fin)
            trabajos.append(trabajo_actual)
            responsabilidades = []

    for linea in lineas:
        fechas, es_actual = extraer_fechas_de_linea(linea)
        solo_fechas = es_linea_solo_fechas(linea)
        linea_sin_fechas = re.sub(
            r"(\d{2}\s*[-/]\s*\d{4}|\b(20|19)\d{2}\b\s*[–—\-]?\s*\b(20|19)\d{2}\b|\b(20|19)\d{2}\b|"
            r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            r"septiembre|octubre|noviembre|diciembre)\b)",
            "", linea, flags=re.IGNORECASE
        ).strip(" –—-/,")

        # ── PATRÓN ESPECIAL: "Empresa - Cargo" en una sola línea (Lorena style) ──
        if not solo_fechas and not fechas:
            emp_guion, cargo_guion = separar_empresa_cargo_guion(linea)
            if emp_guion and cargo_guion:
                cerrar_trabajo()
                trabajo_actual = {
                    "empresa": emp_guion,
                    "cargo": cargo_guion,
                    "fecha_inicio": None,
                    "fecha_fin": None,
                    "duracion_meses": None,
                    "responsabilidades": []
                }
                linea_anterior = linea
                continue

        # ── CASO 1: Línea con empresa + fechas juntas (ej: "SULICOR SAS 04-2025 12-2025") ──
        tiene_fechas_inline = len(fechas) >= 1 and not solo_fechas and len(linea_sin_fechas) > 3
        es_emp_con_fechas = tiene_fechas_inline and (
            es_probable_empresa(linea_sin_fechas) or es_probable_cargo(linea_sin_fechas)
        )

        # ── CASO 2: Línea de solo fechas que sigue a un cargo o empresa ──
        es_bloque_fechas = solo_fechas and len(fechas) >= 1 and linea_anterior is not None

        if es_emp_con_fechas:
            cerrar_trabajo()
            inicio = fechas[0] if fechas else None
            fin = fechas[1] if len(fechas) > 1 else ("presente" if es_actual else None)
            trabajo_actual = {
                "empresa": linea_sin_fechas.strip(),
                "cargo": None,
                "fecha_inicio": inicio,
                "fecha_fin": fin,
                "duracion_meses": None,
                "responsabilidades": []
            }

        elif es_bloque_fechas:
            inicio = fechas[0] if fechas else None
            fin = fechas[1] if len(fechas) > 1 else ("presente" if es_actual else None)

            if trabajo_actual is None:
                # Fechas solas sin trabajo abierto → abrimos trabajo, empresa/cargo vendrán después
                cerrar_trabajo()
                trabajo_actual = {
                    "empresa": None,
                    "cargo": None,
                    "fecha_inicio": inicio,
                    "fecha_fin": fin,
                    "duracion_meses": None,
                    "responsabilidades": []
                }
            else:
                # Ya tenemos trabajo abierto → las fechas pertenecen al cargo detectado antes
                if not trabajo_actual.get("fecha_inicio"):
                    trabajo_actual["fecha_inicio"] = inicio
                if not trabajo_actual.get("fecha_fin"):
                    trabajo_actual["fecha_fin"] = fin or ("presente" if es_actual else None)
                # Si la línea anterior era cargo y no lo habíamos asignado
                if linea_anterior and es_probable_cargo(linea_anterior) and not trabajo_actual.get("cargo"):
                    trabajo_actual["cargo"] = linea_anterior

        elif es_probable_cargo(linea) and not solo_fechas:
            if trabajo_actual is not None and not trabajo_actual.get("cargo"):
                # Trabajo abierto sin cargo: asignar
                # Si tampoco tiene empresa, la línea anterior puede serlo
                if not trabajo_actual.get("empresa") and linea_anterior and not es_linea_solo_fechas(linea_anterior) and not es_probable_cargo(linea_anterior):
                    trabajo_actual["empresa"] = linea_anterior
                trabajo_actual["cargo"] = linea
            elif trabajo_actual is not None:
                cerrar_trabajo()
                trabajo_actual = {
                    "empresa": None, "cargo": linea,
                    "fecha_inicio": None, "fecha_fin": None,
                    "duracion_meses": None, "responsabilidades": []
                }
            else:
                trabajo_actual = {
                    "empresa": None, "cargo": linea,
                    "fecha_inicio": None, "fecha_fin": None,
                    "duracion_meses": None, "responsabilidades": []
                }

        elif trabajo_actual is not None and not solo_fechas:
            # Si el trabajo no tiene empresa todavía y parece empresa
            if not trabajo_actual.get("empresa") and not trabajo_actual.get("cargo") and len(linea) < 70:
                # Primera línea después de fechas → probablemente empresa
                trabajo_actual["empresa"] = linea
            elif not trabajo_actual.get("empresa") and trabajo_actual.get("cargo") and es_probable_empresa(linea):
                trabajo_actual["empresa"] = linea
            else:
                # Es responsabilidad
                resp = re.sub(r"^[\d]+[.\-\)]\s*", "", linea).strip("•-– ")
                if resp and len(resp) > 8:
                    responsabilidades.append(resp)

        linea_anterior = linea

    cerrar_trabajo()
    trabajos_limpios = [t for t in trabajos if t.get("cargo") or t.get("empresa")]

    # ── Enriquecer con spaCy: rellenar empresa=None usando NER ──
    trabajos_limpios = enriquecer_trabajos_con_nlp(trabajos_limpios, texto)

    return trabajos_limpios


def parsear_educacion(texto):
    """Extrae lista de títulos con institución y año."""
    entradas = []
    if not texto.strip():
        return entradas

    lineas = [l.strip() for l in texto.split("\n") if l.strip()]
    entrada_actual = {}

    for linea in lineas:
        año = re.search(r"\b(19|20)\d{2}\b", linea)
        tiene_año = bool(año)

        instituciones_keywords = ["universidad", "corporacion", "corporación",
                                  "instituto", "colegio", "sena", "escuela", "politecnico"]
        es_institucion = any(k in linea.lower() for k in instituciones_keywords)

        titulos_keywords = ["contador", "administrador", "ingeniero", "licenciado",
                            "tecnico", "tecnólogo", "diplomado", "especialista", "magister"]
        es_titulo = any(k in linea.lower() for k in titulos_keywords)

        if tiene_año and not es_institucion:
            if entrada_actual:
                entradas.append(entrada_actual)
            entrada_actual = {"titulo": None, "institucion": None, "año": año.group()}

        elif es_titulo and not entrada_actual.get("titulo"):
            if not entrada_actual:
                entrada_actual = {}
            entrada_actual["titulo"] = linea

        elif es_institucion and not entrada_actual.get("institucion"):
            if not entrada_actual:
                entrada_actual = {}
            entrada_actual["institucion"] = linea

    if entrada_actual:
        entradas.append(entrada_actual)

    return entradas


def parsear_habilidades(texto):
    """Extrae habilidades como lista limpia."""
    if not texto.strip():
        return []

    items = re.split(r"[\n,;•\-]", texto)
    return [i.strip().capitalize() for i in items if len(i.strip()) > 2]


def parsear_cursos(texto):
    """Extrae cursos/certificaciones como lista."""
    return parsear_habilidades(texto)  # misma lógica


def parsear_contacto_desde_perfil(texto_completo):
    """Extrae email, teléfono y dirección del texto completo."""
    contacto = {}

    email = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", texto_completo)
    if email:
        contacto["email"] = email.group()

    telefono = re.search(r"\b3\d{2}[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2}\b", texto_completo)
    if telefono:
        contacto["telefono"] = re.sub(r"[-\s]", "", telefono.group())

    return contacto


def calcular_años_experiencia(trabajos):
    """Suma duración de todos los trabajos en años."""
    total_meses = sum(t.get("duracion_meses") or 0 for t in trabajos)
    return round(total_meses / 12, 1)


def extraer_skills_del_texto(texto_completo):
    """Busca skills técnicas y blandas en todo el CV."""
    texto_norm = limpiar_para_comparacion(texto_completo)
    tecnicas = [s.upper() for s in SKILLS_TECNICAS if s in texto_norm]
    blandas = [s.capitalize() for s in SKILLS_BLANDAS if s in texto_norm]
    return {"tecnicas": tecnicas, "blandas": blandas}


# ---------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL
# ---------------------------------------------------------------------------

def estructurar_cv(secciones, texto_completo=""):
    """
    Toma el dict de secciones {perfil, experiencia, educacion, habilidades, cursos}
    y retorna un JSON estructurado listo para ranking/matching.
    """
    experiencia = parsear_experiencia(secciones.get("experiencia", ""))
    educacion = parsear_educacion(secciones.get("educacion", ""))
    habilidades_lista = parsear_habilidades(secciones.get("habilidades", ""))
    cursos_lista = parsear_cursos(secciones.get("cursos", ""))
    contacto = parsear_contacto_desde_perfil(texto_completo)
    skills_detectadas = extraer_skills_del_texto(texto_completo)

    return {
        "contacto": contacto,
        "perfil_resumen": secciones.get("perfil", "").strip(),
        "experiencia": experiencia,
        "educacion": educacion,
        "habilidades": habilidades_lista,
        "skills_detectadas": skills_detectadas,
        "cursos": cursos_lista,
        "referencias": secciones.get("referencias", "").strip(),
        # Campos calculados para ranking
        "años_experiencia_total": calcular_años_experiencia(experiencia),
        "cantidad_empleos": len(experiencia),
    }
