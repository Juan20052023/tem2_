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
import io
import re
import pydeck as pdk # <-- NUEVA IMPORTACIÓN PARA EL MAPA INTERACTIVO

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
                            "Energia_Dia_kWh": datos_fila[1], # Se mantiene el nombre interno pero se etiqueta como kWh en UI
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
    # Usamos try/except por si el archivo aún no existe en la primera ejecución
    try:
        df = pd.read_csv(DATA_FILENAME, encoding='utf-8', engine='python')
    except FileNotFoundError:
        # Retornamos un dataframe vacío con la estructura si falla
        return pd.DataFrame(columns=["Fecha", "Concepto", "Energia_Dia_kWh", "Inc_Dia_Porc", "Energia_Mes_kWh", "Inc_Mes_Porc", "Energia_Año_kWh", "Inc_Año_Porc", "Ultimos_365_Dias_kWh"]), "Fecha"

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
# UTILIDADES PARA MAPAS
# -----------------------------------------------------------------------------
def convertir_coordenadas(coord_str):
    """Convierte coordenadas de Grados Minutos Segundos (DMS) a Decimales para el mapa."""
    coord_str = str(coord_str).strip()
    partes = re.findall(r"[\d.]+", coord_str)
    if len(partes) >= 3:
        grados = float(partes[0])
        minutos = float(partes[1])
        segundos = float(partes[2])
        decimal = grados + (minutos / 60.0) + (segundos / 3600.0)
        # Si es Sur (S) u Oeste (O/W), la coordenada es negativa
        if 'S' in coord_str.upper() or 'O' in coord_str.upper() or 'W' in coord_str.upper():
            decimal = -decimal
        return decimal
    return None

# -----------------------------------------------------------------------------
# UI & DASHBOARD
# -----------------------------------------------------------------------------

with st.spinner('Verificando y cargando datos del CENACE...'):
    df, TIME_COLUMN = load_data()

st.title("Dashboard Operación del Sistema Eléctrico, Acumulado")

# -----------------------------------------------------------------------------
# FILTROS, MAPA Y TABLA EN LA BARRA LATERAL
# -----------------------------------------------------------------------------
st.sidebar.header("Filtros")

if not df.empty:
    min_date = df[TIME_COLUMN].min()
    max_date = df[TIME_COLUMN].max()

    date_range = st.sidebar.slider(
        "Rango de fechas",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date)
    )
else:
    date_range = (datetime.now(), datetime.now())
    st.sidebar.warning("Aún no hay datos disponibles en el histórico.")

st.sidebar.markdown("---")

# --- CARGA Y PROCESAMIENTO DE DATOS DE CENTRALES ---
csv_centrales = """Central Hidroeléctrica,Ubicación (Ciudad/Prov),Latitud,Longitud,Oferta (MW),Aporte Nacional
Coca Codo Sinclair,"El Chaco, Napo","0° 28' 37.2"" S","77° 59' 24.0"" O",1500,33.11%
Paute Molino,"Sevilla de Oro, Azuay","2° 46' 8.4"" S","78° 45' 28.8"" O",1100,24.28%
Sopladora,"Sevilla de Oro, Azuay","2° 36' 54.0"" S","78° 32' 52.8"" O",487,10.75%
Minas San Francisco,"Pucará, Azuay","3° 18' 10.8"" S","79° 24' 10.8"" O",270,5.96%
Manduriacu,"Cotacachi, Imbabura","0° 18' 54.0"" N","78° 46' 51.6"" O",65,1.43%
Delsitanisagua,"Zamora, Zamora Chinchipe","3° 57' 25.2"" S","78° 44' 27.6"" O",180,3.97%
Mazar,"Sevilla de Oro, Azuay","2° 43' 12.0"" S","78° 39' 0.0"" O",170,3.75%
Agoyán,"Baños, Tungurahua","1° 23' 45.6"" S","78° 25' 19.2"" O",156,3.44%
San Francisco,"Baños, Tungurahua","1° 24' 50.4"" S","78° 16' 15.6"" O",230,5.08%
Marcel Laniado de Wind,"El Empalme, Guayas","2° 10' 37.2"" S","79° 50' 49.2"" O",213,4.70%
Toachi Pilatón,"Mejía, Pichincha","0° 25' 1.2"" S","78° 57' 0.0"" O",254,5.61%
Quijos,"Quijos, Napo","0° 25' 48.0"" S","77° 52' 12.0"" O",50,1.10%
Pucará,"Píllaro, Tungurahua","1° 10' 30.0"" S","78° 29' 10.0"" O",73,1.61%
Due,"Gonzalo Pizarro, Sucumbíos","0° 2' 45.0"" N","77° 20' 15.0"" O",49.71,1.10%
Cumbayá,"Quito, Pichincha","0° 11' 55.0"" S","78° 26' 15.0"" O",40,0.88%
Hidroabanico,"Macas, Morona Santiago","2° 17' 20.0"" S","78° 8' 50.0"" O",38.45,0.85%
Nayón,"Quito, Pichincha","0° 10' 10.0"" S","78° 26' 25.0"" O",29.7,0.66%
Ocaña,"La Troncal, Cañar","2° 28' 15.0"" S","79° 19' 40.0"" O",26.1,0.58%
Guangopolo,"Quito, Pichincha","0° 16' 12.0"" S","78° 27' 10.0"" O",20.92,0.46%
Calope,"Pangua, Cotopaxi","1° 7' 30.0"" S","79° 8' 45.0"" O",16.5,0.36%
Hidrosibimbe,"Echeandía, Bolívar","1° 25' 10.0"" S","79° 18' 20.0"" O",15.37,0.34%
Palmira-Nanegal,"Quito, Pichincha","0° 8' 20.0"" N","78° 40' 15.0"" O",10.36,0.23%
Hidrotambo,"Guaranda, Bolívar","1° 35' 15.0"" S","79° 0' 50.0"" O",8,0.18%
Alazán,"Cuenca, Azuay","2° 55' 10.0"" S","79° 1' 20.0"" O",6.23,0.14%
Vindobona,"Quito, Pichincha","0° 3' 40.0"" N","78° 28' 30.0"" O",5.86,0.13%
Pasachoa,"Mejía, Pichincha","0° 23' 15.0"" S","78° 28' 10.0"" O",4.5,0.10%
Illuchi N. 1,"Latacunga, Cotopaxi","0° 54' 20.0"" S","78° 35' 40.0"" O",4.2,0.09%"""

df_centrales = pd.read_csv(io.StringIO(csv_centrales))

# Crear columnas decimales para el mapa
df_centrales['latitude'] = df_centrales['Latitud'].apply(convertir_coordenadas)
df_centrales['longitude'] = df_centrales['Longitud'].apply(convertir_coordenadas)

# --- MAPA INTERACTIVO CON PYDECK ---
st.sidebar.subheader("Mapa de Centrales Hidroeléctricas Potencia Nominal")

# Definir la capa de puntos
layer = pdk.Layer(
    "ScatterplotLayer",
    data=df_centrales,
    get_position=["longitude", "latitude"],
    get_radius=12000, # Ajusta el tamaño de los círculos si los quieres más grandes/chicos
    get_fill_color=[255, 0, 0, 200], # Color rojo con un poco de transparencia
    pickable=True, # Habilita la interacción del mouse
)

# Definir la vista inicial del mapa
view_state = pdk.ViewState(
    latitude=df_centrales['latitude'].mean(),
    longitude=df_centrales['longitude'].mean(),
    zoom=5.5,
    pitch=0,
)

# Crear el mapa configurando el tooltip
mapa_deck = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip={"text": "{Central Hidroeléctrica}\nOferta: {Oferta (MW)} MW"}
)

# Mostrar el mapa en el sidebar
st.sidebar.pydeck_chart(mapa_deck)

st.sidebar.markdown("---")

# --- TABLA DE DATOS ACTUALIZADA ---
st.sidebar.subheader("Información de Centrales Hidroeléctricas")
# Quitamos las columnas auxiliares de lat/lon decimales para que la tabla luzca limpia
st.sidebar.dataframe(df_centrales.drop(columns=['latitude', 'longitude']), hide_index=True)

# -----------------------------------------------------------------------------
# FILTRADO BASE Y BALANCE ENERGÉTICO
# -----------------------------------------------------------------------------
if not df.empty:
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
    st.header("Estado del Sistema (kWh)")

    if not balance_df.empty:
        latest = balance_df.iloc[-1]

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Generación (kWh)", f"{latest['Total Generación']:,.0f}")
        col2.metric("Importación (kWh)", f"{latest['Total Importación']:,.0f}")
        col3.metric("Demanda (kWh)", f"{latest['Demanda']:,.0f}")

        balance_val = latest["Balance"]
        color = "normal" if balance_val >= 0 else "inverse"

        col4.metric(
            "Balance (kWh)",
            f"{balance_val:,.0f}",
            delta="Superávit" if balance_val >= 0 else "Déficit",
            delta_color=color
        )
    else:
        st.warning("No hay datos suficientes para calcular los KPIs en el rango seleccionado.")

    # -----------------------------------------------------------------------------
    # GRÁFICOS Y TABLA
    # -----------------------------------------------------------------------------
    st.header("Oferta vs Demanda")
    if not balance_df.empty:
        st.line_chart(balance_df, x="Fecha", y=["Oferta", "Demanda"])
        
        st.markdown("""
        ****
        - **Superávit:** Ocurre cuando la línea de **Oferta** (Generación + Importación) está por encima de la línea de **Demanda**. Esto indica que el sistema tiene energía suficiente para cubrir el consumo e incluso exportar o ahorrar agua en embalses.
        - **Oferta vs Demanda:** El cruce de estas líneas es crítico. Si la Demanda supera la Oferta, el sistema entra en déficit, lo que suele requerir cortes de carga o importaciones de emergencia para mantener la estabilidad de la frecuencia.
        """)

    st.header("Pérdidas del sistema (kWh)")
    if not balance_df.empty:
        st.line_chart(balance_df, x="Fecha", y="Total Pérdidas Transporte")

    st.header("Balance detallado (Unidades en Kilovatios-hora - kWh)")

    if not balance_df.empty:
        tabla_final = balance_df.copy()
        tabla_final.columns = [
            "Fecha", "Generación (kWh)", "Importación (kWh)", "Exportación (kWh)", 
            "Demanda (kWh)", "Pérdidas Transp. (kWh)", "Oferta Total (kWh)", 
            "Consumo Total (kWh)", "Balance/Superávit (kWh)"
        ]

        st.dataframe(tabla_final, use_container_width=True)