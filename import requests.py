import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import urllib3
import csv

# Desactivamos advertencias de seguridad SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL_BASE = "https://smec.cenace.gob.ec/SMEC/ResultadoInforme1.do"

def obtener_rango_fechas():
    """Calcula el primer día del mes anterior y la fecha de ayer."""
    hoy = datetime.now()
    ayer = hoy - timedelta(days=1)
    
    # Calculamos el primer día del mes anterior
    # 1. Vamos al primero de este mes
    primero_este_mes = hoy.replace(day=1)
    # 2. Restamos un día para llegar al último del mes pasado
    ultimo_mes_pasado = primero_este_mes - timedelta(days=1)
    # 3. Vamos al primero de ese mes
    primero_mes_pasado = ultimo_mes_pasado.replace(day=1)
    
    return primero_mes_pasado, ayer

def scraping_automatico_simec():
    fecha_inicio, fecha_fin = obtener_rango_fechas()
    
    print(f"--- Robot SIMEC Activado ---")
    print(f"Rango: {fecha_inicio.strftime('%Y/%m/%d')} hasta {fecha_fin.strftime('%Y/%m/%d')}\n")
    
    datos_totales = []
    fecha_actual = fecha_inicio
    
    while fecha_actual <= fecha_fin:
        fecha_texto = fecha_actual.strftime("%Y/%m/%d")
        print(f"Consultando: {fecha_texto}...", end="\r")
        
        parametros = {'fecha': fecha_texto}
        
        try:
            respuesta = requests.get(URL_BASE, params=parametros, verify=False, timeout=15)
            respuesta.raise_for_status()
            
            sopa = BeautifulSoup(respuesta.text, 'html.parser')
            tabla = sopa.find('table', class_='bordeazul2')
            
            if tabla:
                filas = tabla.find_all('tr')
                for fila in filas:
                    celdas = fila.find_all('td', class_='bordegris')
                    
                    if len(celdas) >= 8:
                        datos_fila = [c.get_text(strip=True) for c in celdas]
                        
                        registro = {
                            "Fecha": fecha_texto,
                            "Concepto": datos_fila[0],
                            "Energia_Dia_kWh": datos_fila[1],
                            "Inc_Dia_Porc": datos_fila[2],
                            "Energia_Mes_kWh": datos_fila[3],
                            "Inc_Mes_Porc": datos_fila[4],
                            "Energia_Año_kWh": datos_fila[5],
                            "Inc_Año_Porc": datos_fila[6],
                            "Ultimos_365_Dias_kWh": datos_fila[7]
                        }
                        datos_totales.append(registro)
            
        except Exception as e:
            print(f"\n❌ Error en {fecha_texto}: {e}")
            
        # Un pequeño delay para no saturar el servidor del CENACE
        time.sleep(0.5) 
        fecha_actual += timedelta(days=1)
        
    print(f"\n\n✓ Extracción completada. Total de registros: {len(datos_totales)}")
    return datos_totales

# --- INICIO DEL PROCESO ---
datos_acumulados = scraping_automatico_simec()

if datos_acumulados:
    nombre_archivo = f"reporte_simec_historico_{datetime.now().strftime('%Y%m%d')}.csv"
    columnas = datos_acumulados[0].keys()
    
    with open(nombre_archivo, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        writer.writerows(datos_acumulados)
        
    print(f"📁 Datos guardados exitosamente en: {nombre_archivo}")
else:
    print("⚠️ No se obtuvieron datos para procesar.")