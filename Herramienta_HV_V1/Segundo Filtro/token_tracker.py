# token_tracker.py
# Contador global de tokens — importar en ai_parser.py y tercer_filtro.py

_uso = {
    "ai_parser":      {"prompt": 0, "completion": 0},
    "tercer_filtro":  {"prompt": 0, "completion": 0},
}

def registrar(modulo: str, usage):
    """Recibe el objeto response.usage de OpenAI y acumula."""
    if usage is None:
        return
    _uso[modulo]["prompt"]     += usage.prompt_tokens
    _uso[modulo]["completion"] += usage.completion_tokens

def reporte():
    """Imprime resumen de tokens y costo estimado."""
    # Precios gpt-4o-mini (marzo 2026, por 1M tokens)
    PRECIO_INPUT  = 0.150 / 1_000_000   # $0.150 por 1M tokens de entrada
    PRECIO_OUTPUT = 0.600 / 1_000_000   # $0.600 por 1M tokens de salida

    print("\n" + "═"*55)
    print("  RESUMEN DE TOKENS USADOS")
    print("═"*55)

    total_prompt = total_completion = 0

    for modulo, datos in _uso.items():
        p = datos["prompt"]
        c = datos["completion"]
        costo = p * PRECIO_INPUT + c * PRECIO_OUTPUT
        print(f"  {modulo:<20} entrada: {p:>7,}  salida: {c:>6,}  ~${costo:.4f}")
        total_prompt     += p
        total_completion += c

    costo_total = total_prompt * PRECIO_INPUT + total_completion * PRECIO_OUTPUT
    print("─"*55)
    print(f"  {'TOTAL':<20} entrada: {total_prompt:>7,}  salida: {total_completion:>6,}  ~${costo_total:.4f}")
    print("═"*55 + "\n")

def reset():
    """Reinicia contadores (llamar al inicio de cada ejecución)."""
    for m in _uso:
        _uso[m]["prompt"] = 0
        _uso[m]["completion"] = 0