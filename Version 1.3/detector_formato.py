def detectar_formato(texto):

    texto = texto.lower()

    claves_funcion_publica = [
        "formato único",
        "hoja de vida persona natural",
        "leyes 190 de 1995",
        "funcionpublica.gov.co",
        "entidad receptora"
    ]

    for clave in claves_funcion_publica:
        if clave in texto:
            return "funcion_publica"

    return "libre"