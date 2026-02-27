import pdfplumber


def extraer_texto_pdf(ruta_pdf):
    """Extrae texto de un PDF manejando layouts de dos columnas."""
    texto_completo = ""

    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            for pagina in pdf.pages:
                ancho_pagina = pagina.width
                mitad = ancho_pagina / 2

                # Extraer palabras con sus coordenadas
                palabras = pagina.extract_words()

                if not palabras:
                    continue

                # Detectar el umbral de columna automáticamente:
                # buscamos el "gap" más grande entre valores de x0
                xs = sorted(set(round(p["x0"]) for p in palabras))
                umbral = _detectar_umbral_columnas(xs, ancho_pagina)

                # Separar columna izquierda y derecha
                col_izq = [p for p in palabras if p["x0"] < umbral]
                col_der = [p for p in palabras if p["x0"] >= umbral]

                # Reconstruir texto por columna, agrupando líneas por coordenada Y
                texto_izq = _palabras_a_texto(col_izq)
                texto_der = _palabras_a_texto(col_der)

                # Columna derecha primero (generalmente el contenido principal)
                # luego izquierda (datos de contacto, educación, cursos)
                texto_pagina = texto_der + "\n" + texto_izq
                texto_completo += texto_pagina + "\n"

    except Exception as e:
        print(f"Error al procesar el archivo {ruta_pdf}: {e}")

    return texto_completo


def _detectar_umbral_columnas(xs, ancho_pagina):
    """
    Detecta el punto de separación entre columnas buscando el gap más grande
    en la distribución de coordenadas X, en el tercio central de la página.
    """
    if not xs:
        return ancho_pagina / 2

    tercio_izq = ancho_pagina * 0.25
    tercio_der = ancho_pagina * 0.75
    xs_centro = [x for x in xs if tercio_izq < x < tercio_der]

    if len(xs_centro) < 2:
        return ancho_pagina / 2

    # Buscar el gap más largo entre xs consecutivos en el centro
    max_gap = 0
    umbral = ancho_pagina / 2
    for i in range(1, len(xs_centro)):
        gap = xs_centro[i] - xs_centro[i - 1]
        if gap > max_gap:
            max_gap = gap
            umbral = (xs_centro[i] + xs_centro[i - 1]) / 2

    return umbral


def _palabras_a_texto(palabras, tolerancia_y=3):
    """
    Agrupa palabras por línea (coordenada Y similar) y las une en texto.
    tolerancia_y: diferencia máxima en px para considerar que están en la misma línea.
    """
    if not palabras:
        return ""

    # Ordenar por Y (arriba→abajo), luego por X (izquierda→derecha)
    palabras_sorted = sorted(palabras, key=lambda w: (round(w["top"] / tolerancia_y), w["x0"]))

    lineas = []
    linea_actual = []
    y_actual = None

    for palabra in palabras_sorted:
        y = round(palabra["top"] / tolerancia_y)
        if y_actual is None or y == y_actual:
            linea_actual.append(palabra["text"])
            y_actual = y
        else:
            lineas.append(" ".join(linea_actual))
            linea_actual = [palabra["text"]]
            y_actual = y

    if linea_actual:
        lineas.append(" ".join(linea_actual))

    return "\n".join(lineas)
