# =========================
# CONFIGURAÇÃO INICIAL
# =========================
import streamlit as st

st.set_page_config(
    page_title="Desempenho Comercial",
    layout="wide",
    page_icon="📊"
)

# =========================
# IMPORTS
# =========================
import pandas as pd
import numpy as np
import re
import io

import plotly.graph_objects as go

# =========================
# FUNÇÕES AUXILIARES
# =========================
def limpar_moeda(valor):
    if pd.isna(valor):
        return 0.0
    if isinstance(valor, (int, float, np.number)):
        return float(valor)
    if isinstance(valor, str):
        v = valor.strip()
        if v in ("", "-"):
            return 0.0
        v = v.replace("R$", "").replace("r$", "").strip()
        v = re.sub(r"\.(?=\d{3},)", "", v)
        v = v.replace(",", ".")
        try:
            return float(v)
        except:
            return 0.0
    return 0.0


def format_large_numbers(value):
    if value is None or pd.isna(value):
        return ""
    return f"R$ {value:,.0f}".replace(",", ".")


# =========================
# CARREGAMENTO + PROCESSAMENTO (CACHE)
# =========================
@st.cache_data(show_spinner=True)
def carregar_dados():
    df = pd.read_parquet("consolidado.parquet")

    colunas_para_converter = [
        'Real', 'Meta Mês', 'Ticket Médio',
        'Novo', 'Refin', 'PORT + Refin da Port >=1,85',
        'Refin da Port < 1,85', 'Rep. Legal', 'META AUMENTO MARGEM'
    ]

    for col in colunas_para_converter:
        if col in df.columns and df[col].dtype == object:
            df[col] = df[col].apply(limpar_moeda)

    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")

    # --------- DIAS POR MÊS ---------
    df["ano_mes"] = df["Data"].dt.to_period("M")
    dias = (
        df.groupby(["Nome_Loja", "ano_mes"])
        .size()
        .rename("DIAS")
        .reset_index()
    )
    df = df.merge(dias, on=["Nome_Loja", "ano_mes"], how="left")

    # --------- META MÊS ---------
    df["Meta Mês"] = (
        df["Meta Mês"]
        .replace(0, pd.NA)
        .groupby([df["Nome_Loja"], df["ano_mes"]])
        .transform(lambda x: x.bfill())
        .fillna(0)
    )

    # --------- VARIAÇÃO ---------
    df = df.sort_values(["Nome_Loja", "ano_mes", "Data"])

    def variacao(x):
        v = x - x.shift(1)
        v.iloc[0] = x.iloc[0]
        return v

    df["Real_Variacao"] = (
        df.groupby(["Nome_Loja", "ano_mes"])["Real"]
        .transform(variacao)
    )

    # --------- META DIA ---------
    df["Meta Dia"] = df["Meta Mês"] / df["DIAS"]

    return df.drop(columns=["ano_mes"])


rede = carregar_dados()

# =========================
# UI PRINCIPAL
# =========================
st.title("Desempenho Comercial")

pagina = st.selectbox(
    "Selecione a página:",
    ["Produção"]
)

# =========================
# SIDEBAR — FILTROS
# =========================
st.sidebar.header("Filtros")

produto_sel = st.sidebar.selectbox(
    "Produto",
    ["Todos"] + sorted(rede["Produto"].dropna().unique())
)

regional_sel = st.sidebar.selectbox(
    "Regional",
    ["Todas"] + sorted(rede["Regional"].dropna().unique())
)

df_tmp = rede if regional_sel == "Todas" else rede[rede["Regional"] == regional_sel]

coordenador_sel = st.sidebar.selectbox(
    "Coordenador",
    ["Todos"] + sorted(df_tmp["Coordenador"].dropna().unique())
)

df_tmp = df_tmp if coordenador_sel == "Todos" else df_tmp[df_tmp["Coordenador"] == coordenador_sel]

loja_sel = st.sidebar.selectbox(
    "Loja",
    ["Todas"] + sorted(df_tmp["Nome_Loja"].dropna().unique())
)

anos = sorted(rede["Data"].dt.year.unique())
meses = sorted(rede["Data"].dt.month.unique())

ano_sel = st.sidebar.selectbox("Ano", anos, index=len(anos) - 1)
mes_sel = st.sidebar.selectbox("Mês", meses)

# =========================
# FILTRAGEM
# =========================
df_f = rede.copy()

if produto_sel != "Todos":
    df_f = df_f[df_f["Produto"] == produto_sel]
if regional_sel != "Todas":
    df_f = df_f[df_f["Regional"] == regional_sel]
if coordenador_sel != "Todos":
    df_f = df_f[df_f["Coordenador"] == coordenador_sel]
if loja_sel != "Todas":
    df_f = df_f[df_f["Nome_Loja"] == loja_sel]

df_f = df_f[
    (df_f["Data"].dt.year == ano_sel) &
    (df_f["Data"].dt.month == mes_sel)
]

if df_f.empty:
    st.warning("Nenhum dado após aplicar os filtros.")
    st.stop()

# =========================
# ACUMULADOS
# =========================
df_grouped = (
    df_f.groupby("Data", as_index=False)
    .agg({
        "Real_Variacao": "sum",
        "Meta Dia": "sum"
    })
    .sort_values("Data")
)

df_grouped["REAL_ACUM"] = df_grouped["Real_Variacao"].cumsum()
df_grouped["META_ACUM"] = df_grouped["Meta Dia"].cumsum()
df_grouped["DESVIO_DIA"] = df_grouped["Real_Variacao"] - df_grouped["Meta Dia"]
df_grouped["DESVIO_ACUM"] = df_grouped["REAL_ACUM"] - df_grouped["META_ACUM"]

# =========================
# GRÁFICOS
# =========================
st.subheader(f"{produto_sel} — {mes_sel}/{ano_sel}")

fig = go.Figure()
fig.add_bar(
    x=df_grouped["Data"],
    y=df_grouped["Real_Variacao"],
    name="Real Dia",
    marker_color="#EA9411"
)
fig.add_scatter(
    x=df_grouped["Data"],
    y=df_grouped["Meta Dia"],
    name="Meta Dia",
    mode="lines+markers",
    marker=dict(color="blue")
)

fig.update_layout(template="plotly_white", dragmode=False)
st.plotly_chart(fig, use_container_width=True)

# =========================
# TABELA FINAL
# =========================
st.subheader("Tabela Consolidada")

df_exibir = pd.DataFrame({
    "Data": df_grouped["Data"],
    "Produção Dia": df_grouped["Real_Variacao"].apply(format_large_numbers),
    "Meta Dia": df_grouped["Meta Dia"].apply(format_large_numbers),
    "Desvio Dia": df_grouped["DESVIO_DIA"].apply(format_large_numbers),
    "Produção Acumulada": df_grouped["REAL_ACUM"].apply(format_large_numbers),
    "Meta Acumulada": df_grouped["META_ACUM"].apply(format_large_numbers),
    "Desvio Acumulado": df_grouped["DESVIO_ACUM"].apply(format_large_numbers),
})

st.dataframe(df_exibir, use_container_width=True)

buffer = io.BytesIO()
df_exibir.to_excel(buffer, index=False, engine="openpyxl")
buffer.seek(0)

st.download_button(
    "Baixar tabela em Excel",
    buffer,
    f"consolidado_{mes_sel}_{ano_sel}.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
