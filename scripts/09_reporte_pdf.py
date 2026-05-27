#!/usr/bin/env python3
import os
import re
import sys
import argparse
from datetime import datetime

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
except ImportError:
    print("[-] ERROR: La biblioteca 'reportlab' no está instalada.")
    print("    Ejecuta: pip install reportlab")
    sys.exit(1)

DIRECTORIO_DEFAULT = "/mnt/Destino_ForenSys"

def main():
    parser = argparse.ArgumentParser(description="Generador de Reporte PDF — Foren-Sys")
    parser.add_argument("--caso",  required=True,  help="ID del caso (Ej: TEST-123)")
    parser.add_argument("--dest",  required=False, default=DIRECTORIO_DEFAULT,
                        help=f"Ruta base donde vive el caso (default: {DIRECTORIO_DEFAULT})")
    args = parser.parse_args()

    caso_id = re.sub(r'[^a-zA-Z0-9_\-]', '', args.caso.strip())
    directorio_base = args.dest.strip()

    print(f"[PROGRESO:10] Iniciando generación de PDF para el caso: {caso_id}")

    carpeta_resultados = os.path.join(directorio_base, caso_id, "03_Results_(Resultados_Extraidos)")
    if not os.path.exists(carpeta_resultados):
        print(f"[-] ERROR: No se encontró la carpeta de resultados en: {carpeta_resultados}")
        sys.exit(1)

    # Rutas de origen
    ruta_maestro = os.path.join(carpeta_resultados, "Reporte_Forense_Maestro.txt")
    ruta_ia = os.path.join(carpeta_resultados, f"Sintesis_IA_{caso_id}.md")
    ruta_pdf = os.path.join(carpeta_resultados, f"Reporte_Legal_Final_{caso_id}.pdf")

    print(f"[PROGRESO:30] Compilando datos de reportes existentes...")

    # Leer Maestro
    texto_maestro = "No se encontró el Reporte Maestro."
    if os.path.exists(ruta_maestro):
        with open(ruta_maestro, 'r', encoding='utf-8', errors='ignore') as f:
            texto_maestro = f.read()

    # Leer IA
    texto_ia = "No se encontró la Síntesis IA (Módulo 8 no ejecutado)."
    if os.path.exists(ruta_ia):
        with open(ruta_ia, 'r', encoding='utf-8', errors='ignore') as f:
            texto_ia = f.read()

    print(f"[PROGRESO:60] Generando estructura del documento PDF...")

    doc = SimpleDocTemplate(ruta_pdf, pagesize=letter,
                            rightMargin=40, leftMargin=40,
                            topMargin=40, bottomMargin=40)
    
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    h1_style = styles['Heading1']
    normal_style = styles['Normal']
    
    # Estilo para texto preformateado (como código o texto plano exacto)
    code_style = ParagraphStyle(
        'CodeStyle',
        parent=styles['Code'],
        fontSize=8,
        leading=10,
        spaceAfter=10,
        wordWrap='CJK'  # Para envolver líneas largas
    )

    story = []

    # PORTADA
    story.append(Paragraph(f"Reporte Legal Forense", title_style))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph(f"<b>Caso ID:</b> {caso_id}", h1_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"<b>Fecha de Emisión:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
    story.append(Spacer(1, 2 * inch))
    story.append(Paragraph("Generado por la Plataforma Foren-Sys V3.0", normal_style))
    story.append(PageBreak())

    # SECCIÓN 1: REPORTE MAESTRO
    story.append(Paragraph("1. Reporte Forense Maestro (Cadena de Custodia)", h1_style))
    story.append(Spacer(1, 0.2 * inch))
    
    # Limitar longitud para evitar que un reporte masivo rompa el PDF por tiempo
    if len(texto_maestro) > 100000:
        texto_maestro = texto_maestro[:100000] + "\n\n[... TEXTO TRUNCADO POR TAMAÑO ...]"
    
    # Preformateado respeta los saltos de línea originales
    story.append(Preformatted(texto_maestro, code_style))
    story.append(PageBreak())

    # SECCIÓN 2: DICTAMEN IA
    story.append(Paragraph("2. Síntesis de Inteligencia Forense (IA Asistida)", h1_style))
    story.append(Spacer(1, 0.2 * inch))
    
    if len(texto_ia) > 100000:
        texto_ia = texto_ia[:100000] + "\n\n[... TEXTO TRUNCADO POR TAMAÑO ...]"
        
    story.append(Preformatted(texto_ia, code_style))

    print(f"[PROGRESO:85] Construyendo PDF en disco...")
    
    try:
        doc.build(story)
        print(f"[PROGRESO:100] Reporte PDF generado exitosamente: {ruta_pdf}")
    except Exception as e:
        print(f"[-] ERROR al generar el PDF: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
