import re
import unicodedata


def limpiar_texto(texto):
    """
    Limpia el texto conservando tildes y caracteres especiales del español.
    
    IMPORTANTE: No usar encode('ascii') porque elimina tildes, y spaCy / 
    los patrones regex en español las necesitan para funcionar bien.
    """
    # Normalizar unicode sin eliminar tildes (NFC conserva, NFKD+ascii elimina)
    texto = unicodedata.normalize("NFC", texto)

    # Eliminar caracteres de control excepto saltos de línea y tabulaciones
    texto = re.sub(r"[^\w\s\n\-@./,áéíóúüñÁÉÍÓÚÜÑ]", " ", texto)

    # Colapsar espacios/tabs múltiples (pero no saltos de línea)
    texto = re.sub(r"[ \t]+", " ", texto)

    # Limpiar líneas individualmente
    lineas = [linea.strip() for linea in texto.split("\n")]

    # Eliminar líneas completamente vacías duplicadas
    lineas_limpias = []
    linea_vacia_anterior = False
    for linea in lineas:
        if linea == "":
            if not linea_vacia_anterior:
                lineas_limpias.append(linea)
            linea_vacia_anterior = True
        else:
            lineas_limpias.append(linea)
            linea_vacia_anterior = False

    return "\n".join(lineas_limpias).strip()


def limpiar_para_comparacion(texto):
    """
    Versión más agresiva para comparaciones y matching:
    minúsculas, sin tildes, sin puntuación.
    Usar SOLO para scoring/matching, no para el JSON de salida.
    """
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    texto = texto.lower()
    texto = re.sub(r"[^\w\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()
