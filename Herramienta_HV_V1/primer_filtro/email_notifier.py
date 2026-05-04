"""
email_notifier.py
=================
Envío de correos de notificación para la herramienta de filtrado de CVs.

Configuración:
  - Cambia los valores de EMAIL_CONFIG según tu cuenta.
  - Para la contraseña, se recomienda usar variable de entorno:
        export EMAIL_PASSWORD="ssrz ldin nvyx ixry"
    Si no hay variable de entorno, se usa el valor hardcodeado como fallback.
"""

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


# =================== CONFIGURACIÓN DE EMAIL ===================
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_port_ssl": 465,
    "sender_email": "data_science@fertrac.com",
    "sender_password": os.getenv("EMAIL_PASSWORD", ""),  # ← Contraseña de aplicación de Google
    "recipient_emails": [
        "analista_automatizacion@fertrac.com",
        "data_science@fertrac.com",
   
        
    ],
    "enabled": True  # Cambiar a False para desactivar correos
}

# =================== HELPER INTERNO ===================

def _enviar(subject: str, body_html: str, log=print) -> bool:
    """
    Envía un correo HTML. Retorna True si se envió, False si falló.
    Centraliza toda la lógica SMTP para no duplicar código.
    """
    if not EMAIL_CONFIG.get("enabled", False):
        log("📧 Notificaciones por correo desactivadas (enabled=False)")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = EMAIL_CONFIG["sender_email"]
        msg["To"]      = ", ".join(EMAIL_CONFIG["recipient_emails"])
        msg["Subject"] = subject
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP_SSL(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port_ssl"]) as server:
            server.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
            server.send_message(msg)

        log("📧 Correo enviado correctamente")
        return True

    except smtplib.SMTPAuthenticationError:
        log("❌ Error de autenticación SMTP — verifica la contraseña de aplicación")
        return False
    except smtplib.SMTPException as e:
        log(f"❌ Error SMTP al enviar correo: {e}")
        return False
    except Exception as e:
        log(f"❌ Error inesperado al enviar correo: {e}")
        return False


# =================== CORREO DE ÉXITO ===================

def enviar_correo_exito(vacante: str, costo: dict, log=print, desde_cache: bool = False, modo_cache: str = None):
    """
    Notifica una ejecución completada sin errores.

    Args:
        vacante      : Nombre de la vacante procesada.
        costo        : Dict con claves input_tokens, output_tokens, costo_total_usd, etc.
        log          : Función de logging.
        desde_cache  : True si el proceso corrió desde caché (cache_runner).
        modo_cache   : "f2", "f3" o None. Describe desde qué fase se reanudó.
    """
    hora = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Descripción del modo de ejecución
    if desde_cache:
        modos = {
            "f3": "Re-evaluación desde caché — Solo Tercer Filtro",
            "f2": "Re-evaluación desde caché — Segundo + Tercer Filtro",
        }
        modo_texto = modos.get(modo_cache, "Re-evaluación desde caché")
        icono_modo = "🔄"
    else:
        modo_texto = "Ejecución completa (Fases 1 → 2 → 3)"
        icono_modo = "🚀"

    asunto = f"Auto. Filtrado HV — {vacante} — ✅ Ejecución exitosa"

    body = f"""
    <html><body style="font-family:Arial,sans-serif; color:#333; max-width:600px; margin:auto;">
      <h2 style="color:#2e7d32;">✅ Proceso completado exitosamente</h2>
      <table style="width:100%; border-collapse:collapse;">
        <tr><td style="padding:6px; font-weight:bold;">Vacante</td>
            <td style="padding:6px;">{vacante}</td></tr>
        <tr style="background:#f5f5f5;">
            <td style="padding:6px; font-weight:bold;">Tipo de ejecución</td>
            <td style="padding:6px;">{icono_modo} {modo_texto}</td></tr>
        <tr><td style="padding:6px; font-weight:bold;">Hora</td>
            <td style="padding:6px;">{hora}</td></tr>
      </table>

      <h3 style="color:#1565c0; margin-top:20px;">💰 Consumo de IA</h3>
      <table style="width:100%; border-collapse:collapse; border:1px solid #ddd;">
        <tr style="background:#e3f2fd;">
          <th style="padding:8px; text-align:left;">Concepto</th>
          <th style="padding:8px; text-align:right;">Valor</th>
        </tr>
        <tr>
          <td style="padding:8px;">Tokens input</td>
          <td style="padding:8px; text-align:right;">{costo.get('input_tokens', 0):,}</td>
        </tr>
        <tr style="background:#f5f5f5;">
          <td style="padding:8px;">Tokens output</td>
          <td style="padding:8px; text-align:right;">{costo.get('output_tokens', 0):,}</td>
        </tr>
        <tr>
          <td style="padding:8px;">Costo input</td>
          <td style="padding:8px; text-align:right;">${costo.get('costo_input_usd', 0):.6f}</td>
        </tr>
        <tr style="background:#f5f5f5;">
          <td style="padding:8px;">Costo output</td>
          <td style="padding:8px; text-align:right;">${costo.get('costo_output_usd', 0):.6f}</td>
        </tr>
        <tr style="font-weight:bold; background:#e8f5e9;">
          <td style="padding:8px;">TOTAL USD</td>
          <td style="padding:8px; text-align:right;">${costo.get('costo_total_usd', 0):.6f}</td>
        </tr>
      </table>
    </body></html>
    """

    _enviar(asunto, body, log)


# =================== CORREO DE ERROR ===================

def enviar_correo_error(asunto: str, mensaje: str, log=print, vacante=None, fatal: bool = False):
    """
    Notifica un error ocurrido durante la ejecución.

    Args:
        asunto   : Línea de asunto del correo.
        mensaje  : Detalle del error (traceback o descripción).
        log      : Función de logging.
        vacante  : Nombre de la vacante (opcional).
        fatal    : True si el proceso se detuvo completamente; False si fue un error parcial.
    """
    hora = datetime.now().strftime("%d/%m/%Y %H:%M")
    severidad_texto = "❌ Error fatal — proceso detenido" if fatal else "⚠️ Error parcial — proceso continuó"
    severidad_color = "#c62828" if fatal else "#e65100"
    severidad_bg    = "#ffebee" if fatal else "#fff3e0"

    vacante_str = vacante or "No especificada"

    # Escapar caracteres HTML en el traceback para mostrarlo en <pre>
    mensaje_escapado = (
        mensaje
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    body = f"""
    <html><body style="font-family:Arial,sans-serif; color:#333; max-width:600px; margin:auto;">
      <h2 style="color:{severidad_color};">{severidad_texto}</h2>
      <table style="width:100%; border-collapse:collapse;">
        <tr><td style="padding:6px; font-weight:bold;">Vacante</td>
            <td style="padding:6px;">{vacante_str}</td></tr>
        <tr style="background:#f5f5f5;">
            <td style="padding:6px; font-weight:bold;">Hora</td>
            <td style="padding:6px;">{hora}</td></tr>
        <tr>
            <td style="padding:6px; font-weight:bold;">Severidad</td>
            <td style="padding:6px; background:{severidad_bg}; font-weight:bold; color:{severidad_color};">
              {"🛑 FATAL" if fatal else "⚠️ PARCIAL"}</td></tr>
      </table>

      <h3 style="margin-top:20px;">📋 Detalle del error</h3>
      <pre style="background:#f5f5f5; padding:12px; border-left:4px solid {severidad_color};
                  font-size:12px; overflow-x:auto; white-space:pre-wrap;">{mensaje_escapado}</pre>
    </body></html>
    """

    _enviar(asunto, body, log)
