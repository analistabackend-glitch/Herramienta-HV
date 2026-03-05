from groq import Groq
import json
import re
import json
from dotenv import load_dotenv
import os

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


def parsear_cv(texto):

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