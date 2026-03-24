# =========================
# CONFIG COSTOS GPT-4o-mini
# =========================
PRECIO_INPUT = 0.00015
PRECIO_OUTPUT = 0.0006

total_input_tokens = 0
total_output_tokens = 0


def reset():
    global total_input_tokens, total_output_tokens
    total_input_tokens = 0
    total_output_tokens = 0


def registrar(origen, usage):
    global total_input_tokens, total_output_tokens

    if not usage:
        return

    total_input_tokens += usage.prompt_tokens
    total_output_tokens += usage.completion_tokens


def calcular_costo():
    costo_input = (total_input_tokens / 1000) * PRECIO_INPUT
    costo_output = (total_output_tokens / 1000) * PRECIO_OUTPUT

    return {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "costo_input_usd": costo_input,
        "costo_output_usd": costo_output,
        "costo_total_usd": costo_input + costo_output
    }


def reporte(log=None):
    data = calcular_costo()

    lineas = [
        "\n💰 COSTO IA",
        f"   Tokens input : {data['input_tokens']}",
        f"   Tokens output: {data['output_tokens']}",
        f"   Costo input  : ${data['costo_input_usd']:.6f}",
        f"   Costo output : ${data['costo_output_usd']:.6f}",
        f"   TOTAL USD    : ${data['costo_total_usd']:.6f}",
    ]

    for linea in lineas:
        if log:
            log(linea)
        else:
            print(linea)