#!/usr/bin/env python3
"""
app.py
======
Punto de entrada principal de la aplicación.

Uso:
    python app.py
"""

import tkinter as tk
from pathlib import Path

from config import CARPETA_DESCARGA
from ui import AppUI
from main import iniciar_proceso_thread


def main():
    """Punto de entrada principal."""
    
    # Crear carpeta de resultados
    CARPETA_DESCARGA.mkdir(parents=True, exist_ok=True)
    
    # Crear ventana
    root = tk.Tk()
    
    # Crear interfaz
    app = AppUI(root, iniciar_proceso_thread)
    
    # Ejecutar
    root.mainloop()


if __name__ == "__main__":
    main()
