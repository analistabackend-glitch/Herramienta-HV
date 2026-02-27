import re

# ---------------------------------------------------------------------------
# ENCABEZADOS DE SECCIÓN
# Mapeamos variantes de encabezado → clave interna del JSON
# ---------------------------------------------------------------------------
ENCABEZADOS = {
    "perfil": r"\b(perfil|resumen|sobre\s*m[ií]|acerca\s*de)\b",
    "experiencia": r"\b(experiencias?\s*(laboral(es)?|profesional(es)?)?|experencias?\s*(laboral(es)?|profesional(es)?)?|trayectoria|historial\s*laboral)\b",
    "educacion": r"\b(educaci[oó]n|formaci[oó]n|estudios|t[íi]tulos?|acad[eé]mica)\b",
    "habilidades": r"\b(habilidades|competencias|destrezas|conocimientos|skills)\b",
    "cursos": r"^(cursos?|certificaciones?|diplomados?|capacitaciones?)[\s:]*$",
    "referencias": r"\b(referencias?|referencia\s*personal)\b",
    "contacto": r"\b(contacto|datos\s*personales?|informaci[oó]n\s*personal)\b",
}

# Encabezados que son secciones "principales" para el JSON de salida
SECCIONES_PRINCIPALES = {"perfil", "experiencia", "educacion", "habilidades", "cursos", "referencias"}


def es_encabezado(linea):
    """
    Detecta si una línea es un encabezado de sección.
    Retorna la clave de sección o None.
    """
    linea_limpia = linea.strip()
    if not linea_limpia or len(linea_limpia) > 80:
        return None

    linea_lower = linea_limpia.lower()

    for seccion, patron in ENCABEZADOS.items():
        if re.search(patron, linea_lower):
            return seccion

    return None


def dividir_secciones(texto):
    """
    Divide el texto en secciones usando una máquina de estados.
    
    En vez de clasificar línea por línea (lo que falla porque "SULICOR SAS"
    no contiene keywords), detectamos los ENCABEZADOS y agrupamos todo lo que
    sigue hasta el próximo encabezado en esa sección.
    """
    lineas = texto.split("\n")

    # Estado inicial: todo cae en "perfil" hasta encontrar otro encabezado
    seccion_actual = "perfil"
    acumulador = {sec: [] for sec in SECCIONES_PRINCIPALES}
    acumulador["perfil"] = []

    for linea in lineas:
        seccion_detectada = es_encabezado(linea)

        if seccion_detectada and seccion_detectada in SECCIONES_PRINCIPALES:
            seccion_actual = seccion_detectada
            # No agregamos la línea del encabezado en sí, solo el contenido
            continue

        # Ignorar líneas vacías al inicio de sección
        if not linea.strip() and not acumulador[seccion_actual]:
            continue

        if seccion_actual in acumulador:
            acumulador[seccion_actual].append(linea)

    # Unir en texto por sección
    resultado = {}
    for sec in SECCIONES_PRINCIPALES:
        resultado[sec] = "\n".join(acumulador[sec]).strip()

    return resultado
