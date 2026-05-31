#!/usr/bin/env python3
"""
Módulo 10: Generador de Reporte de Telemetría (PDF)
Lee los archivos telemetry_*.json de un caso y genera un reporte auditable.
"""
import argparse
import glob
import json
import os
from datetime import datetime

from fpdf import FPDF

class TelemetryReportPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'ForenSys - Reporte de Rendimiento de Hardware y Telemetría', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, 'Auditoría de cumplimiento forense y métricas de carga física', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def generate_pdf(case_dir):
    json_files = glob.glob(os.path.join(case_dir, 'telemetry_*.json'))
    
    if not json_files:
        print(f"[TELEMETRÍA] No hay archivos JSON de telemetría en {case_dir}")
        return

    pdf = TelemetryReportPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"ID del Caso: {os.path.basename(case_dir.rstrip('/'))}", ln=1)
    pdf.cell(0, 10, f"Fecha de Reporte: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=1)
    pdf.ln(5)

    for j_file in sorted(json_files):
        try:
            with open(j_file, 'r') as f:
                data = json.load(f)
                
            module = data.get("module", "Desconocido")
            duration = data.get("duration_sec", 0)
            cpu_avg = data.get("cpu_percent_avg", 0)
            cpu_max = data.get("cpu_percent_max", 0)
            ram_avg = data.get("ram_mb_avg", 0)
            ram_max = data.get("ram_mb_max", 0)
            temp_max = data.get("temp_c_max", 0)
            
            pdf.set_fill_color(240, 240, 240)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, f"Módulo Evaluado: {module}", border=1, ln=1, fill=True)
            
            pdf.set_font("Arial", size=10)
            
            # Formateo visual
            pdf.cell(50, 8, "Tiempo Ejecución:", 0, 0)
            pdf.cell(0, 8, f"{duration:.2f} segundos", 0, 1)
            
            pdf.cell(50, 8, "Uso CPU (Promedio / Máx):", 0, 0)
            pdf.cell(0, 8, f"{cpu_avg:.1f}% / {cpu_max:.1f}%", 0, 1)
            
            pdf.cell(50, 8, "Uso RAM (Promedio / Pico):", 0, 0)
            pdf.cell(0, 8, f"{ram_avg:.1f} MB / {ram_max:.1f} MB", 0, 1)
            
            pdf.cell(50, 8, "I/O Lectura:", 0, 0)
            pdf.cell(0, 8, f"{data.get('io_read_mb', 0):.2f} MB", 0, 1)
            
            # Alerta de Temperatura
            pdf.cell(50, 8, "Temperatura Máxima:", 0, 0)
            if temp_max > 75:
                pdf.set_text_color(255, 0, 0)
                pdf.cell(0, 8, f"{temp_max:.1f} C (¡ALERTA TÉRMICA!)", 0, 1)
                pdf.set_text_color(0, 0, 0)
            else:
                pdf.cell(0, 8, f"{temp_max:.1f} C (Normal)", 0, 1)
                
            pdf.ln(5)
            
        except Exception as e:
            print(f"[TELEMETRÍA] Error leyendo {j_file}: {e}")

    out_pdf = os.path.join(case_dir, "Reporte_Rendimiento_Hardware.pdf")
    try:
        pdf.output(out_pdf)
        print(f"[TELEMETRÍA] Reporte PDF generado exitosamente en: {out_pdf}")
    except Exception as e:
        print(f"[TELEMETRÍA] Error generando PDF: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--caso_dir", type=str, required=True, help="Directorio del caso forense")
    args = parser.parse_args()
    
    generate_pdf(args.caso_dir)
