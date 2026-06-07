#!/usr/import/env python3
#!/usr/bin/env python3
import os
import re
import sys
import json
import glob
import argparse
from datetime import datetime

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Preformatted, PageBreak, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
except ImportError:
    print("[-] ERROR: La biblioteca 'reportlab' no está instalada.")
    print("    Ejecuta: pip install reportlab")
    sys.exit(1)

DIRECTORIO_DEFAULT = "/mnt/Destino_ForenSys"

# Estilos globales
styles = getSampleStyleSheet()
style_title = ParagraphStyle('TitleStyle', parent=styles['Title'], fontSize=24, spaceAfter=20)
style_h1 = ParagraphStyle('H1', parent=styles['Heading1'], fontSize=16, spaceAfter=12, textColor=colors.HexColor("#1e3a8a"))
style_h2 = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=14, spaceAfter=10, textColor=colors.HexColor("#2563eb"))
style_h3 = ParagraphStyle('H3', parent=styles['Heading3'], fontSize=12, spaceAfter=8)
style_normal = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=10, leading=14)
style_bullet = ParagraphStyle('BulletStyle', parent=styles['Normal'], fontSize=10, leading=14, leftIndent=20, bulletIndent=10)
style_code = ParagraphStyle('CodeStyle', parent=styles['Code'], fontSize=8, leading=10, spaceAfter=10, wordWrap='CJK')

# Componentes del documento
story = []

def header_footer(canvas, doc):
    canvas.saveState()
    
    # Header
    canvas.setFont('Helvetica-Bold', 10)
    canvas.setFillColor(colors.HexColor("#1e3a8a"))
    canvas.drawString(inch, letter[1] - 0.5 * inch, f"ForenSys v3.0 - Dictamen Pericial (Caso: {doc.caso_id})")
    
    # Línea separadora Header
    canvas.setStrokeColor(colors.lightgrey)
    canvas.setLineWidth(1)
    canvas.line(inch, letter[1] - 0.6 * inch, letter[0] - inch, letter[1] - 0.6 * inch)

    # Footer
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(colors.gray)
    canvas.drawString(inch, 0.5 * inch, "DOCUMENTO LEGAL CONFIDENCIAL")
    canvas.drawRightString(letter[0] - inch, 0.5 * inch, f"Página {doc.page}")
    
    canvas.restoreState()

def parse_markdown_to_story(text):
    """Convierte texto Markdown básico en objetos Paragraph de ReportLab"""
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.1 * inch))
            continue
            
        # Parsear negritas **texto** -> <b>texto</b>
        line = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line)
        
        if line.startswith('# '):
            story.append(Paragraph(line[2:], style_h1))
        elif line.startswith('## '):
            story.append(Paragraph(line[3:], style_h2))
        elif line.startswith('### '):
            story.append(Paragraph(line[4:], style_h3))
        elif line.startswith('- ') or line.startswith('* '):
            story.append(Paragraph(u"• " + line[2:], style_bullet))
        elif line.startswith('> '):
            # Citas
            p = Paragraph(f"<i>{line[2:]}</i>", style_normal)
            story.append(p)
        else:
            story.append(Paragraph(line, style_normal))

def crear_portada(caso_id):
    story.append(Spacer(1, 1.5 * inch))
    story.append(Paragraph("DICTAMEN PERICIAL FORENSE", style_title))
    story.append(Spacer(1, 0.5 * inch))
    
    data = [
        ["Número de Expediente:", caso_id],
        ["Fecha y Hora de Emisión:", datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        ["Plataforma de Adquisición:", "Foren-Sys v3.0 (Automated Triage)"],
        ["Estado de Integridad:", "Validado criptográficamente"]
    ]
    
    t = Table(data, colWidths=[2.5*inch, 3.5*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#f1f5f9")),
        ('TEXTCOLOR', (0,0), (0,-1), colors.HexColor("#334155")),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
    ]))
    
    story.append(t)
    story.append(Spacer(1, 2 * inch))
    story.append(Paragraph("<b>ADVERTENCIA LEGAL:</b> Este documento contiene hallazgos generados mediante adquisición automatizada y correlación de Inteligencia Artificial. Su contenido debe ser evaluado y ratificado por un perito informático certificado antes de ser presentado como prueba definitiva en un tribunal de justicia.", style_normal))
    story.append(PageBreak())

def inyectar_cadena_custodia(carpeta_resultados):
    story.append(Paragraph("1. Cadena de Custodia e Integridad", style_h1))
    story.append(Spacer(1, 0.2 * inch))
    
    ruta_hashes = os.path.join(carpeta_resultados, "hashes_integridad.json")
    if os.path.exists(ruta_hashes):
        story.append(Paragraph("A continuación se detallan los valores Hash criptográficos que garantizan la inmutabilidad de la evidencia adquirida durante el triaje:", style_normal))
        story.append(Spacer(1, 0.2 * inch))
        
        try:
            with open(ruta_hashes, 'r', encoding='utf-8') as f:
                hashes = json.load(f)
                
            tabla_data = [["Archivo / Evidencia", "Algoritmo", "Hash Criptográfico"]]
            
            for archivo, data in hashes.items():
                if isinstance(data, dict):
                    # Formato nuevo: {"MD5": "...", "SHA-1": "..."}
                    for alg, h in data.items():
                        tabla_data.append([archivo, alg, h])
                else:
                    # Formato antiguo: Hash directo
                    tabla_data.append([archivo, "SHA-256", data])
                    
            t = Table(tabla_data, colWidths=[2.5*inch, 1*inch, 3*inch])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1e3a8a")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
                ('FONTSIZE', (0,1), (-1,-1), 8),
                ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 8),
                ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
                ('WORDWRAP', (0,0), (-1,-1), True)
            ]))
            story.append(t)
        except Exception as e:
            story.append(Paragraph(f"<i>Error al parsear el archivo de hashes: {e}</i>", style_normal))
    else:
        story.append(Paragraph("<i>No se encontró el archivo de Hashes de Integridad (hashes_integridad.json).</i>", style_normal))
        
    story.append(PageBreak())

def inyectar_reporte_texto(titulo, ruta_archivo, seccion_numero):
    story.append(Paragraph(f"{seccion_numero}. {titulo}", style_h1))
    story.append(Spacer(1, 0.2 * inch))
    
    if os.path.exists(ruta_archivo):
        with open(ruta_archivo, 'r', encoding='utf-8', errors='ignore') as f:
            texto = f.read()
            if len(texto) > 100000:
                texto = texto[:100000] + "\n\n[... TEXTO TRUNCADO POR TAMAÑO ...]"
            parse_markdown_to_story(texto)
    else:
        story.append(Paragraph("<i>No se encontraron resultados para esta sección.</i>", style_normal))
    
    story.append(PageBreak())

def inyectar_reporte_glob(titulo, patron_glob, carpeta_resultados, seccion_numero):
    archivos = glob.glob(os.path.join(carpeta_resultados, patron_glob))
    if archivos:
        archivos.sort()
        inyectar_reporte_texto(titulo, archivos[-1], seccion_numero)

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

    ruta_pdf = os.path.join(carpeta_resultados, f"Reporte_Legal_Final_{caso_id}.pdf")

    print(f"[PROGRESO:30] Compilando datos de reportes existentes...")

    # Configurar el Template Base
    doc = BaseDocTemplate(ruta_pdf, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    doc.caso_id = caso_id # Para acceder en el header
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    template = PageTemplate(id='test', frames=frame, onPage=header_footer)
    doc.addPageTemplates([template])

    print(f"[PROGRESO:60] Generando estructura del documento PDF...")

    # 1. Portada
    crear_portada(caso_id)
    
    # 2. Cadena de Custodia (Hashes)
    inyectar_cadena_custodia(carpeta_resultados)
    
    # 3. Reporte Forense Maestro (texto plano pero parseado un poco)
    ruta_maestro = os.path.join(carpeta_resultados, "Reporte_Forense_Maestro.txt")
    inyectar_reporte_texto("Reporte Forense Maestro (Resumen de Triaje)", ruta_maestro, 2)
    
    # 4. Síntesis IA
    ruta_ia = os.path.join(carpeta_resultados, f"Sintesis_IA_{caso_id}.md")
    inyectar_reporte_texto("Síntesis de Inteligencia Forense (IA)", ruta_ia, 3)
    
    # 5. Document Intelligence
    inyectar_reporte_glob("Análisis Documental de Inteligencia (IA)", "Docs_IA_Completo_*.md", carpeta_resultados, 4)
    
    # 6. Visión Artificial
    inyectar_reporte_glob("Análisis de Visión Artificial (Imágenes)", "Vision_IA_Completo_*.md", carpeta_resultados, 5)

    print(f"[PROGRESO:85] Construyendo PDF en disco...")
    
    try:
        doc.build(story)
        print(f"[PROGRESO:100] Reporte PDF generado exitosamente: {ruta_pdf}")
    except Exception as e:
        print(f"[-] ERROR al generar el PDF: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
