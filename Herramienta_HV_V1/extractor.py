import pdfplumber
from docx import Document


def leer_pdf(path):

    texto = ""

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                texto += t + "\n"

    return texto


def leer_docx(path):

    doc = Document(path)

    return "\n".join(p.text for p in doc.paragraphs)


def extraer_texto(path):

    if path.endswith(".pdf"):
        return leer_pdf(path)

    if path.endswith(".docx"):
        return leer_docx(path)

    return ""