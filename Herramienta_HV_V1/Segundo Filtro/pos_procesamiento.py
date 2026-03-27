from datetime import datetime
import re


# ──────────────────────────────────────────────
# Mapas de meses
# ──────────────────────────────────────────────

MESES_ES = {
    "ene": 1, "enero": 1, "january": 1, "jan": 1,
    "feb": 2, "febrero": 2, "february": 2,
    "mar": 3, "marzo": 3, "march": 3,
    "abr": 4, "abril": 4, "april": 4, "apr": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "junio": 6, "june": 6,
    "jul": 7, "julio": 7, "july": 7,
    "ago": 8, "agosto": 8, "august": 8, "aug": 8,
    "sep": 9, "sept": 9, "septiembre": 9, "september": 9,
    "oct": 10, "octubre": 10, "october": 10,
    "nov": 11, "noviembre": 11, "november": 11,
    "dic": 12, "diciembre": 12, "december": 12, "dec": 12,
}

# Palabras que significan "actualmente"
PALABRAS_ACTUAL = {
    "actual", "actualmente", "actualidad", "act",
    "presente", "present", "current", "currently",
    "hoy", "today", "vigente", "labor",
    "contrato labor",          # caso 14: fecha_fin con texto de tipo de contrato
}


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _es_actual(valor: str) -> bool:
    """True si el valor representa 'actualmente'."""
    v = valor.strip().lower()
    # coincidencia exacta
    if v in PALABRAS_ACTUAL:
        return True
    # contiene alguna palabra clave
    for p in PALABRAS_ACTUAL:
        if re.search(rf"\b{re.escape(p)}\b", v):
            return True
    return False


def _mes_nombre_a_num(nombre: str) -> int | None:
    """Convierte nombre de mes (cualquier idioma/abrev) a número 1-12."""
    key = nombre.strip().lower().rstrip(".")
    return MESES_ES.get(key)


def _anio_valido(a: int) -> bool:
    return 1950 <= a <= datetime.now().year + 2

def limpiar_fecha(fecha: str) -> str:
    if not fecha:
        return ""

    fecha = str(fecha).lower().strip()

    # ✅ normalizar SOLO guiones raros (NO el normal "-")
    fecha = fecha.replace("–", "-")
    fecha = fecha.replace("—", "-")

    # quitar palabras innecesarias
    fecha = re.sub(r"\b(del|de|hasta)\b", " ", fecha)

    # quitar comas
    fecha = fecha.replace(",", " ")

    # eliminar dobles espacios
    fecha = re.sub(r"\s+", " ", fecha).strip()

    return fecha

# ──────────────────────────────────────────────
# Detector de rango en un solo campo
# ──────────────────────────────────────────────

_SEP_RANGO = re.compile(
    r"\s*(?:[-–—]|hasta|a)\s*",
    re.IGNORECASE,
)

def _dividir_rango(valor: str):
    """
    Si el campo contiene un rango (ej. '2023-2025', 'Feb 2023 – Actual',
    'Febrero 2023 hasta Actual', 'Jul 2022 - Present') lo divide en
    (inicio, fin). Si no es un rango devuelve (valor, None).
    """
    # Evitar confundir '04-2025' (mes-año) con un rango
    # Un rango siempre tiene dos partes que contienen año (4 dígitos)
    partes = _SEP_RANGO.split(valor, maxsplit=1)
    if len(partes) == 2:
        izq, der = partes[0].strip(), partes[1].strip()
        # Verificar que al menos la parte izquierda tenga un año
        if re.search(r"\d{4}", izq):
            return izq, der
    return valor, None


# ──────────────────────────────────────────────
# Normalizador principal
# ──────────────────────────────────────────────

def normalizar_fecha(fecha):
    """
    Convierte múltiples formatos de fecha de CV a YYYY-MM.
    Si detecta 'actual', devuelve None.
    """

    if not fecha:
        return None

    fecha = limpiar_fecha(fecha)

    # normalizar separadores raros
    fecha = fecha.replace("–", "-")
    fecha = fecha.replace("—", "-")

    # quitar palabras innecesarias
    fecha = re.sub(r"\b(del|de)\b", " ", fecha)

    # arreglar cosas como "-2024"
    fecha = re.sub(r"\s*-\s*(\d{4})", r" \1", fecha)

    # quitar dobles espacios
    fecha = re.sub(r"\s+", " ", fecha).strip()
    
    # quitar palabra "hasta"
    fecha = re.sub(r"^hasta\s+", "", fecha)


    if not fecha:
        return None

    # limpiar puntos
    fecha = re.sub(r"\.(\s)", r"\1", fecha)
    fecha = re.sub(r"\.$", "", fecha)

    # detectar palabras tipo "actual"
    if _es_actual(fecha):
        return None

    # YYYY-MM
    if re.fullmatch(r"\d{4}-\d{2}", fecha):
        return fecha

    # solo año
    if re.fullmatch(r"\d{4}", fecha):
        return fecha + "-01"
    
    # DD/MM/YYYY  (19/01/2026 → 2026-01)
    m = re.fullmatch(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", fecha)
    if m:
        mes = int(m.group(2))
        anio = int(m.group(3))

        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # DD/MM/YY  (01/06/25 → 2025-06)
    m = re.fullmatch(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})", fecha)
    if m:
        mes = int(m.group(2))
        anio = int(m.group(3))

        if anio <= 30:
            anio = 2000 + anio
        else:
            anio = 1900 + anio

        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"
        
    # MM/YY  (06/25 → 2025-06)
    m = re.fullmatch(r"(\d{1,2})[/\-](\d{2})", fecha)
    if m:
        mes = int(m.group(1))
        anio = int(m.group(2))

        if anio <= 30:
            anio = 2000 + anio
        else:
            anio = 1900 + anio

        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"
    # YYYY/MM/DD
    m = re.fullmatch(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", fecha)
    if m:
        anio = int(m.group(1))
        mes = int(m.group(2))

        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"
    # YYYYMM
    m = re.fullmatch(r"(\d{4})(\d{2})", fecha)
    if m:
        anio = int(m.group(1))
        mes = int(m.group(2))

        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"    
    
    # MMYYYY
    m = re.fullmatch(r"(\d{2})(\d{4})", fecha)
    if m:
        mes = int(m.group(1))
        anio = int(m.group(2))

        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"
        
    # YYYY-MM-DD
    m = re.fullmatch(r"(\d{4})\-(\d{1,2})\-(\d{1,2})", fecha)
    if m:
        anio = int(m.group(1))
        mes = int(m.group(2))

        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"
    # DD de Mes YYYY
    m = re.fullmatch(
        r"\d{1,2}\s+de\s+([a-záéíóúüñ]+)\s+(\d{4})",
        fecha
    )
    if m:
        mes = _mes_nombre_a_num(m.group(1))
        anio = int(m.group(2))
        if mes and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # Mes DD YYYY
    m = re.fullmatch(
        r"([a-záéíóúüñ]+)\s+\d{1,2}\s+(\d{4})",
        fecha
    )
    if m:
        mes = _mes_nombre_a_num(m.group(1))
        anio = int(m.group(2))
        if mes and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # Mon DD YYYY
    m = re.fullmatch(
        r"([a-z]{3,})\s+\d{1,2}\s+(\d{4})",
        fecha
    )
    if m:
        mes = _mes_nombre_a_num(m.group(1))
        anio = int(m.group(2))
        if mes and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # MM/YYYY o MM-YYYY
    m = re.fullmatch(r"(\d{1,2})[/\-](\d{4})", fecha)
    if m:
        mes = int(m.group(1))
        anio = int(m.group(2))
        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # YYYY/MM
    m = re.fullmatch(r"(\d{4})[/\-](\d{1,2})", fecha)
    if m:
        anio = int(m.group(1))
        mes = int(m.group(2))
        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # MM.YYYY
    m = re.fullmatch(r"(\d{1,2})\.(\d{4})", fecha)
    if m:
        mes = int(m.group(1))
        anio = int(m.group(2))
        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # YYYY.MM
    m = re.fullmatch(r"(\d{4})\.(\d{1,2})", fecha)
    if m:
        anio = int(m.group(1))
        mes = int(m.group(2))
        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # Mes/YYYY
    m = re.fullmatch(r"([a-záéíóúüñ]+)[/\-](\d{4})", fecha)
    if m:
        mes = _mes_nombre_a_num(m.group(1))
        anio = int(m.group(2))
        if mes and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # Mes.AAAA
    m = re.fullmatch(r"([a-záéíóúüñ]+)\.(\d{4})", fecha)
    if m:
        mes = _mes_nombre_a_num(m.group(1))
        anio = int(m.group(2))
        if mes and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # MesAAAA
    m = re.fullmatch(r"([a-záéíóúüñ]{3,})(\d{4})", fecha)
    if m:
        mes = _mes_nombre_a_num(m.group(1))
        anio = int(m.group(2))
        if mes and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # Mes YYYY
    m = re.fullmatch(
        r"([a-záéíóúüñ]+)\s+(?:de\s+)?(\d{4})",
        fecha
    )
    if m:
        mes = _mes_nombre_a_num(m.group(1))
        anio = int(m.group(2))
        if mes and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    # YYYY Mes
    m = re.fullmatch(
        r"(\d{4})\s+([a-záéíóúüñ]+)",
        fecha
    )
    if m:
        anio = int(m.group(1))
        mes = _mes_nombre_a_num(m.group(2))
        if mes and _anio_valido(anio):
            return f"{anio}-{mes:02d}"
        
    # Mes DD YYYY
    m = re.fullmatch(
        r"([a-záéíóúüñ]+)\s+\d{1,2}\s+(\d{4})",
        fecha
    )

    # DD MON YYYY  (28 NOV 2018)
    m = re.fullmatch(
        r"(\d{1,2})\s+([a-záéíóúüñ]{3,})\s+(\d{4})",
        fecha
    )
    if m:
        mes = _mes_nombre_a_num(m.group(2))
        anio = int(m.group(3))
        if mes and _anio_valido(anio):
            return f"{anio}-{mes:02d}"
        
    # DD Mes del YYYY
    m = re.fullmatch(
        r"(\d{1,2})\s+([a-záéíóúüñ]+)\s+(?:del|de)\s+(\d{4})",
        fecha
    )
    if m:
        mes = _mes_nombre_a_num(m.group(2))
        anio = int(m.group(3))
        if mes and _anio_valido(anio):
            return f"{anio}-{mes:02d}"
    
    # DD MM YYYY con separadores raros
    m = re.fullmatch(
        r"(\d{1,2})\s*[–\- ]\s*(\d{1,2})\s*[–\- ]\s*(\d{4})",
        fecha
    )
    if m:
        mes = int(m.group(2))
        anio = int(m.group(3))
        if 1 <= mes <= 12 and _anio_valido(anio):
            return f"{anio}-{mes:02d}"
    

    # Mes AA  (Abr 22 → 2022-04)
    m = re.fullmatch(r"([a-záéíóúüñ]+)\s+(\d{2})", fecha)
    if m:
        mes = _mes_nombre_a_num(m.group(1))
        anio = int(m.group(2))

        if anio <= 30:
            anio = 2000 + anio
        else:
            anio = 1900 + anio

        if mes and _anio_valido(anio):
            return f"{anio}-{mes:02d}"

    

    return None


# ──────────────────────────────────────────────
# Separador de rangos en un campo
# ──────────────────────────────────────────────

def separar_rango_si_aplica(exp: dict) -> dict:
    """
    Detecta rangos dentro de fecha_inicio y los separa.
    Ejemplos:
      fecha_inicio="2023-2025", fecha_fin=""  →  inicio=2023, fin=2025
      fecha_inicio="Feb 2023 - Ene 2025"     →  inicio=Feb 2023, fin=Ene 2025
      fecha_inicio="Febrero 2023 – Actual"   →  inicio=Febrero 2023, fin=Actual
    """
    fi = str(exp.get("fecha_inicio") or "").strip()
    ff = str(exp.get("fecha_fin") or "").strip()

    # Solo procesamos si fecha_fin está vacía/nula y fecha_inicio parece rango
    parte_ini, parte_fin = _dividir_rango(fi)

    if parte_fin is not None:
        exp["fecha_inicio"] = parte_ini.strip()
        # Solo sobreescribir fecha_fin si estaba vacía
        if not ff:
            exp["fecha_fin"] = parte_fin.strip()

    return exp


# ──────────────────────────────────────────────
# Cálculo de meses
# ──────────────────────────────────────────────
def meses_entre(inicio, fin):

    inicio_norm = normalizar_fecha(inicio)
    fin_norm    = normalizar_fecha(fin)

    if not inicio_norm:
        return 0

    if not fin_norm:
        fin_norm = datetime.now().strftime("%Y-%m")

    try:
        d1 = datetime.strptime(inicio_norm, "%Y-%m")
        d2 = datetime.strptime(fin_norm,    "%Y-%m")
    except ValueError:
        return 0

    diff = (d2.year - d1.year) * 12 + (d2.month - d1.month)

    if d2 < d1:
        return 0

    # ✅ NUEVO: mismo mes → cuenta como 1 mes trabajado
    if diff == 0:
        return 1

    return max(diff, 0)

def meses_entre(inicio, fin):

    inicio_norm = normalizar_fecha(inicio)
    fin_norm    = normalizar_fecha(fin)

    if not inicio_norm:
        return 0

    if not fin_norm:
        fin_norm = datetime.now().strftime("%Y-%m")

    try:
        d1 = datetime.strptime(inicio_norm, "%Y-%m")
        d2 = datetime.strptime(fin_norm,    "%Y-%m")
    except ValueError:
        return 0

    diff = (d2.year - d1.year) * 12 + (d2.month - d1.month)
    if d2 < d1:
        return 0

    return max(diff, 0)


# ──────────────────────────────────────────────
# Detección de gaps
# ──────────────────────────────────────────────

def detectar_gaps(experiencias: list, umbral_meses: int = 3) -> list:
    """
    Compara pares consecutivos (ordenados por inicio) y reporta
    los huecos mayores al umbral.
    """
    fechadas = []
    for exp in experiencias:
        ini = normalizar_fecha(exp.get("fecha_inicio"))
        fin = normalizar_fecha(exp.get("fecha_fin"))
        if ini:
            fechadas.append((ini, fin or datetime.now().strftime("%Y-%m"), exp))

    fechadas.sort(key=lambda x: x[0])

    gaps = []
    for i in range(1, len(fechadas)):
        fin_anterior = fechadas[i - 1][1]
        ini_actual   = fechadas[i][0]
        meses_gap = meses_entre(fin_anterior, ini_actual)
        if meses_gap >= umbral_meses:
            gaps.append({
                "entre": [
                    fechadas[i - 1][2].get("empresa", ""),
                    fechadas[i][2].get("empresa", ""),
                ],
                "meses": meses_gap,
            })

    return gaps


# ──────────────────────────────────────────────
# Función principal
# ──────────────────────────────────────────────

def procesar(data: dict) -> dict:

    total_meses = 0

    for exp in data.get("experiencia", []):

        # 1️⃣ Separar rangos si vienen en un solo campo
        exp = separar_rango_si_aplica(exp)

        fecha_inicio_raw = exp.get("fecha_inicio")
        fecha_fin_raw = str(exp.get("fecha_fin") or "").strip()

        # 2️⃣ Clasificar tipo de fecha_fin
        if _es_actual(fecha_fin_raw):

            exp["fecha_fin"] = ""
            exp["es_actual"] = True

            meses = meses_entre(fecha_inicio_raw, None)

        elif not fecha_fin_raw:

            exp["fecha_fin"] = ""
            exp["es_actual"] = False

            meses = 12

        else:

            exp["es_actual"] = False

            meses = meses_entre(fecha_inicio_raw, fecha_fin_raw)

        # 3️⃣ Normalizar fechas
        exp["fecha_inicio_norm"] = normalizar_fecha(fecha_inicio_raw)

        exp["fecha_fin_norm"] = (
            normalizar_fecha(fecha_fin_raw)
            if not exp["es_actual"] and fecha_fin_raw
            else None
        )

        # 4️⃣ Corregir fechas invertidas automáticamente
        fi = exp["fecha_inicio_norm"]
        ff = exp["fecha_fin_norm"]

        if fi and ff:
            try:

                d1 = datetime.strptime(fi, "%Y-%m")
                d2 = datetime.strptime(ff, "%Y-%m")

                if d2 < d1:
                    exp["fecha_inicio_norm"], exp["fecha_fin_norm"] = ff, fi

            except ValueError:
                pass

        # 5️⃣ Guardar duración
        exp["duracion_meses"] = meses

        total_meses += meses

    # 6️⃣ Estadísticas generales
    cantidad = len(data.get("experiencia", []))

    promedio = total_meses / cantidad if cantidad else 0

    data["años_experiencia_total"] = round(total_meses / 12, 2)

    data["cantidad_empleos"] = cantidad

    # 7️⃣ Estabilidad laboral
    data["estabilidad_laboral"] = {

        "promedio_meses_por_empleo": round(promedio, 1),

        "empleos_menos_6_meses": sum(
            1 for e in data.get("experiencia", [])
            if e.get("duracion_meses", 0) < 6
        ),

        "gaps_detectados": detectar_gaps(data.get("experiencia", [])),
    }

    return data


# ──────────────────────────────────────────────
# Tests rápidos (python pos_procesamiento.py)
# ──────────────────────────────────────────────

if __name__ == "__main__":

    casos = [
        # (fecha_inicio, fecha_fin, esperado_actual, esperado_meses_fijo, descripcion)
        # Caso (b): fin vacio, NO es actual → es_actual=False, duracion=12
        ("2025",             "",              False, 12,   "Solo anio, fin vacio → 12m NO actual"),
        ("2023",             "",              False, 12,   "Anio pasado, fin vacio → 12m NO actual"),
        # Caso (a): fin = palabra actual → es_actual=True, meses hasta hoy
        ("Feb.2025",         "Actualmente",   True,  None, "Mes.Anio - Actualmente"),
        ("Mar2023",          "Current",       True,  None, "Current"),
        ("05/2025",          "Actual",        True,  None, "MM/YYYY - Actual"),
        ("mayo 2019",        "actualidad",    True,  None, "actualidad"),
        ("25 de junio 2025", "contrato labor",True,  None, "contrato labor → actual"),
        ("Febrero 2023",     "Actual",        True,  None, "Actual"),
        ("ABRIL/2024",       "ACTUALMENTE",   True,  None, "ACTUALMENTE mayuscula"),
        ("Febrero 2023 - Actual", "",         True,  None, "Rango guion largo → actual"),
        ("2019 - Actualmente","",             True,  None, "Rango anio-actual"),
        ("Jul 2022 - Present","",             True,  None, "Rango ingles Present"),
        # Caso (c): fin con fecha concreta → es_actual=False, meses calculados
        ("Junio 2022",       "Ene. 2025",     False, None, "Mes Anio completo → 31m"),
        ("Abril de 2023",    "Enero de 2026", False, None, "Mes de Anio → 33m"),
        ("2023-2025",        "",              False, None, "Rango en inicio → 24m"),
        ("AGO/2024",         "ENE/2025",      False, None, "Barra mayuscula → 5m"),
        ("04-2025",          "12-2025",       False, None, "MM-YYYY → 8m"),
        ("May2024",          "Aug2025",       False, None, "MesAAAA ingles → 15m"),
        ("12/2022",          "05/2025",       False, None, "MM/YYYY ambos → 29m"),
        ("01/07/2025",       "31/12/2025",    False, None, "DD/MM/YYYY → 5m"),
        ("17 de octubre 2018","30 de junio 2024",False,None,"D de Mes Anio → 68m"),
        ("Enero 2007",       "Octubre 2015",  False, None, "Mes Anio largo → 105m"),
        ("Julio 2017",       "Diciembre 2021",False, None, "Mes Anio → 53m"),
        ("NOVIEMBRE/2021",   "FEBRERO/2024",  False, None, "Barra mayuscula ambos → 27m"),
        ("septiembre 2019",  "junio 2025",    False, None, "minusculas → 69m"),
        ("Feb 2023 - Ene 2025","",            False, None, "Rango con meses → 23m"),
    ]

    OK = "OK"
    FAIL = "FAIL"

    print(f"{'CASO':<42} {'INICIO_N':<12} {'FIN_N':<12} {'MESES':>6}  {'ACT':<5} {'RES'}")
    print("-" * 95)

    errores = 0
    for fi, ff, exp_actual, exp_meses_fijo, desc in casos:
        exp = {"fecha_inicio": fi, "fecha_fin": ff, "empresa": "Test", "cargo": ""}
        exp = separar_rango_si_aplica(exp)
        ff2 = str(exp.get("fecha_fin") or "").strip()

        if _es_actual(ff2):
            es_act = True
            meses  = meses_entre(exp["fecha_inicio"], None)
        elif not ff2:
            es_act = False
            meses  = 12
        else:
            es_act = False
            meses  = meses_entre(exp["fecha_inicio"], ff2)

        ini_n = normalizar_fecha(exp["fecha_inicio"])
        fin_n = normalizar_fecha(ff2) if not es_act and ff2 else None

        ok_act   = (es_act == exp_actual)
        ok_meses = (exp_meses_fijo is None) or (meses == exp_meses_fijo)
        result   = OK if (ok_act and ok_meses) else FAIL
        if result == FAIL:
            errores += 1

        act_str = "si" if es_act else ""
        print(f"{desc:<42} {str(ini_n):<12} {str(fin_n):<12} {meses:>6}  {act_str:<5} {result}")

    print()
    print(f"{'Todos los tests pasaron' if errores == 0 else str(errores) + ' test(s) fallaron'}")
