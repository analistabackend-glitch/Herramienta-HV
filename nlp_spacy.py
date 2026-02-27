import re

# ---------------------------------------------------------------------------
# CARGA DEL MODELO — con fallback si no está instalado
# ---------------------------------------------------------------------------

_nlp = None
_SPACY_DISPONIBLE = False


def cargar_modelo():
    """Carga es_core_news_lg una sola vez (singleton). Retorna False si falla."""
    global _nlp, _SPACY_DISPONIBLE
    if _SPACY_DISPONIBLE:
        return True
    try:
        import spacy
        _nlp = spacy.load("es_core_news_lg")
        _SPACY_DISPONIBLE = True
        print("spaCy es_core_news_lg cargado correctamente")
        return True
    except OSError:
        print("Modelo es_core_news_lg no encontrado.")
        print("Instalar con: python -m spacy download es_core_news_lg")
        return False
    except ImportError:
        print("spaCy no instalado. Usando solo parser heurístico.")
        print("Instalar con: pip install spacy && python -m spacy download es_core_news_lg")
        return False


def spacy_disponible():
    return _SPACY_DISPONIBLE


# ---------------------------------------------------------------------------
# EXTRACCIÓN DE ENTIDADES
# ---------------------------------------------------------------------------

def extraer_entidades(texto):
    """Extrae entidades nombradas del texto usando spaCy. """

    if not _SPACY_DISPONIBLE or not _nlp:
        return {}

    doc = _nlp(texto[:100_000])  # límite de seguridad

    resultado = {}
    for ent in doc.ents:
        tipo = ent.label_
        if tipo not in resultado:
            resultado[tipo] = []
        texto_ent = ent.text.strip()
        if texto_ent and texto_ent not in resultado[tipo]:
            resultado[tipo].append(texto_ent)

    return resultado


# ---------------------------------------------------------------------------
# DETECCIÓN DE EMPRESA EN LÍNEA
# ---------------------------------------------------------------------------

def es_organizacion_spacy(linea):
    """Retorna True si spaCy identifica la línea como una organización (ORG).
    Útil para detectar empresas sin sufijo SAS/LTDA."""
    
    if not _SPACY_DISPONIBLE or not _nlp:
        return None  # None = sin información, diferente a False

    linea_clean = linea.strip()
    if len(linea_clean) < 3 or len(linea_clean) > 80:
        return False

    doc = _nlp(linea_clean)
    for ent in doc.ents:
        if ent.label_ == "ORG":
            # Verificar que la entidad cubre la mayor parte de la línea
            cobertura = len(ent.text) / len(linea_clean)
            if cobertura > 0.5:
                return True
    return False


def es_cargo_spacy(linea):
    """ Usa el POS tagger de spaCy para detectar si una línea es un título de cargo. Retorna True/False/None (None = sin información)."""
    if not _SPACY_DISPONIBLE or not _nlp:
        return None

    linea_clean = linea.strip()
    if len(linea_clean) < 3 or len(linea_clean) > 100:
        return None

    doc = _nlp(linea_clean)
    tokens = [t for t in doc if not t.is_space]

    if len(tokens) > 10:
        return False

    # Verbos en primera persona = oración, no cargo
    for token in tokens:
        if token.pos_ == "VERB" and token.morph.get("Person") == ["1"]:
            return False

    # Primer token nominal = probable cargo
    if tokens and tokens[0].pos_ in ("NOUN", "ADJ", "PROPN"):
        return True

    return None


# ---------------------------------------------------------------------------
# ENRIQUECIMIENTO DE TRABAJOS DETECTADOS
# ---------------------------------------------------------------------------

def enriquecer_trabajos_con_nlp(trabajos, texto_seccion):
    """Pasa por los trabajos ya detectados por el parser heurístico y usa spaCy para rellenar campos faltantes (empresa principalmente)."""
    
    if not _SPACY_DISPONIBLE or not trabajos:
        return trabajos

    # Extraer todas las organizaciones del texto de experiencia
    entidades = extraer_entidades(texto_seccion)
    orgs_encontradas = entidades.get("ORG", [])

    if not orgs_encontradas:
        return trabajos

    # Para cada trabajo sin empresa, buscar una ORG en el contexto cercano
    lineas = texto_seccion.split("\n")

    for trabajo in trabajos:
        if trabajo.get("empresa"):
            continue  # ya tiene empresa, no tocar

        cargo = trabajo.get("cargo", "")
        if not cargo:
            continue

        # Buscar el índice de la línea donde aparece el cargo
        idx_cargo = None
        for i, linea in enumerate(lineas):
            if cargo[:20] in linea:
                idx_cargo = i
                break

        if idx_cargo is None:
            continue

        # Buscar en las 3 líneas anteriores y posteriores al cargo
        ventana = lineas[max(0, idx_cargo - 3): idx_cargo + 3]
        for linea_ventana in ventana:
            linea_clean = linea_ventana.strip()
            if not linea_clean or linea_clean == cargo:
                continue
            if es_organizacion_spacy(linea_clean):
                trabajo["empresa"] = linea_clean
                break

        # Si aún no encontramos, buscar si alguna ORG global encaja
        if not trabajo.get("empresa") and orgs_encontradas:
            for org in orgs_encontradas:
                # Verificar que la org aparece cerca del cargo en el texto
                idx_org = texto_seccion.find(org)
                idx_c = texto_seccion.find(cargo[:20])
                if idx_org != -1 and idx_c != -1 and abs(idx_org - idx_c) < 300:
                    trabajo["empresa"] = org
                    break

    return trabajos


# ---------------------------------------------------------------------------
# DETECCIÓN DE EMPRESAS EN PATRÓN "empresa - cargo" EN UNA LÍNEA
# ---------------------------------------------------------------------------

def separar_empresa_cargo_guion(linea):
    """Detecta el patrón: "Honor y laurel - Analista de Procesos"""
    
    # Debe tener exactamente un separador " - " significativo
    partes = re.split(r"\s+[-–]\s+", linea, maxsplit=1)
    if len(partes) != 2:
        return None, None

    parte_izq, parte_der = partes[0].strip(), partes[1].strip()

    # Ambas partes deben ser razonablemente cortas
    if len(parte_izq) > 60 or len(parte_der) > 60:
        return None, None

    if _SPACY_DISPONIBLE:
        izq_es_org = es_organizacion_spacy(parte_izq)
        der_es_org = es_organizacion_spacy(parte_der)

        if izq_es_org and not der_es_org:
            return parte_izq, parte_der
        if der_es_org and not izq_es_org:
            return parte_der, parte_izq
        # Si spaCy no resuelve, heurística: izquierda=empresa, derecha=cargo
        return parte_izq, parte_der
    else:
        # Sin spaCy: izquierda siempre empresa (heurística)
        return parte_izq, parte_der
