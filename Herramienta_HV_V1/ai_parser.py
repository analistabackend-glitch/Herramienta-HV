import time

from groq import Groq
import json
import re
from dotenv import load_dotenv
import os

# ─────────────────────────────────────────────────────────────
# Límite de caracteres para enviar a la IA.
# llama-3.1-8b-instant tiene límite de ~6000 TPM.
# ~4 chars ≈ 1 token → 5000 tokens ≈ 20000 chars (margen seguro).
# ─────────────────────────────────────────────────────────────
MAX_CHARS_CV = 18_000


def limpiar_json(texto):

    if not texto:
        return "{}"

    # eliminar bloques ```json
    texto = texto.replace("```json", "")
    texto = texto.replace("```", "")

    # encontrar el primer objeto JSON completo
    stack = []
    inicio = None

    for i, c in enumerate(texto):

        if c == "{":
            if inicio is None:
                inicio = i
            stack.append(c)

        elif c == "}":
            if stack:
                stack.pop()

            if not stack and inicio is not None:
                return texto[inicio:i+1]

    return "{}"


load_dotenv()
client = Groq(
   api_key = os.getenv("GROQ_API_KEY")
)


# ─────────────────────────────────────────────────────────────
# VALIDADOR: ¿es este texto una hoja de vida?
# Usa la IA con un prompt muy corto (≈ 80 tokens de respuesta)
# para decidir ANTES de hacer el parseo completo.
# ─────────────────────────────────────────────────────────────

# Señales textuales que permiten decidir sin llamar a la IA
_SEÑALES_HV = [
    "experiencia laboral", "experiencia profesional", "formación académica",
    "educación", "habilidades", "perfil profesional", "objetivo profesional",
    "datos personales", "referencias", "logros", "cargo", "empresa",
    "curriculum", "hoja de vida", "cv ", "c.v.", "fecha de nacimiento",
    "lugar de nacimiento", "estado civil",
]

_SEÑALES_NO_HV = [
    "número de radicado", "factura", "contrato", "acta de", "resolución",
    "certificado de", "poder notarial", "demanda", "juzgado", "cotización",
    "orden de compra", "remisión", "póliza", "soat", "escritura",
    "número de caso", "ticket", "correo electrónico:", "asunto:",
    "estimado", "cordialmente,", "adjunto", "anexo",
]

def _decision_rapida(texto: str) -> str | None:
    """
    Retorna 'hv' o 'no_hv' si puede decidir por palabras clave,
    o None si no puede decidir y hay que preguntarle a la IA.
    """
    t = texto.lower()
    señales_hv    = sum(1 for s in _SEÑALES_HV    if s in t)
    señales_no_hv = sum(1 for s in _SEÑALES_NO_HV if s in t)

    if señales_hv >= 3:
        return "hv"
    if señales_no_hv >= 2 and señales_hv == 0:
        return "no_hv"
    return None   # indeciso → preguntar a la IA


def es_hoja_de_vida(texto: str) -> tuple[bool, str]:
    """
    Determina si el texto corresponde a una hoja de vida.
    Retorna (es_hv: bool, motivo: str).
    Primero intenta decidir por palabras clave (gratis).
    Solo si es ambiguo, consulta a la IA con un prompt mínimo.
    """
    # 1. Decisión rápida sin IA
    decision = _decision_rapida(texto)
    if decision == "hv":
        return True, "Señales de HV detectadas en el documento."
    if decision == "no_hv":
        return False, "El documento no contiene señales de hoja de vida (posible correo, factura, contrato u otro)."

    # 2. Consulta a la IA con prompt ultra-corto (≈ 200 tokens totales)
    muestra = texto[:2000]   # solo los primeros 2000 chars para esta validación
    prompt_validacion = f"""Analiza el siguiente fragmento de documento y determina si es una hoja de vida / currículum vitae de una persona.

Responde ÚNICAMENTE con este JSON (sin texto adicional):
{{"es_hoja_de_vida": true_o_false, "motivo": "una frase breve"}}

Fragmento:
{muestra}"""

    try:
        time.sleep(2)   # delay entre consultas a la IA
        r = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt_validacion}],
            temperature=0,
            max_tokens=80,
        )
        contenido = limpiar_json(r.choices[0].message.content)
        data = json.loads(contenido)
        es_hv  = bool(data.get("es_hoja_de_vida", False))
        motivo = data.get("motivo", "")
        return es_hv, motivo
    except Exception as e:
        # Si falla la validación, asumir que sí es HV para no perder candidatos reales
        return True, f"No se pudo validar (se asume HV): {e}"


def parsear_cv(texto):

    # Truncar texto muy largo para no exceder el límite de tokens del modelo
    if len(texto) > MAX_CHARS_CV:
        print(f"  ⚠️  Texto truncado de {len(texto):,} a {MAX_CHARS_CV:,} caracteres para evitar error 413.")
        texto = texto[:MAX_CHARS_CV]

    prompt = f"""
Extrae la información del CV y devuélvela en JSON.

Formato exacto:

{{
  "tipo_formato": "libre",
  "contacto": {{
    "nombre":"",
    "email":"",
    "telefono":"",
    "direccion":""
  }},
  "perfil_resumen":"",
  "experiencia":[
    {{
      "empresa":"",
      "cargo":"",
      "fecha_inicio":"",
      "fecha_fin":"",
      "responsabilidades":[]
    }}
  ],
  "educacion":[],
  "habilidades":[],
  "cursos":[]
}}

CV:

{texto}
"""

    time.sleep(2)   # delay entre consultas a la IA
    r = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role":"user","content":prompt}],
        temperature=0
    )

    contenido = r.choices[0].message.content

    contenido = limpiar_json(contenido)

    try:
        data = json.loads(contenido)
    except Exception as e:
        print("⚠️ Error leyendo JSON del modelo")
        print(contenido)
        data = {}

    return data
