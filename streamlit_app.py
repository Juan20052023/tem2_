import streamlit as st
import pandas as pd
from pathlib import Path

# -----------------------------------------------------------------------------
# CONFIG

st.set_page_config(
    page_title='Dashboard CENACE',
    page_icon='⚡',
    layout="wide"
)

# -----------------------------------------------------------------------------
# CARGA DE DATOS

@st.cache_data(ttl=1)
def load_data():
    DATA_FILENAME = Path(__file__).parent / "reporte_simec_historico_20260419.csv"

    df = pd.read_csv(DATA_FILENAME, encoding='latin1', engine='python')

    df.columns = df.columns.str.strip()

    df.columns = [
        col.replace("Ã³", "ó")
           .replace("Ã¡", "á")
           .replace("Ã©", "é")
           .replace("Ã±", "ñ")
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
# LOAD

df, TIME_COLUMN = load_data()

# -----------------------------------------------------------------------------
# UI

st.title("⚡ Dashboard Operación del Sistema Eléctrico")

# -----------------------------------------------------------------------------
# FILTROS

st.sidebar.header("Filtros")

min_date = df[TIME_COLUMN].min()
max_date = df[TIME_COLUMN].max()

date_range = st.sidebar.slider(
    "Rango de fechas",
    min_value=min_date,
    max_value=max_date,
    value=(min_date, max_date)
)

# -----------------------------------------------------------------------------
# FILTRADO BASE

df_filtered = df[
    (df[TIME_COLUMN] >= date_range[0]) &
    (df[TIME_COLUMN] <= date_range[1])
]

# -----------------------------------------------------------------------------
# 🔥 BALANCE ENERGÉTICO

def get_series(nombre):
    return df_filtered[df_filtered["Concepto"] == nombre][["Fecha", "Energia_Dia_kWh"]].rename(
        columns={"Energia_Dia_kWh": nombre}
    )

gen = get_series("Total Generación")
imp = get_series("Total Importación")
exp = get_series("Total Exportación")
dem = get_series("Demanda Distribución")
perd = get_series("Total Pérdidas Transporte")

# Merge todo por fecha
balance_df = gen.merge(imp, on="Fecha", how="left") \
                .merge(exp, on="Fecha", how="left") \
                .merge(dem, on="Fecha", how="left") \
                .merge(perd, on="Fecha", how="left")

# Llenar NaN
balance_df = balance_df.fillna(0)

# 🔥 CALCULOS
balance_df["Oferta"] = balance_df["Total Generación"] + balance_df["Total Importación"]
balance_df["Demanda"] = balance_df["Demanda Distribución"]
balance_df["Balance"] = balance_df["Oferta"] - balance_df["Demanda"]

# -----------------------------------------------------------------------------
# 📊 KPIs

st.header("📊 Estado del Sistema")

latest = balance_df.iloc[-1]

col1, col2, col3, col4 = st.columns(4)

col1.metric("⚡ Generación", f"{latest['Total Generación']:,.0f}")
col2.metric("📥 Importación", f"{latest['Total Importación']:,.0f}")
col3.metric("📊 Demanda", f"{latest['Demanda']:,.0f}")

balance_val = latest["Balance"]
color = "normal" if balance_val >= 0 else "inverse"

col4.metric(
    "⚖️ Balance",
    f"{balance_val:,.0f}",
    delta="Superávit" if balance_val >= 0 else "Déficit",
    delta_color=color
)

# -----------------------------------------------------------------------------
# 📈 OFERTA VS DEMANDA

st.header("📈 Oferta vs Demanda")

st.line_chart(
    balance_df,
    x="Fecha",
    y=["Oferta", "Demanda"]
)

# -----------------------------------------------------------------------------
# 📉 PÉRDIDAS

st.header("📉 Pérdidas del sistema")

st.line_chart(
    balance_df,
    x="Fecha",
    y="Total Pérdidas Transporte"
)

# -----------------------------------------------------------------------------
# 📋 TABLA

st.header("📋 Balance detallado")

st.dataframe(balance_df, use_container_width=True)