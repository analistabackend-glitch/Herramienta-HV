"""Parser especializado para el "Formato Único Hoja de Vida - Persona Natural"
(Leyes 190 de 1995, 489 y 443 de 1998) del Estado colombiano."""

import re
from limpiar import limpiar_para_comparacion


# ---------------------------------------------------------------------------
# DETECCIÓN DEL FORMATO
# ---------------------------------------------------------------------------

MARCADORES_FUNCION_PUBLICA = [
    r"formato\s+[úu]nico",
    r"hoja\s+de\s+vida\s+persona\s+natural",
    r"leyes?\s+190\s+de\s+1995",
    r"489\s+y\s+443\s+de\s+1998",
    r"1\s+datos\s+personales",
    r"entidad\s+receptora",
    r"primer\s+apellido\s+segundo\s+apellido",
    r"libreta\s+militar",
]


def es_formato_funcion_publica(texto):
    """
    Detecta si el texto corresponde al Formato Único de Función Pública.

    Retorna True si encuentra 2 o más marcadores distintivos.
    Umbral bajo (2) porque los PDFs de formularios a veces están fragmentados.
    """
    texto_lower = texto.lower()
    encontrados = sum(1 for patron in MARCADORES_FUNCION_PUBLICA
                      if re.search(patron, texto_lower))
    return encontrados >= 2


# ---------------------------------------------------------------------------
# PARSERS DE SECCIONES DEL FORMULARIO
# ---------------------------------------------------------------------------

def _extraer_datos_personales(lineas):
    """
    Sección 1: DATOS PERSONALES
    Extrae nombre, cédula, email, teléfono, dirección.
    """
    datos = {}
    texto = "\n".join(lineas)

    # Email
    email = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", texto)
    if email:
        datos["email"] = email.group()

    # Teléfono colombiano
    tel = re.search(r"\b3\d{9}\b", re.sub(r"\s", "", texto))
    if tel:
        datos["telefono"] = tel.group()

    # Cédula
    cc = re.search(r"\b1\d{8,9}\b", texto)
    if cc:
        datos["cedula"] = cc.group()

    # Nombre: buscar después de "NOMBRES" o "PRIMER APELLIDO"
    nombre = _buscar_valor_campo(lineas, ["NOMBRES", "PRIMER APELLIDO", "SEGUNDO APELLIDO"])
    if nombre:
        datos["nombre_raw"] = nombre

    return datos


def _buscar_valor_campo(lineas, etiquetas):
    """
    En el formulario, los valores suelen estar en la línea siguiente a la etiqueta.
    Busca la primera etiqueta que aparezca y retorna el valor de la línea siguiente.
    """
    for i, linea in enumerate(lineas):
        linea_upper = linea.strip().upper()
        for etiqueta in etiquetas:
            if etiqueta in linea_upper and len(linea.strip()) < 60:
                # El valor está en la siguiente línea no vacía
                for j in range(i + 1, min(i + 4, len(lineas))):
                    valor = lineas[j].strip()
                    if valor and not valor.isupper() and len(valor) < 80:
                        return valor
    return None


def _extraer_educacion_formulario(lineas):
    """
    Sección 2: FORMACIÓN ACADÉMICA
    El formulario tiene columnas: MODALIDAD | SEMESTRES | GRADUADO | NOMBRE ESTUDIOS | AÑO
    Extrae títulos y años de graduación.
    """
    educacion = []
    texto = "\n".join(lineas)

    # Patrones de modalidad académica
    modalidades = {
        "POSTGRADO": "Postgrado",
        "PREGRADO": "Pregrado",
        "TECNICA": "Técnica",
        "TC": "Técnica",
        "TL": "Tecnológica",
        "ES": "Especialización",
        "MG": "Maestría",
        "DOC": "Doctorado",
    }

    for linea in lineas:
        linea_upper = linea.strip().upper()

        for codigo, nombre_modalidad in modalidades.items():
            if linea_upper.startswith(codigo) or f" {codigo} " in linea_upper:
                # Buscar nombre del programa en la misma línea
                # El formulario mezcla todo en una línea tras OCR
                resto = re.sub(
                    r"^(POSTGRADO|PREGRADO|TECNICA|TC|TL|ES|MG|DOC)\s*\d*\s*X?\s*",
                    "", linea, flags=re.IGNORECASE
                ).strip()

                # Buscar año en el texto cercano
                año = re.search(r"\b(20\d{2}|19\d{2})\b", linea)

                if resto and len(resto) > 4:
                    educacion.append({
                        "modalidad": nombre_modalidad,
                        "titulo": resto.split("  ")[0].strip(),
                        "año": año.group() if año else None,
                        "institucion": None  # el formulario separa institución en otra fila
                    })
                break

    # Buscar instituciones por nombre conocido
    instituciones_keywords = [
        "universidad", "corporacion", "politecnico", "institución",
        "escuela", "colegio", "sena", "unad", "esap"
    ]
    for i, linea in enumerate(lineas):
        if any(k in linea.lower() for k in instituciones_keywords):
            # Asociar a la última entrada de educación sin institución
            for entry in reversed(educacion):
                if not entry.get("institucion"):
                    entry["institucion"] = linea.strip()
                    break

    return educacion


def _extraer_experiencia_formulario(lineas):
    """
    Sección 5: EXPERIENCIA LABORAL
    El formulario tiene campos:
        - ENTIDAD / EMPRESA
        - CARGO / EMPLEO
        - FECHA INICIO (MES / AÑO)
        - FECHA RETIRO (MES / AÑO)
        - ÁREA / DEPENDENCIA
        - TIPO (PÚBLICO / PRIVADO)

    El OCR del PDF mezcla columnas, así que buscamos pares de etiquetas conocidas.
    """
    trabajos = []
    texto = "\n".join(lineas)

    # Buscar bloques de experiencia por etiquetas del formulario
    etiquetas_entidad = [
        "ENTIDAD O EMPRESA", "NOMBRE DE LA ENTIDAD", "EMPRESA",
        "RAZÓN SOCIAL", "ENTIDAD"
    ]
    etiquetas_cargo = [
        "CARGO O EMPLEO DESEMPEÑADO", "CARGO", "EMPLEO DESEMPEÑADO",
        "DENOMINACIÓN DEL CARGO"
    ]
    etiquetas_inicio = ["FECHA DE INICIO", "FECHA INICIO", "DESDE"]
    etiquetas_retiro = ["FECHA DE RETIRO", "FECHA RETIRO", "HASTA", "FECHA DE TERMINACIÓN"]

    # Estrategia: recorrer líneas buscando las etiquetas y capturar el valor siguiente
    i = 0
    trabajo_actual = {}

    while i < len(lineas):
        linea = lineas[i].strip().upper()

        # Detectar inicio de un nuevo bloque de experiencia
        if any(et in linea for et in [e.upper() for e in etiquetas_entidad]):
            if trabajo_actual.get("empresa") or trabajo_actual.get("cargo"):
                trabajos.append(_normalizar_trabajo_formulario(trabajo_actual))
            trabajo_actual = {}
            # Valor en línea siguiente
            if i + 1 < len(lineas):
                trabajo_actual["empresa"] = lineas[i + 1].strip()
                i += 2
                continue

        elif any(et in linea for et in [e.upper() for e in etiquetas_cargo]):
            if i + 1 < len(lineas):
                trabajo_actual["cargo"] = lineas[i + 1].strip()
                i += 2
                continue

        elif any(et in linea for et in [e.upper() for e in etiquetas_inicio]):
            # Fecha puede estar en la misma línea o en la siguiente
            año = re.search(r"\b(20\d{2}|19\d{2})\b", linea)
            mes = re.search(r"\b(0?[1-9]|1[0-2])\b", linea)
            if not año and i + 1 < len(lineas):
                año = re.search(r"\b(20\d{2}|19\d{2})\b", lineas[i + 1])
                mes = re.search(r"\b(0?[1-9]|1[0-2])\b", lineas[i + 1])
            if año:
                m = mes.group().zfill(2) if mes else "01"
                trabajo_actual["fecha_inicio"] = f"{año.group()}-{m}"

        elif any(et in linea for et in [e.upper() for e in etiquetas_retiro]):
            año = re.search(r"\b(20\d{2}|19\d{2})\b", linea)
            mes = re.search(r"\b(0?[1-9]|1[0-2])\b", linea)
            if not año and i + 1 < len(lineas):
                año = re.search(r"\b(20\d{2}|19\d{2})\b", lineas[i + 1])
                mes = re.search(r"\b(0?[1-9]|1[0-2])\b", lineas[i + 1])
            if año:
                m = mes.group().zfill(2) if mes else "12"
                trabajo_actual["fecha_fin"] = f"{año.group()}-{m}"
            else:
                # Buscar "CARGO ACTUAL" o similar como indicador de empleo vigente
                if re.search(r"(actual|vigente|presente)", linea.lower()):
                    trabajo_actual["fecha_fin"] = "presente"

        i += 1

    # Guardar último trabajo
    if trabajo_actual.get("empresa") or trabajo_actual.get("cargo"):
        trabajos.append(_normalizar_trabajo_formulario(trabajo_actual))

    # Si no encontró nada con etiquetas (OCR fragmentado), intentar heurística
    if not trabajos:
        trabajos = _extraer_experiencia_heuristica_formulario(lineas)

    return trabajos


def _extraer_experiencia_heuristica_formulario(lineas):
    """
    Fallback para formularios con OCR muy fragmentado.
    Busca patrones de año y texto mayúscula que sean probables entidades.
    """
    trabajos = []
    trabajo_actual = None

    for linea in lineas:
        linea_strip = linea.strip()
        if not linea_strip:
            continue

        # Años en formato "MES AÑO MES AÑO" (columnas del formulario)
        años = re.findall(r"\b(20\d{2}|19\d{2})\b", linea_strip)

        # Línea completamente en mayúsculas y razonablemente corta = posible entidad
        es_entidad = (
            linea_strip.isupper() and 5 < len(linea_strip) < 80 and
            not any(k in linea_strip for k in [
                "CARGO", "ENTIDAD", "FECHA", "ÁREA", "TIPO",
                "EXPERIENCIA", "FORMACIÓN", "DATOS"
            ])
        )

        if es_entidad:
            if trabajo_actual:
                trabajos.append(trabajo_actual)
            trabajo_actual = {
                "empresa": linea_strip,
                "cargo": None,
                "fecha_inicio": años[0] if años else None,
                "fecha_fin": años[1] if len(años) > 1 else None,
                "duracion_meses": None,
                "responsabilidades": []
            }
        elif trabajo_actual and años and not trabajo_actual.get("fecha_inicio"):
            trabajo_actual["fecha_inicio"] = años[0]
            if len(años) > 1:
                trabajo_actual["fecha_fin"] = años[1]

    if trabajo_actual:
        trabajos.append(trabajo_actual)

    return trabajos


def _normalizar_trabajo_formulario(trabajo):
    """Normaliza un trabajo del formulario al esquema estándar."""
    from estructurar_cv import calcular_duracion_meses
    ini = trabajo.get("fecha_inicio")
    fin = trabajo.get("fecha_fin")
    dur = None
    if ini and fin and fin != "presente":
        try:
            dur = calcular_duracion_meses(ini, fin)
        except Exception:
            pass
    return {
        "empresa": trabajo.get("empresa"),
        "cargo": trabajo.get("cargo"),
        "fecha_inicio": ini,
        "fecha_fin": fin,
        "duracion_meses": dur,
        "responsabilidades": trabajo.get("responsabilidades", [])
    }


# ---------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL: parsear CV de Función Pública completo
# ---------------------------------------------------------------------------

def parsear_cv_funcion_publica(texto):
    """
    Parsea el Formato Único de Hoja de Vida y retorna el mismo esquema JSON
    estándar que usa el pipeline para CVs normales.

    Args:
        texto: texto crudo extraído del PDF

    Returns:
        dict con el mismo esquema que estructurar_cv.estructurar_cv()
    """
    from estructurar_cv import extraer_skills_del_texto, calcular_años_experiencia

    lineas = [l.strip() for l in texto.split("\n")]

    # ── Dividir el texto en secciones por los números del formulario ──
    secciones = _dividir_secciones_formulario(lineas)

    datos_personales = _extraer_datos_personales(
        secciones.get("datos_personales", [])
    )
    educacion = _extraer_educacion_formulario(
        secciones.get("formacion_academica", [])
    )
    experiencia = _extraer_experiencia_formulario(
        secciones.get("experiencia_laboral", [])
    )
    skills = extraer_skills_del_texto(texto)

    # Construir contacto desde datos personales
    contacto = {k: v for k, v in datos_personales.items()
                if k in ("email", "telefono")}

    return {
        "tipo_formato": "funcion_publica",  # marcador para identificar este formato
        "contacto": contacto,
        "perfil_resumen": "",  # el formulario no tiene perfil libre
        "experiencia": experiencia,
        "educacion": educacion,
        "habilidades": [],
        "skills_detectadas": skills,
        "cursos": [],
        "referencias": "",
        "años_experiencia_total": calcular_años_experiencia(experiencia),
        "cantidad_empleos": len(experiencia),
    }


def _dividir_secciones_formulario(lineas):
    """
    El formulario tiene secciones numeradas:
        1 DATOS PERSONALES
        2 FORMACIÓN ACADÉMICA
        3 EDUCACIÓN PARA EL TRABAJO
        4 EXPERIENCIA DOCENTE
        5 EXPERIENCIA LABORAL
        6 OTROS DATOS
    """
    SECCIONES_FORMULARIO = {
        r"^1\s+datos\s+personales": "datos_personales",
        r"^2\s+formaci[oó]n\s+acad[eé]mica": "formacion_academica",
        r"^3\s+educaci[oó]n\s+para\s+el\s+trabajo": "educacion_trabajo",
        r"^4\s+experiencia\s+docente": "experiencia_docente",
        r"^5\s+experiencia\s+laboral": "experiencia_laboral",
        r"^6\s+otros\s+datos": "otros_datos",
    }

    secciones = {v: [] for v in SECCIONES_FORMULARIO.values()}
    seccion_actual = "datos_personales"  # default

    for linea in lineas:
        linea_lower = linea.lower().strip()
        detectada = False
        for patron, nombre in SECCIONES_FORMULARIO.items():
            if re.match(patron, linea_lower):
                seccion_actual = nombre
                detectada = True
                break
        if not detectada and linea.strip():
            if seccion_actual in secciones:
                secciones[seccion_actual].append(linea)

    return secciones
