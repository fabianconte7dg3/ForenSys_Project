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
            
            io_write = data.get('io_write_mb', 0)
            pdf.cell(50, 8, "I/O Escritura:", 0, 0)
            pdf.cell(0, 8, f"{io_write:.2f} MB", 0, 1)
            
            if duration > 0:
                speed_read = data.get('io_read_mb', 0) / duration
                speed_write = io_write / duration
                pdf.cell(50, 8, "Velocidad Promedio:", 0, 0)
                pdf.cell(0, 8, f"Lectura: {speed_read:.2f} MB/s | Escritura: {speed_write:.2f} MB/s", 0, 1)
            
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

    # ===== AUDITORÍA DE IA (MÓDULO 8) =====
    ia_files = glob.glob(os.path.join(case_dir, "03_Results_(Resultados_Extraidos)", "Auditoria_IA_*.json"))
    if ia_files:
        for ia_file in sorted(ia_files):
            try:
                with open(ia_file, 'r') as f:
                    ia_data = json.load(f)
                
                pdf.set_fill_color(240, 240, 240)
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, f"Módulo Evaluado: Auditoría de IA (Módulo 8)", border=1, ln=1, fill=True)
                pdf.set_font("Arial", size=10)
                
                modelo = ia_data.get("modelo", "N/A")
                motor_url = ia_data.get("motor_url", "N/A")
                tokens = ia_data.get("tokens_count", 0)
                estado = ia_data.get("estado", "N/A")
                confianza = ia_data.get("alucinaciones", {}).get("confianza", "N/A")
                
                pdf.cell(50, 8, "Modelo LLM:", 0, 0)
                pdf.cell(0, 8, f"{modelo}", 0, 1)
                
                pdf.cell(50, 8, "Motor:", 0, 0)
                pdf.cell(0, 8, f"{motor_url}", 0, 1)
                
                pdf.cell(50, 8, "Tokens Procesados:", 0, 0)
                pdf.cell(0, 8, f"{tokens} tokens", 0, 1)
                
                pdf.cell(50, 8, "Nivel de Confianza:", 0, 0)
                pdf.cell(0, 8, f"{confianza}", 0, 1)
                
                pdf.cell(50, 8, "Estado del Análisis:", 0, 0)
                pdf.cell(0, 8, f"{estado}", 0, 1)
                
                # Calcular tiempo si tenemos timestamps
                t_ini = ia_data.get("timestamp_inicio_utc")
                t_fin = ia_data.get("timestamp_fin_utc")
                if t_ini and t_fin:
                    try:
                        from datetime import datetime as dt
                        fmt = "%Y-%m-%dT%H:%M:%S.%f"
                        d1 = dt.strptime(t_ini, fmt)
                        d2 = dt.strptime(t_fin, fmt)
                        dur = (d2 - d1).total_seconds()
                        pdf.cell(50, 8, "Tiempo de Inferencia:", 0, 0)
                        pdf.cell(0, 8, f"{dur:.2f} segundos", 0, 1)
                        if dur > 0:
                            speed = tokens / dur
                            pdf.cell(50, 8, "Velocidad de Generación:", 0, 0)
                            pdf.cell(0, 8, f"{speed:.2f} tokens/s", 0, 1)
                    except Exception:
                        pass
                
                pdf.ln(5)
            except Exception as e:
                print(f"[TELEMETRÍA] Error leyendo {ia_file}: {e}")


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
