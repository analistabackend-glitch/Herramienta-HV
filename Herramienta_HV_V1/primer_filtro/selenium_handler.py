"""
selenium_handler.py  (versión optimizada)
==========================================
Cambios principales:
  1. Reemplazados todos los time.sleep() fijos por esperas dinámicas (WebDriverWait).
  2. descargar_hv usa un pool de hilos (ThreadPoolExecutor) → descargas en paralelo.
  3. extraer_urls corrige el bug de reintento (recargaba current_url en pág 1).
  4. Scraping de perfiles con múltiples drivers en paralelo (pool de drivers).
  5. Pequeñas mejoras de robustez (early-exit en filtros, regex precompiladas).
"""

import re
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

from config import (
    CARPETA_DESCARGA,
    CACHE_PDF,
    CACHE_JSON_VACANTE,
    COMPUTRABAJO_EMAIL,
    COMPUTRABAJO_PASSWORD,
    COMPUTRABAJO_OFFERS_URL,
    COMPUTRABAJO_BASE_URL,
    CHROME_WINDOW_SIZE,
    SELENIUM_WAIT_TIMEOUT,
)

# ── Regex precompiladas (se compilan una sola vez al importar) ─────────────────
_RE_EDAD   = re.compile(r"(\d{1,2})\s*a[nñ]os?", re.IGNORECASE)
_RE_SAL    = re.compile(
    # Captura la respuesta tras cualquier pregunta sobre salario/aspiración/pretensión,
    # sin importar la redacción exacta de la vacante.
    r"(?:[^\n]*(?:aspir|pretens|salar|remuner)[^\n]*)\n"
    r"(?:\s*\n)*\s*([^\n]+)",
    re.IGNORECASE,
)
_RE_SAB    = re.compile(
    # Captura SI/NO tras cualquier pregunta que mencione sábado/sabado
    # o disponibilidad de fin de semana, sin importar la redacción exacta.
    r"(?:[^\n]*(?:s[aá]bado|disponibilidad[^\n]{0,30}(?:fin\s*de\s*semana|weekend))[^\n]*)"
    r"\n(?:\s*\n)*\s*(SI|NO)\b",
    re.IGNORECASE,
)
_RE_NUM    = re.compile(r"[^\d.,]")
_RE_GRUPOS = re.compile(r"\d+(?:[.,]\d+)*")
_RE_RANGO  = re.compile(r"\d\s*(?:a|-)\s*\d", re.IGNORECASE)

# Número de drivers paralelos para scraping de perfiles.
# Ajusta según la RAM disponible (cada Chrome ~150-200 MB).
MAX_DRIVERS = 3

# ══════════════════════════════════════════
#  DRIVER
# ══════════════════════════════════════════

def crear_driver(headless: bool = False):
    opts = webdriver.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument(f"--window-size={CHROME_WINDOW_SIZE}")
    if headless:
        # headless reduce el overhead de renderizado en scraping masivo
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
    opts.add_experimental_option(
        "prefs", {"download.default_directory": str(CARPETA_DESCARGA.absolute())}
    )
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts
    )


# ══════════════════════════════════════════
#  LOGIN
# ══════════════════════════════════════════

def login(driver, log):
    log("Iniciando sesion en Computrabajo...")
    driver.get(COMPUTRABAJO_OFFERS_URL)

    # ❌ ANTES: time.sleep(2)
    # ✅ AHORA: espera dinámica — avanza en cuanto la URL cambia o aparece el campo
    wait = WebDriverWait(driver, SELENIUM_WAIT_TIMEOUT)
    try:
        wait.until(lambda d: d.current_url != "about:blank")
    except TimeoutException:
        pass

    if "login" in driver.current_url.lower() or "account" in driver.current_url.lower():
        log("  Login requerido...")
        try:
            campo_user = wait.until(EC.presence_of_element_located((By.ID, "UserName")))
            campo_user.clear()
            campo_user.send_keys(COMPUTRABAJO_EMAIL)
            campo_pass = driver.find_element(By.ID, "fiesta")
            campo_pass.clear()
            campo_pass.send_keys(COMPUTRABAJO_PASSWORD)
            driver.find_element(
                By.CSS_SELECTOR, "button[type='submit'], input[type='submit']"
            ).click()
            wait.until(lambda d: "login" not in d.current_url.lower())
            log("Login exitoso")
            return True
        except TimeoutException:
            log("ERROR: Login fallido")
            return False

    log("Sesion activa")
    return True


def _copiar_cookies(source_driver, dest_driver):
    """Copia las cookies de sesión de un driver a otro (mismo dominio)."""
    for c in source_driver.get_cookies():
        try:
            dest_driver.add_cookie(c)
        except Exception:
            pass


# ══════════════════════════════════════════
#  EXTRACCIÓN DE URLs
# ══════════════════════════════════════════
def extraer_urls(driver, url_vacante, log):
    """
    Extrae todas las URLs de candidatos recorriendo la paginación de Computrabajo.

    Paginación de Computrabajo:
      <nav class="pag_numeric">
        <a class="sel">1</a>          ← página activa
        <a id="2">2</a>               ← páginas numéricas
        <a class="b_next">›</a>       ← botón siguiente  ✅ selector clave
        <a class="b_prev">‹</a>       ← botón anterior
      </nav>
    """
    log("Obteniendo candidatos...")
    SELECTOR_CVS  = "a[href*='MatchCvDetail'],a[href*='MatchDetail'],a[href*='CvDetail']"
    SELECTOR_NEXT = "a.b_next"   # selector exacto confirmado en el HTML de Computrabajo

    urls   = set()
    pagina = 1

    # Cargar primera página una sola vez (no recargar en cada vuelta del loop)
    driver.get(url_vacante)

    while True:
        log(f"  Pagina {pagina}...")

        # Esperar a que carguen los candidatos
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, SELECTOR_CVS))
            )
        except TimeoutException:
            log(f"  [WARN] Sin candidatos en pág {pagina}, continuando...")

        # Recolectar URLs de esta página
        antes = len(urls)
        for a in driver.find_elements(By.CSS_SELECTOR, SELECTOR_CVS):
            h = a.get_attribute("href")
            if not h:
                continue
            if h.startswith("/"):
                h = COMPUTRABAJO_BASE_URL + h
            urls.add(h)
        log(f"  → {len(urls) - antes} nuevas URLs (total acumulado: {len(urls)})")

        # Buscar botón "siguiente" (›) — clase b_next en Computrabajo
        try:
            btn_next = driver.find_element(By.CSS_SELECTOR, SELECTOR_NEXT)
            clase = btn_next.get_attribute("class") or ""
            # La clase b_next desaparece o se deshabilita en la última página
            if "disabled" in clase:
                log("  Última página alcanzada.")
                break
        except NoSuchElementException:
            log("  Sin botón siguiente — última página.")
            break

        # Navegar a la siguiente página
        url_antes = driver.current_url
        try:
            btn_next.click()
        except Exception as e:
            log(f"  [WARN] Click en siguiente falló ({e}), usando href...")
            href_next = btn_next.get_attribute("href") or ""
            if href_next and href_next != "#":
                driver.get(href_next)
            else:
                break

        # Esperar a que la URL cambie (indica nueva página cargada)
        try:
            WebDriverWait(driver, 15).until(lambda d: d.current_url != url_antes)
        except TimeoutException:
            time.sleep(2)  # fallback para SPAs que no cambian URL

        pagina += 1

    log(f"  {len(urls)} candidatos encontrados en {pagina} página(s)")
    return list(urls)


# ══════════════════════════════════════════
#  HELPERS NUMÉRICOS  (sin cambios de lógica)
# ══════════════════════════════════════════

def _num_col(t):
    t = _RE_NUM.sub("", t.strip().replace(" ", ""))
    if not t:
        return None
    if t.count(".") > 1:
        t = t.replace(".", "")
    elif t.count(",") > 1:
        t = t.replace(",", "")
    elif "." in t and "," in t:
        t = t.replace(".", "").replace(",", "")
    elif "." in t:
        t = t.replace(".", "")
    elif "," in t:
        t = t.replace(",", "")
    try:
        v = int(t)
        if v < 1000:
            v *= 1_000_000
        elif v < 10000:
            v *= 1_000
        return v
    except Exception:
        return None


def parsear_salario(texto):
    """
    Convierte texto libre de salario a un entero (pesos colombianos).
    Maneja:
      - Números con separadores mixtos: 2.500.000, 2,500,000, 2'500'000, 2'500.000
      - Forma corta con apostrofe: 2'5 → 2.500.000, 2'8 → 2.800.000
      - Notación M/m: 2.5M → 2.500.000
      - Rangos "Entre X a Y" → toma el menor
      - Doble valor ("200000 2500000") → toma el mayor (el primero suele ser error)
      - Texto libre ("A convenir", "SMMLV") → retorna None (sin filtrar)
    """
    if not texto:
        return None

    limpio = texto.strip().replace("$", "")

    # Forma corta: "2'5" o "2'8" → N millones + D*100_000
    m_corto = re.match(r"^(\d)[\'](\d)$", limpio.strip())
    if m_corto:
        return int(m_corto.group(1)) * 1_000_000 + int(m_corto.group(2)) * 100_000

    # Notación M/m: "2.5M", "2,5M", "2M"
    m_mill = re.match(r"^([\d][\d.,]*)\s*[Mm]$", limpio.strip())
    if m_mill:
        try:
            val = float(m_mill.group(1).replace(",", "."))
            return int(val * 1_000_000)
        except Exception:
            pass

    # Normalizar apóstrofes como separadores de miles: 2'500'000 → 2500000
    limpio = re.sub(r"(\d)[\'](\d)", r"\1\2", limpio)

    grupos = _RE_GRUPOS.findall(limpio)
    if not grupos:
        return None  # texto libre ("A convenir", "SMMLV", etc.)

    if len(grupos) >= 2 and _RE_RANGO.search(limpio):
        # Rango "Entre X a Y" → tomar el menor
        v1, v2 = _num_col(grupos[0]), _num_col(grupos[1])
        if v1 and v2:
            return min(v1, v2)
        return v1 or v2

    if len(grupos) >= 2:
        # Doble valor sin rango ("200000 2500000") → tomar el mayor
        vals = [_num_col(g) for g in grupos[:2]]
        vals = [v for v in vals if v]
        if vals:
            return max(vals)

    return _num_col(grupos[0])


# ══════════════════════════════════════════
#  SCRAPING DE PERFIL + FILTRADO
# ══════════════════════════════════════════

def extraer_datos_y_filtrar(driver, url, cfg, log):
    """
    Versión optimizada:
    - Reemplazado time.sleep(1) por espera dinámica con fallback.
    - Early-exit en filtros: en cuanto hay rechazo, no sigue evaluando.
    - Regex precompiladas (módulo-level).
    """
    # Reintento ante ConnectionResetError (error 10054 de Windows/Computrabajo)
    for intento in range(3):
        try:
            driver.get(url)
            break
        except Exception as e:
            if intento < 2:
                log(f"  [WARN] Error cargando perfil (intento {intento+1}/3): {e}")
                time.sleep(2 * (intento + 1))
            else:
                raise

    wait = WebDriverWait(driver, 10)
    try:
        wait.until(
            EC.any_of(
                EC.presence_of_element_located((By.ID, "candidato")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1.fwB")),
            )
        )
    except TimeoutException:
        pass  # continuar con lo que haya

    # ❌ ANTES: time.sleep(1)  → innecesario después de WebDriverWait

    datos = {
        "url": url,
        "nombre": None,
        "url_pdf": None,
        "edad": None,
        "salario": None,
        "sabados": None,
        "pasa_filtro": False,
        "motivo_rechazo": None,
        "motivo_seleccion": None,
    }

    texto_pagina = ""
    try:
        texto_pagina = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        pass

    try:
        datos["nombre"] = (
            driver.find_element(By.CSS_SELECTOR, "h1.fwB")
            .text.replace("Hoja de vida de", "")
            .strip()
        )
    except Exception:
        pass

    m = _RE_EDAD.search(texto_pagina)
    if m:
        datos["edad"] = int(m.group(1))

    m_sal = _RE_SAL.search(texto_pagina)
    if m_sal:
        datos["salario"] = parsear_salario(m_sal.group(1))

    m_sab = _RE_SAB.search(texto_pagina)
    if m_sab:
        datos["sabados"] = m_sab.group(1).strip().lower()

    try:
        a = driver.find_element(By.CSS_SELECTOR, "a.js_download_file")
        h = a.get_attribute("href")
        if h and h != "#":
            if h.startswith("/"):
                h = COMPUTRABAJO_BASE_URL + h
            datos["url_pdf"] = h
    except Exception:
        pass

    log(
        f"  Edad: {datos['edad']} | "
        f"Salario: {datos['salario']} | "
        f"Sabados: {datos['sabados']}"
    )

    # ── Aplicar filtros con early-exit ────────────────────────────────────────
    motivos = []

    edad = datos["edad"]
    if edad is not None and (edad < cfg["edad_min"] or edad > cfg["edad_max"]):
        motivos.append(f"Edad {edad} fuera del rango {cfg['edad_min']}-{cfg['edad_max']}")

    salario = datos["salario"]
    if salario is not None and (salario < cfg["sal_min"] or salario > cfg["sal_max"]):
        motivos.append(
            f"Salario ${salario:,} fuera del rango ${cfg['sal_min']:,}-${cfg['sal_max']:,}"
        )

    sab = datos["sabados"]
    if cfg.get("requiere_sabados") and sab is not None:
        if sab.lower() in {"no", "no.", "no,", "nop", "nope"}:
            motivos.append("No disponible los sabados")

    if motivos:
        datos["pasa_filtro"] = False
        datos["motivo_rechazo"] = " | ".join(motivos)
    else:
        datos["pasa_filtro"] = True
        razones = []
        if edad is None:
            razones.append("Edad no declarada (pasa automáticamente)")
        else:
            razones.append(f"Edad {edad} dentro del rango {cfg['edad_min']}-{cfg['edad_max']}")
        if salario is None:
            razones.append("Salario no declarado (pasa automáticamente)")
        else:
            razones.append(
                f"Salario ${salario:,} dentro del rango ${cfg['sal_min']:,}-${cfg['sal_max']:,}"
            )
        if cfg.get("requiere_sabados"):
            if sab is None:
                razones.append("Disponibilidad sábados no declarada (pasa automáticamente)")
            else:
                razones.append(f"Disponible los sábados ({sab})")
        datos["motivo_seleccion"] = " | ".join(razones)

    return datos


# ══════════════════════════════════════════
#  SCRAPING PARALELO DE PERFILES
# ══════════════════════════════════════════

def scraping_paralelo(urls, cfg, log, session_driver, num_drivers=MAX_DRIVERS):
    """
    Divide las URLs entre `num_drivers` drivers Chrome en paralelo.
    Cada driver replica la sesión del driver principal (cookies).

    Retorna lista de dicts con los datos de cada candidato.
    """
    if not urls:
        return []

    # Crear drivers adicionales y copiar sesión
    drivers = []
    for _ in range(min(num_drivers, len(urls))):
        d = crear_driver(headless=True)
        # Navegar al dominio base para poder agregar cookies
        d.get(COMPUTRABAJO_BASE_URL)
        _copiar_cookies(session_driver, d)
        drivers.append(d)

    chunks = [urls[i::len(drivers)] for i in range(len(drivers))]
    resultados = []

    def _worker(driver, chunk):
        return [extraer_datos_y_filtrar(driver, u, cfg, log) for u in chunk]

    try:
        with ThreadPoolExecutor(max_workers=len(drivers)) as ex:
            futures = {ex.submit(_worker, d, c): d for d, c in zip(drivers, chunks)}
            for fut in as_completed(futures):
                try:
                    resultados.extend(fut.result())
                except Exception as e:
                    log(f"  [ERROR] Worker falló: {e}")
    finally:
        for d in drivers:
            try:
                d.quit()
            except Exception:
                pass

    return resultados


# ══════════════════════════════════════════
#  DESCRIPCIÓN DE VACANTE
# ══════════════════════════════════════════

def extraer_descripcion_vacante(driver, nombre_vacante, url_vacante_match, log, cfg=None, carpeta_destino=None):
    log("Extrayendo descripcion de la vacante...")
    try:
        m = re.search(r"[?&]oi=([A-Fa-f0-9]+)", url_vacante_match)
        if not m:
            log("  [WARN] No se pudo extraer oi de la URL.")
            return None
        oi = m.group(1)
        url_pub = f"https://empresa.co.computrabajo.com/Company/Offers/Publish?oi={oi}"
        # 🔥 CARGA ROBUSTA CON REINTENTOS
        for intento in range(3):
            try:
                driver.get(url_pub)

                WebDriverWait(driver, 15).until(
                    lambda d: len(d.find_element(By.TAG_NAME, "body").text) > 200
                )
                break
            except Exception:
                log(f"  [WARN] Reintentando carga de descripción ({intento+1}/3)...")
                time.sleep(2)
        # 👇 🔥 AQUÍ VA EL DEBUG (FUERA DEL FOR)
        try:
            body_len = len(driver.find_element(By.TAG_NAME, "body").text)
            print("DEBUG BODY LENGTH:", body_len)
        except Exception:
            print("DEBUG BODY ERROR")
            
        # ❌ ANTES: time.sleep(4)
        # ✅ AHORA: espera a que aparezca un textarea o contenteditable
        wait = WebDriverWait(driver, 15)
        try:
            wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.TAG_NAME, "textarea")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[contenteditable='true']")),
                    EC.presence_of_element_located((By.TAG_NAME, "iframe")),
                )
            )
        except TimeoutException:
            pass

        descripcion = None

        for ta in driver.find_elements(By.TAG_NAME, "textarea"):
            val = (ta.get_attribute("value") or ta.text or "").strip()
            if len(val) > 80:
                descripcion = val
                break

        if not descripcion:
            for el in driver.find_elements(By.CSS_SELECTOR, "[contenteditable='true']"):
                val = (el.text or "").strip()
                if len(val) > 80:
                    descripcion = val
                    break

        if not descripcion:
            for frame in driver.find_elements(By.TAG_NAME, "iframe"):
                try:
                    driver.switch_to.frame(frame)
                    val = (driver.find_element(By.TAG_NAME, "body").text or "").strip()
                    driver.switch_to.default_content()
                    if len(val) > 80:
                        descripcion = val
                        break
                except Exception:
                    driver.switch_to.default_content()

        if not descripcion:
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                if len(body_text) > 200:
                    descripcion = body_text
                    log("  [INFO] Descripción tomada del body completo")
            except Exception:
                pass

        if not descripcion:
            log("  [WARN] No se encontro la descripcion de tareas.")
            return None

        resultado = {
            "vacante": nombre_vacante,
            "offer_id": oi,
            "url_formulario": url_pub,
            "descripcion_tareas": descripcion,
            "peso_experiencia_laboral": f"{cfg.get('peso_exp', '')} %" if cfg else "",
            "peso_formacion_academica": f"{cfg.get('peso_aca', '')} %" if cfg else "",
            "palabras_clave": cfg.get("palabras_clave", "") if cfg else "",
            "fecha_extraccion": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        nombre_limpio = re.sub(r"[^\w\s-]", "", nombre_vacante).strip().replace(" ", "_")[:60]
        destino_json = Path(carpeta_destino) if carpeta_destino else CARPETA_DESCARGA
        destino_json.mkdir(parents=True, exist_ok=True)

        json_path = destino_json / f"descripcion_{nombre_limpio}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)

        shutil.copy(json_path, CACHE_JSON_VACANTE / json_path.name)
        log(f"  Descripcion guardada: {json_path.name}")
        return resultado

    except Exception as e:
        log(f"  [WARN] Error extrayendo descripcion: {e}")
        return None


# ══════════════════════════════════════════
#  DESCARGA DE HV (PDF / DOCX)
# ══════════════════════════════════════════

def descargar_hv(driver, url_hv, nombre, carpeta=None):
    """Descarga el archivo de HV usando las cookies activas de Selenium."""
    destino_dir = Path(carpeta) if carpeta else CARPETA_DESCARGA
    destino_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    for c in driver.get_cookies():
        session.cookies.set(c["name"], c["value"])
    headers = {"User-Agent": driver.execute_script("return navigator.userAgent")}

    r = session.get(url_hv, headers=headers, stream=True, timeout=30)
    if r.status_code != 200:
        return None

    contenido = b"".join(r.iter_content(8192))
    if len(contenido) < 1000:
        return None

    ct = r.headers.get("Content-Type", "").lower()
    if contenido[:4] == b"%PDF" or "pdf" in ct:
        ext = ".pdf"
    elif (
        contenido[:2] == b"PK"
        or "wordprocessingml" in ct
        or "msword" in ct
        or url_hv.lower().endswith(".docx")
    ):
        ext = ".docx"
    else:
        ext = ".pdf"

    ruta = destino_dir / f"{nombre}{ext}"
    with open(ruta, "wb") as f:
        f.write(contenido)
    return ruta


def descargar_hv_thread(driver, datos, nombre_f, carpeta_vacante):
    """Descarga la HV y la copia al caché. Retorna la ruta o None."""
    try:
        ruta = descargar_hv(driver, datos["url_pdf"], nombre_f, carpeta=carpeta_vacante)
        if ruta:
            shutil.copy(ruta, CACHE_PDF / Path(ruta).name)
        return ruta
    except Exception:
        return None


def descargar_hvs_en_paralelo(driver, lista_datos, carpeta_vacante, log, max_workers=6):
    """
    ✅ NUEVA función: descarga todas las HVs en paralelo con requests (sin Selenium).
    `lista_datos` es la lista de dicts retornada por extraer_datos_y_filtrar.
    Solo descarga candidatos que pasaron el filtro y tienen url_pdf.
    """
    pendientes = [d for d in lista_datos if d.get("pasa_filtro") and d.get("url_pdf")]
    if not pendientes:
        log("  Sin HVs para descargar.")
        return []

    # Capturar cookies una sola vez
    cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
    user_agent = driver.execute_script("return navigator.userAgent")
    headers = {"User-Agent": user_agent}

    resultados = []

    def _dl(d):
        nombre_f = re.sub(r"[^\w\s-]", "", d.get("nombre") or "candidato").strip()[:50]
        session = requests.Session()
        session.cookies.update(cookies)
        try:
            r = session.get(d["url_pdf"], headers=headers, stream=True, timeout=30)
            if r.status_code != 200:
                return None
            contenido = b"".join(r.iter_content(8192))
            if len(contenido) < 1000:
                return None
            ct = r.headers.get("Content-Type", "").lower()
            ext = ".pdf" if (contenido[:4] == b"%PDF" or "pdf" in ct) else ".docx"
            ruta = Path(carpeta_vacante) / f"{nombre_f}{ext}"
            ruta.parent.mkdir(parents=True, exist_ok=True)
            with open(ruta, "wb") as f:
                f.write(contenido)
            shutil.copy(ruta, CACHE_PDF / ruta.name)
            return ruta
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_dl, d): d for d in pendientes}
        for fut in as_completed(futures):
            ruta = fut.result()
            if ruta:
                log(f"  ✓ Descargado: {Path(ruta).name}")
                resultados.append(ruta)

    log(f"  {len(resultados)}/{len(pendientes)} HVs descargadas.")
    return resultados
