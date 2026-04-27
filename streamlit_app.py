import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import urllib3
import csv
import os
from pathlib import Path

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title='Dashboard CENACE (Acumulado)',
    layout="wide"
)

# Desactivamos advertencias de seguridad SSL para el scraping
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
URL_BASE = "https://smec.cenace.gob.ec/SMEC/ResultadoInforme1.do"
DATA_FILENAME = Path(__file__).parent / "reporte_simec_historico_dinamico.csv"

# -----------------------------------------------------------------------------
# FUNCIONES DE SCRAPING (Con lógica incremental)
# -----------------------------------------------------------------------------
def extraer_datos_rango(fecha_inicio, fecha_fin):
    """Extrae datos del CENACE para un rango de fechas específico usando tu lógica original."""
    datos_totales = []
    fecha_actual = fecha_inicio

    while fecha_actual <= fecha_fin:
        fecha_texto = fecha_actual.strftime("%Y/%m/%d")
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
                            "Energia_Dia_kWh": datos_fila[1], # Se mantiene el nombre interno pero se etiqueta como MWh en UI
                            "Inc_Dia_Porc": datos_fila[2],
                            "Energia_Mes_kWh": datos_fila[3],
                            "Inc_Mes_Porc": datos_fila[4],
                            "Energia_Año_kWh": datos_fila[5],
                            "Inc_Año_Porc": datos_fila[6],
                            "Ultimos_365_Dias_kWh": datos_fila[7]
                        }
                        datos_totales.append(registro)

        except Exception as e:
            print(f"Error en {fecha_texto}: {e}")

        time.sleep(0.5) # Delay para no saturar
        fecha_actual += timedelta(days=1)

    return datos_totales

def actualizar_archivo_csv():
    """Verifica el archivo CSV, determina qué fechas faltan y las añade."""
    hoy = datetime.now()
    ayer = hoy - timedelta(days=1)
    
    if not DATA_FILENAME.exists():
        fecha_inicio = hoy - timedelta(days=30)
        fecha_fin = ayer
        datos = extraer_datos_rango(fecha_inicio, fecha_fin)
        
        if datos:
            columnas = datos[0].keys()
            with open(DATA_FILENAME, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=columnas)
                writer.writeheader()
                writer.writerows(datos)
    
    else:
        df_existente = pd.read_csv(DATA_FILENAME, encoding='utf-8')
        ultima_fecha_str = df_existente['Fecha'].max()
        ultima_fecha = datetime.strptime(ultima_fecha_str, "%Y/%m/%d")
        
        if ultima_fecha.date() < ayer.date():
            fecha_inicio = ultima_fecha + timedelta(days=1)
            fecha_fin = ayer
            nuevos_datos = extraer_datos_rango(fecha_inicio, fecha_fin)
            
            if nuevos_datos:
                columnas = nuevos_datos[0].keys()
                with open(DATA_FILENAME, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=columnas)
                    writer.writerows(nuevos_datos)

@st.cache_data(ttl=86400)
def load_data():
    actualizar_archivo_csv()
    df = pd.read_csv(DATA_FILENAME, encoding='utf-8', engine='python')

    df.columns = df.columns.str.strip()
    df.columns = [
        col.replace("Ã³", "ó").replace("Ã¡", "á").replace("Ã©", "é").replace("Ã±", "ñ")
        for col in df.columns
    ]

    TIME_COLUMN = "Fecha"
    df[TIME_COLUMN] = pd.to_datetime(df[TIME_COLUMN], errors='coerce')
    df = df.dropna(subset=[TIME_COLUMN])
    df[TIME_COLUMN] = df[TIME_COLUMN].dt.to_pydatetime()

    numeric_cols = [col for col in df.columns if col not in ["Fecha", "Concepto"]]

    for col in numeric_cols:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace('"', '', regex=False)
        )
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df["Concepto"] = (
        df["Concepto"]
        .str.replace("Ã³", "ó")
        .str.replace("Ã¡", "á")
        .str.replace("Ã©", "é")
        .str.replace("Ã±", "ñ")
    )

    df = df.sort_values(TIME_COLUMN)
    return df, TIME_COLUMN

# -----------------------------------------------------------------------------
# UI & DASHBOARD
# -----------------------------------------------------------------------------

with st.spinner('Verificando y cargando datos del CENACE...'):
    df, TIME_COLUMN = load_data()

st.title("Dashboard Operación del Sistema Eléctrico, Acumulado")

# -----------------------------------------------------------------------------
# FILTROS Y BARRA LATERAL
# -----------------------------------------------------------------------------
st.sidebar.header("Filtros")

min_date = df[TIME_COLUMN].min()
max_date = df[TIME_COLUMN].max()

date_range = st.sidebar.slider(
    "Rango de fechas",
    min_value=min_date,
    max_value=max_date,
    value=(min_date, max_date)
)

st.sidebar.markdown("---")
st.sidebar.subheader("Información de Centrales Hidroeléctricas")

datos_centrales = {
    "Central Hidroeléctrica": [
        "Coca Codo Sinclair", "Paute Molino", "Sopladora", "Minas San Francisco",
        "Manduriacu", "Delsitanisagua", "Mazar", "Agoyán", "San Francisco",
        "Marcel Laniado de Wind", "Toachi Pilatón", "Quijos"
    ],
    "Ubicación (Ciudad/Prov)": [
        "El Chaco, Napo", "Sevilla de Oro, Azuay", "Sevilla de Oro, Azuay",
        "Pucará, Azuay", "Cotacachi, Imbabura", "Zamora, Zamora Chinchipe",
        "Sevilla de Oro, Azuay", "Baños, Tungurahua", "Baños, Tungurahua",
        "El Empalme, Guayas", "Mejía, Pichincha", "Quijos, Napo"
    ],
    "Latitud": [
        "0° 28' 37.2\" S", "2° 46' 8.4\" S", "2° 36' 54.0\" S", "3° 18' 10.8\" S",
        "0° 18' 54.0\" N", "3° 57' 25.2\" S", "2° 43' 12.0\" S", "1° 23' 45.6\" S",
        "1° 24' 50.4\" S", "2° 10' 37.2\" S", "0° 25' 1.2\" S", "0° 25' 48.0\" S"
    ],
    "Longitud": [
        "77° 59' 24.0\" O", "78° 45' 28.8\" O", "78° 32' 52.8\" O", "79° 24' 10.8\" O",
        "78° 46' 51.6\" O", "78° 44' 27.6\" O", "78° 39' 0.0\" O", "78° 25' 19.2\" O",
        "78° 16' 15.6\" O", "79° 50' 49.2\" O", "78° 57' 0.0\" O", "77° 52' 12.0\" O"
    ],
    "Oferta (MW)": [
        "1500", "1100", "487", "270", "65", "180", "170", "156", "230", "213", "254", "50"
    ],
    "Aporte Nacional": [
        "33.11%", "24.28%", "10.75%", "5.96%", "1.43%", "3.97%", "3.75%", "3.44%", "5.08%", "4.70%", "5.61%", "1.10%"
    ]
}

df_centrales = pd.DataFrame(datos_centrales)
st.sidebar.dataframe(df_centrales, hide_index=True)

# -----------------------------------------------------------------------------
# FILTRADO BASE Y BALANCE ENERGÉTICO
# -----------------------------------------------------------------------------
df_filtered = df[
    (df[TIME_COLUMN] >= date_range[0]) &
    (df[TIME_COLUMN] <= date_range[1])
]

def get_series(nombre):
    return df_filtered[df_filtered["Concepto"] == nombre][["Fecha", "Energia_Dia_kWh"]].rename(
        columns={"Energia_Dia_kWh": nombre}
    )

gen = get_series("Total Generación")
imp = get_series("Total Importación")
exp = get_series("Total Exportación")
dem = get_series("Demanda Distribución")
perd = get_series("Total Pérdidas Transporte")

balance_df = gen.merge(imp, on="Fecha", how="left") \
                .merge(exp, on="Fecha", how="left") \
                .merge(dem, on="Fecha", how="left") \
                .merge(perd, on="Fecha", how="left")

balance_df = balance_df.fillna(0)

balance_df["Oferta"] = balance_df["Total Generación"] + balance_df["Total Importación"]
balance_df["Demanda"] = balance_df["Demanda Distribución"]
balance_df["Balance"] = balance_df["Oferta"] - balance_df["Demanda"]

# -----------------------------------------------------------------------------
# KPIs
# -----------------------------------------------------------------------------
st.header("Estado del Sistema (MWh)")

if not balance_df.empty:
    latest = balance_df.iloc[-1]

    col1, col2, col3, col4 = st.columns(4)

    # Se añade la unidad oficial MWh según reportes de CENACE
    col1.metric("Generación (MWh)", f"{latest['Total Generación']:,.0f}")
    col2.metric("Importación (MWh)", f"{latest['Total Importación']:,.0f}")
    col3.metric("Demanda (MWh)", f"{latest['Demanda']:,.0f}")

    balance_val = latest["Balance"]
    color = "normal" if balance_val >= 0 else "inverse"

    col4.metric(
        "Balance (MWh)",
        f"{balance_val:,.0f}",
        delta="Superávit" if balance_val >= 0 else "Déficit",
        delta_color=color
    )
else:
    st.warning("No hay datos suficientes para calcular los KPIs.")

# -----------------------------------------------------------------------------
# GRÁFICOS Y TABLA
# -----------------------------------------------------------------------------
st.header("Oferta vs Demanda")
if not balance_df.empty:
    st.line_chart(balance_df, x="Fecha", y=["Oferta", "Demanda"])
    
    # INTERPRETACIÓN SOLICITADA
    st.markdown("""
    ****
    - **Superávit:** Ocurre cuando la línea de **Oferta** (Generación + Importación) está por encima de la línea de **Demanda**. Esto indica que el sistema tiene energía suficiente para cubrir el consumo e incluso exportar o ahorrar agua en embalses.
    - **Oferta vs Demanda:** El cruce de estas líneas es crítico. Si la Demanda supera la Oferta, el sistema entra en déficit, lo que suele requerir cortes de carga o importaciones de emergencia para mantener la estabilidad de la frecuencia.
    """)

st.header("Pérdidas del sistema (MWh)")
if not balance_df.empty:
    st.line_chart(balance_df, x="Fecha", y="Total Pérdidas Transporte")

st.header("Balance detallado (Unidades en Megavatios-hora - MWh)")

# Renombrar columnas para la tabla final para evitar confusiones
tabla_final = balance_df.copy()
tabla_final.columns = [
    "Fecha", "Generación (MWh)", "Importación (MWh)", "Exportación (MWh)", 
    "Demanda (MWh)", "Pérdidas Transp. (MWh)", "Oferta Total (MWh)", 
    "Consumo Total (MWh)", "Balance/Superávit (MWh)"
]

st.dataframe(tabla_final, use_container_width=True)