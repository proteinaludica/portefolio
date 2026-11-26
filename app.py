"""Análise de portefólio de investimentos (Streamlit + Plotly + yfinance).

Como correr:  streamlit run app.py
"""

import io
import math
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="O meu portefólio", page_icon="📊", layout="wide")

EXEMPLO = Path(__file__).parent / "portefolio_exemplo.csv"

# Nome interno de cada coluna e variantes aceites no ficheiro CSV.
COLUNAS = {
    "ticker": ["ticker", "simbolo", "codigo"],
    "quantidade": ["quantidade", "qtd", "qty"],
    "preco_medio": [
        "preco medio de compra",
        "preco medio",
        "preco de compra",
        "pmc",
    ],
    "tipo": ["tipo de activo", "tipo de ativo", "tipo", "classe"],
    "setor": ["setor", "sector"],
    "pais": ["pais", "country"],
}
COLUNAS_OPCIONAIS = {
    "data_compra": ["data de compra", "data da compra", "data compra", "data"],
}
PERIODOS = {"3 meses": "3mo", "12 meses": "1y", "5 anos": "5y"}
NOMES_BONITOS = {
    "data_compra": "Data de Compra",
    "ticker": "Ticker",
    "quantidade": "Quantidade",
    "preco_medio": "Preço Médio de Compra",
    "tipo": "Tipo de Activo",
    "setor": "Setor",
    "pais": "País",
    "preco_atual": "Preço Actual (€)",
    "valor_investido": "Valor Investido (€)",
    "valor_atual": "Valor Actual (€)",
    "pl_abs": "P&L (€)",
    "pl_pct": "P&L (%)",
    "estado": "Estado do preço",
}


# ------------------------------------------------------------------ leitura
def normalizar(texto: str) -> str:
    """Tira acentos, maiúsculas e espaços a mais."""
    sem_acentos = unicodedata.normalize("NFKD", str(texto))
    sem_acentos = "".join(c for c in sem_acentos if not unicodedata.combining(c))
    return " ".join(sem_acentos.lower().split())


def para_numero(valor) -> float:
    """Converte '1.234,56', '1234,56' ou '1234.56' em número."""
    if pd.isna(valor):
        return float("nan")
    texto = str(valor).strip().replace("€", "").replace("$", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return float("nan")


def ler_csv(ficheiro) -> pd.DataFrame:
    """Lê o CSV (vírgula ou ponto e vírgula; UTF-8 ou Excel antigo)."""
    conteudo = ficheiro.read() if hasattr(ficheiro, "read") else ficheiro
    if isinstance(conteudo, str):
        conteudo = conteudo.encode("utf-8")
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1")
    df = pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str)

    mapa = {}
    for coluna in df.columns:
        chave = normalizar(coluna)
        for interno, variantes in (COLUNAS | COLUNAS_OPCIONAIS).items():
            if chave in variantes:
                mapa[coluna] = interno
    df = df.rename(columns=mapa)

    em_falta = [NOMES_BONITOS[c] for c in COLUNAS if c not in df.columns]
    if em_falta:
        raise ValueError("Faltam colunas no ficheiro: " + ", ".join(em_falta))

    if "data_compra" not in df.columns:
        df["data_compra"] = None
    df = df[list(COLUNAS) + ["data_compra"]].copy()
    bruto = df["data_compra"]
    df["data_compra"] = pd.to_datetime(bruto, dayfirst=True, errors="coerce", format="mixed")
    datas_ma = bruto.notna() & df["data_compra"].isna()
    if datas_ma.any():
        st.warning(
            f"{int(datas_ma.sum())} data(s) de compra não foram entendidas e serão ignoradas. "
            "Use o formato dd/mm/aaaa."
        )
    df["quantidade"] = df["quantidade"].map(para_numero)
    df["preco_medio"] = df["preco_medio"].map(para_numero)
    for c in ("ticker", "tipo", "setor", "pais"):
        df[c] = df[c].fillna("Sem indicação").str.strip()

    invalidas = df["quantidade"].isna() | df["preco_medio"].isna()
    if invalidas.any():
        st.warning(
            f"{int(invalidas.sum())} linha(s) ignorada(s) por terem quantidade "
            "ou preço inválidos."
        )
        df = df[~invalidas]

    df["valor_investido"] = df["quantidade"] * df["preco_medio"]
    return df.reset_index(drop=True)


# ------------------------------------------------------------ dados de mercado
def simbolo_yahoo(ticker: str, tipo: str) -> str | None:
    """Símbolo a procurar no Yahoo Finance. P2P não tem cotação."""
    tipo_norm = normalizar(tipo)
    if tipo_norm == "p2p":
        return None
    simbolo = ticker.strip().upper()
    # Criptomoedas: BTC passa a BTC-EUR (preço já em euros).
    if tipo_norm in ("crypto", "cripto", "criptomoeda") and "-" not in simbolo:
        simbolo += "-EUR"
    return simbolo


@st.cache_data(ttl=300, show_spinner=False)
def buscar_precos(simbolos: tuple):
    """Devolve ({símbolo: preço em euros ou None}, hora da consulta).

    O Yahoo dá o preço na moeda da bolsa (dólares, libras...). Aqui converte-se
    tudo para euros. Os dados têm um atraso típico de cerca de 15 minutos.
    """
    brutos = {}
    for s in simbolos:
        try:
            info = yf.Ticker(s).fast_info
            preco = float(info["last_price"])
            if preco != preco:  # NaN
                raise ValueError("sem preço")
            brutos[s] = (preco, info["currency"])
        except Exception:
            brutos[s] = None

    taxas = {"EUR": 1.0}
    resultado = {}
    for s, valor in brutos.items():
        if valor is None:
            resultado[s] = None
            continue
        preco, moeda = valor
        if moeda in ("GBp", "GBX"):  # libras em "pence"
            preco, moeda = preco / 100, "GBP"
        if moeda not in taxas:
            try:
                taxas[moeda] = float(yf.Ticker(f"{moeda}EUR=X").fast_info["last_price"])
            except Exception:
                taxas[moeda] = None
        resultado[s] = None if taxas[moeda] is None else preco * taxas[moeda]
    return resultado, datetime.now()


def _data_noticia(valor):
    if valor is None:
        return pd.NaT
    if isinstance(valor, (int, float)):
        return pd.to_datetime(valor, unit="s", utc=True)
    return pd.to_datetime(valor, utc=True, errors="coerce")


@st.cache_data(ttl=900, show_spinner=False)
def buscar_noticias(simbolos: tuple, por_ticker: int = 3) -> list[dict]:
    """As notícias mais recentes de cada símbolo (título, fonte, link, data)."""
    noticias = []
    for s in simbolos:
        try:
            itens = yf.Ticker(s).news or []
        except Exception:
            continue
        do_simbolo = []
        for item in itens:
            c = item.get("content", item)  # o formato mudou entre versões
            titulo = c.get("title")
            link = (
                (c.get("canonicalUrl") or c.get("clickThroughUrl") or {}).get("url")
                or c.get("link")
            )
            fonte = (c.get("provider") or {}).get("displayName") or c.get("publisher")
            if not titulo or not link:
                continue
            do_simbolo.append(
                {
                    "simbolo": s,
                    "titulo": titulo,
                    "fonte": fonte or "Fonte desconhecida",
                    "link": link,
                    "data": _data_noticia(c.get("pubDate") or c.get("providerPublishTime")),
                }
            )
        do_simbolo = sorted(
            do_simbolo,
            key=lambda n: n["data"] if not pd.isna(n["data"]) else pd.Timestamp(0, tz="UTC"),
            reverse=True,
        )
        noticias.extend(do_simbolo[:por_ticker])
    return noticias


def juntar_precos(df: pd.DataFrame, precos: dict) -> pd.DataFrame:
    """Acrescenta preço actual, valor actual e P&L a cada posição."""
    df = df.copy()
    df["simbolo"] = [simbolo_yahoo(t, tp) for t, tp in zip(df["ticker"], df["tipo"])]
    df["preco_atual"] = df["simbolo"].map(lambda s: precos.get(s) if s else None)

    def estado(linha):
        if pd.isna(linha["simbolo"]):
            return "Sem cotação (ao custo)"
        if pd.isna(linha["preco_atual"]):
            return "Não encontrado (ao custo)"
        return "Actualizado"

    df["estado"] = df.apply(estado, axis=1)
    com_preco = df["preco_atual"].notna()
    df["valor_atual"] = df["valor_investido"]  # sem preço, conta ao custo
    df.loc[com_preco, "valor_atual"] = (
        df.loc[com_preco, "quantidade"] * df.loc[com_preco, "preco_atual"]
    )
    df["pl_abs"] = df["valor_atual"] - df["valor_investido"]
    df["pl_pct"] = df["pl_abs"] / df["valor_investido"] * 100
    return df


# ------------------------------------------------------------ evolução temporal
BENCHMARKS = {
    "S&P 500 (^GSPC)": "^GSPC",
    "VWCE - FTSE All-World (VWCE.DE)": "VWCE.DE",
    "MSCI World (IWDA.AS)": "IWDA.AS",
}


def _limpar_serie(serie: pd.Series) -> pd.Series:
    """Datas sem fuso horário nem horas, sem repetidos nem vazios."""
    serie = serie.dropna()
    datas = pd.to_datetime(serie.index)
    if datas.tz is not None:
        datas = datas.tz_localize(None)
    serie.index = datas.normalize()
    return serie[~serie.index.duplicated(keep="last")]


@st.cache_data(ttl=3600, show_spinner=False)
def buscar_historico(simbolos: tuple, periodo: str = "1y") -> pd.DataFrame:
    """Preços de fecho diários do período pedido (3mo, 1y, 5y), em euros.

    Uma coluna por símbolo. Os símbolos sem dados ficam de fora. Os preços
    estão ajustados a dividendos e desdobramentos (retorno total).
    """
    series = {}
    taxas = {}
    for s in simbolos:
        try:
            ticker = yf.Ticker(s)
            hist = _limpar_serie(ticker.history(period=periodo, auto_adjust=True)["Close"])
            moeda = ticker.fast_info["currency"]
            if hist.empty:
                continue
            if moeda in ("GBp", "GBX"):
                hist, moeda = hist / 100, "GBP"
            if moeda != "EUR":
                if moeda not in taxas:
                    cambio = yf.Ticker(f"{moeda}EUR=X").history(period=periodo)["Close"]
                    taxas[moeda] = _limpar_serie(cambio)
                cambio = taxas[moeda]
                if cambio.empty:
                    continue
                datas = hist.index.union(cambio.index)
                hist = (hist * cambio.reindex(datas).ffill().reindex(hist.index)).dropna()
            series[s] = hist
        except Exception:
            continue
    return pd.DataFrame(series).sort_index() if series else pd.DataFrame()


def retornos_carteira(precos: pd.DataFrame, pesos: pd.Series) -> pd.Series:
    """Retornos diários da carteira com os pesos actuais constantes.

    Cada dia aplica os mesmos pesos aos retornos diários dos activos. Se um
    activo ainda não tinha preço, os pesos dos restantes são refeitos.
    """
    colunas = [c for c in precos.columns if c in pesos.index]
    p = precos[colunas].sort_index().ffill()
    retornos = p / p.shift(1) - 1
    pesos_dia = retornos.notna().mul(pesos[colunas], axis=1)
    pesos_dia = pesos_dia.div(pesos_dia.sum(axis=1), axis=0).fillna(0)
    return (retornos.fillna(0) * pesos_dia).sum(axis=1)


def retornos_reais(precos: pd.DataFrame, lotes: pd.DataFrame) -> pd.Series:
    """Retornos diários da carteira real, com as quantidades e datas de compra.

    Cada lote (linha do CSV) entra na carteira na data de compra. Lotes sem data
    contam desde o início do período. A compra no próprio dia não conta como
    retorno (retorno ponderado no tempo): só mexe o preço dos activos já detidos.
    """
    p = precos.sort_index().ffill()
    valor = pd.Series(0.0, index=p.index)
    entradas = pd.Series(0.0, index=p.index)
    for _, lote in lotes.iterrows():
        if lote["simbolo"] not in p.columns:
            continue
        preco = p[lote["simbolo"]]
        activo = preco.notna()
        if pd.notna(lote["data_compra"]):
            activo = activo & (p.index >= lote["data_compra"])
        valor_lote = preco.fillna(0.0) * lote["quantidade"] * activo
        entrou = activo & ~activo.shift(1, fill_value=bool(activo.iloc[0]))
        valor = valor + valor_lote
        entradas = entradas + valor_lote * entrou
    anterior = valor.shift(1)
    retorno = (valor - entradas) / anterior - 1
    return retorno.where(anterior > 0, 0.0).fillna(0.0)


def curva_carteira(precos: pd.DataFrame, pesos: pd.Series) -> pd.Series:
    """Rentabilidade acumulada (%) da carteira com os pesos actuais constantes."""
    return ((1 + retornos_carteira(precos, pesos)).cumprod() - 1) * 100


def alinhar_benchmark(curva: pd.Series, benchmark: pd.Series):
    """Põe carteira e benchmark nas mesmas datas, ambos a 0 % no primeiro dia."""
    datas = curva.index.union(benchmark.index)
    b = benchmark.reindex(datas).ffill().reindex(curva.index).dropna()
    if b.empty:
        return None
    c = curva.loc[b.index]
    c = ((1 + c / 100) / (1 + c.iloc[0] / 100) - 1) * 100
    b = (b / b.iloc[0] - 1) * 100
    return c, b


def grafico_evolucao(carteira_pct: pd.Series, bench_pct: pd.Series, nome_bench: str, rotulo: str = "12 meses"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=carteira_pct.index, y=carteira_pct, name="A minha carteira",
                             mode="lines", line=dict(width=3, color="#1f77b4")))
    fig.add_trace(go.Scatter(x=bench_pct.index, y=bench_pct, name=nome_bench,
                             mode="lines", line=dict(width=2, color="#ff7f0e", dash="dot")))
    fig.add_hline(y=0, line_width=1, line_color="gray")
    fig.update_traces(hovertemplate="%{y:+.2f} %")
    fig.update_layout(
        title=f"Performance acumulada ({rotulo}, em euros)",
        hovermode="x unified",
        yaxis=dict(ticksuffix=" %", title="Retorno acumulado"),
        xaxis_title="",
        legend=dict(orientation="h", y=-0.15),
        margin=dict(t=60, l=10, r=10, b=10),
    )
    return fig


DIAS_BOLSA = 252  # dias de negociação num ano


def _risco_serie(ret: pd.Series, taxa_livre: float) -> dict:
    """Volatilidade anualizada, Sharpe e queda máxima de uma série de retornos diários."""
    vol = ret.std() * math.sqrt(DIAS_BOLSA)
    sharpe = (ret.mean() * DIAS_BOLSA - taxa_livre) / vol if vol > 0 else float("nan")
    valor = (1 + ret).cumprod()
    pico = valor.cummax().clip(lower=1.0)  # o capital inicial conta como pico
    queda = valor / pico - 1
    return {"volatilidade": vol, "sharpe": sharpe, "queda_maxima": queda.min(), "queda": queda}


def metricas_risco(ret_carteira: pd.Series, ret_benchmark: pd.Series, taxa_livre: float):
    """Métricas de risco da carteira e do benchmark nas datas em comum.

    Devolve None se houver menos de 30 dias em comum.
    """
    juntos = pd.concat([ret_carteira, ret_benchmark], axis=1, join="inner").dropna()
    if len(juntos) < 30:
        return None
    juntos.columns = ["carteira", "benchmark"]
    variancia = juntos["benchmark"].var()
    beta = juntos["carteira"].cov(juntos["benchmark"]) / variancia if variancia > 0 else float("nan")
    return {
        "dias": len(juntos),
        "beta": beta,
        "carteira": _risco_serie(juntos["carteira"], taxa_livre),
        "benchmark": _risco_serie(juntos["benchmark"], taxa_livre),
    }


def grafico_quedas(queda_c: pd.Series, queda_b: pd.Series, nome_bench: str):
    """Quanto a carteira e o benchmark estiveram abaixo do máximo anterior."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=queda_c.index, y=queda_c * 100, name="A minha carteira",
                             fill="tozeroy", line=dict(color="#1f77b4")))
    fig.add_trace(go.Scatter(x=queda_b.index, y=queda_b * 100, name=nome_bench,
                             line=dict(color="#ff7f0e", dash="dot")))
    fig.update_traces(hovertemplate="%{y:.2f} %")
    fig.update_layout(
        title="Queda face ao máximo anterior (drawdown)",
        hovermode="x unified",
        yaxis=dict(ticksuffix=" %"),
        legend=dict(orientation="h", y=-0.15),
        margin=dict(t=60, l=10, r=10, b=10),
    )
    return fig


# ------------------------------------------------------------------ gráficos
def grafico_alocacao(df, coluna, titulo, tipo, valor="valor_investido"):
    """Pie chart ou treemap com a soma por categoria."""
    agrupado = df.groupby(coluna, as_index=False)[valor].sum()
    agrupado["percentagem"] = agrupado[valor] / agrupado[valor].sum()
    if tipo == "Treemap":
        fig = px.treemap(
            agrupado, path=[coluna], values=valor, title=titulo,
            custom_data=["percentagem"],
        )
        fig.update_traces(
            texttemplate="%{label}<br>%{value:,.2f} €<br>%{customdata[0]:.1%}",
            hovertemplate="%{label}<br>%{value:,.2f} €<br>%{customdata[0]:.1%}<extra></extra>",
        )
    else:
        fig = px.pie(agrupado, names=coluna, values=valor, title=titulo, hole=0.35)
        fig.update_traces(
            textinfo="label+percent",
            hovertemplate="%{label}<br>%{value:,.2f} €<br>%{percent}<extra></extra>",
        )
    fig.update_layout(margin=dict(t=60, l=10, r=10, b=10))
    return fig


def grafico_pl(df):
    """Barras com o P&L (%) de cada posição."""
    d = df.sort_values("pl_pct")
    fig = px.bar(
        d, x="pl_pct", y="ticker", orientation="h",
        title="P&L por posição (%)",
        color=d["pl_pct"] >= 0,
        color_discrete_map={True: "#2e7d32", False: "#c62828"},
    )
    fig.update_traces(hovertemplate="%{y}: %{x:.2f} %<extra></extra>")
    fig.update_layout(showlegend=False, margin=dict(t=60, l=10, r=10, b=10),
                      xaxis_title="%", yaxis_title="")
    return fig


def mostrar_noticia(n: dict):
    titulo = n["titulo"].replace("[", "(").replace("]", ")")
    data = "" if pd.isna(n["data"]) else f" · {n['data']:%d/%m/%Y %H:%M}"
    st.markdown(f"**[{titulo}]({n['link']})**  \n{n['fonte']}{data}")


def cor_pl(valor):
    if pd.isna(valor):
        return ""
    return "color: #2e7d32" if valor >= 0 else "color: #c62828"


# ---------------------------------------------------------------- interface
st.title("📊 O meu portefólio de investimentos")

with st.sidebar:
    st.header("Dados")
    ficheiro = st.file_uploader("Carregue o ficheiro CSV", type=["csv"])
    usar_exemplo = st.checkbox("Usar dados de exemplo", disabled=not EXEMPLO.exists())
    tipo_grafico = st.radio("Tipo de gráfico", ["Pie Chart", "Treemap"])
    base_graficos = st.radio("Gráficos de alocação por", ["Valor actual", "Valor investido"])
    st.header("Período de análise")
    rotulo_periodo = st.selectbox("Histórico a analisar", list(PERIODOS), index=1)
    st.header("Benchmark")
    escolha = st.selectbox("Comparar com", list(BENCHMARKS) + ["Outro símbolo"])
    if escolha == "Outro símbolo":
        simbolo_bench = st.text_input("Símbolo (Yahoo Finance)", "^GSPC").strip().upper()
        nome_bench = simbolo_bench
    else:
        simbolo_bench = BENCHMARKS[escolha]
        nome_bench = escolha
    if st.button("🔄 Actualizar preços e notícias"):
        st.cache_data.clear()
    st.caption(
        "Colunas necessárias: Ticker, Quantidade, Preço Médio de Compra, "
        "Tipo de Activo, Setor, País. O preço médio de compra é lido em euros."
    )

if ficheiro is None and not usar_exemplo:
    st.info("Carregue um ficheiro CSV na barra lateral para começar.")
    st.stop()

try:
    if ficheiro is not None:
        carteira = ler_csv(ficheiro)
    else:
        carteira = ler_csv(EXEMPLO.read_bytes())
except Exception as erro:
    st.error(f"Não consegui ler o ficheiro. {erro}")
    st.stop()

if carteira.empty:
    st.error("O ficheiro não tem linhas válidas.")
    st.stop()

# Preços actuais
simbolos = tuple(
    sorted({s for s in (simbolo_yahoo(t, tp) for t, tp in zip(carteira["ticker"], carteira["tipo"])) if s})
)
with st.spinner("A procurar preços actuais..."):
    precos, hora = buscar_precos(simbolos)
carteira = juntar_precos(carteira, precos)

sem_preco = carteira[carteira["estado"] == "Não encontrado (ao custo)"]
if len(simbolos) and sem_preco.shape[0] == len(simbolos):
    st.error(
        "Não consegui obter nenhum preço. Verifique a ligação à internet. "
        "Os valores abaixo estão ao preço de compra."
    )
elif not sem_preco.empty:
    st.warning(
        "Sem preço no Yahoo Finance para: " + ", ".join(sem_preco["ticker"])
        + ". Confirme o símbolo (ex.: EDP.LS para Lisboa, VWCE.DE para Xetra)."
    )

# Historial do período escolhido (usado no Dashboard e nas Métricas de Risco)
tem_datas = bool(carteira["data_compra"].notna().any())
with st.sidebar:
    modo_curva = st.radio(
        "Curva da carteira",
        ["Pesos actuais (simulação)", "Compras reais (usa a Data de Compra)"],
        disabled=not tem_datas,
        help="Compras reais precisa da coluna 'Data de Compra' no CSV.",
    )
modo_real = tem_datas and modo_curva.startswith("Compras reais")

pesos_valor = carteira.dropna(subset=["simbolo"]).groupby("simbolo")["valor_atual"].sum()
with st.spinner("A descarregar o historial de preços..."):
    historico = buscar_historico(
        tuple(sorted(set(pesos_valor.index) | {simbolo_bench})), PERIODOS[rotulo_periodo]
    )

cobertos = [s for s in pesos_valor.index if s in historico.columns]
historico_ok = bool(cobertos) and simbolo_bench in historico.columns
pesos = pesos_valor[cobertos] / pesos_valor[cobertos].sum() if historico_ok else None
lotes = carteira.dropna(subset=["simbolo"])[["simbolo", "quantidade", "data_compra"]]


def retornos_do_modo(precos_df: pd.DataFrame) -> pd.Series:
    """Retornos diários pela curva escolhida (compras reais ou pesos actuais)."""
    if modo_real:
        return retornos_reais(precos_df, lotes)
    return retornos_carteira(precos_df, pesos)


texto_metodo = (
    "Usa as quantidades e as datas de compra reais; lotes sem data contam desde o início do período."
    if modo_real
    else "Aplica os pesos actuais (valor actual de cada posição), constantes, aos preços do período. "
    "Não é o histórico real das compras."
)
texto_cobertura = ""
if historico_ok:
    cobertura = pesos_valor[cobertos].sum() / carteira["valor_atual"].sum() * 100
    fora = [t for t, tp in zip(carteira["ticker"], carteira["tipo"]) if simbolo_yahoo(t, tp) not in cobertos]
    texto_cobertura = f"Cobre {cobertura:.0f} % do valor da carteira" + (
        f"; ficam de fora: {', '.join(fora)}." if fora else "."
    )

tab_dash, tab_aloc, tab_risco, tab_noticias = st.tabs(
    ["Dashboard Geral", "Alocação por Setor/País", "Métricas de Risco", "Notícias do Mercado"]
)

# ------------------------------------------------------------ Dashboard Geral
with tab_dash:
    investido = carteira["valor_investido"].sum()
    atual = carteira["valor_atual"].sum()
    pl_abs = atual - investido
    pl_pct = pl_abs / investido * 100 if investido else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Valor investido", f"{investido:,.2f} €")
    m2.metric("Valor actual", f"{atual:,.2f} €")
    m3.metric("P&L (€)", f"{pl_abs:+,.2f} €", delta=f"{pl_abs:+,.2f} €")
    m4.metric("P&L (%)", f"{pl_pct:+.2f} %", delta=f"{pl_pct:+.2f} %")
    st.caption(
        f"Preços obtidos às {hora:%H:%M} (atraso típico de cerca de 15 minutos; "
        "convertidos para euros). Posições sem cotação, como P2P, contam ao preço de compra."
    )

    mostrar = carteira[
        ["ticker", "tipo", "data_compra", "quantidade", "preco_medio", "preco_atual",
         "valor_investido", "valor_atual", "pl_abs", "pl_pct", "estado"]
    ].rename(columns=NOMES_BONITOS | {"preco_medio": "Preço Médio de Compra (€)"})
    estilo = (
        mostrar.style.map(cor_pl, subset=["P&L (€)", "P&L (%)"])
        .format(
            {
                "Data de Compra": lambda v: "—" if pd.isna(v) else f"{v:%d/%m/%Y}",
                "Quantidade": "{:,.4f}".format,
                "Preço Médio de Compra (€)": "{:,.2f}".format,
                "Preço Actual (€)": lambda v: "—" if pd.isna(v) else f"{v:,.2f}",
                "Valor Investido (€)": "{:,.2f}".format,
                "Valor Actual (€)": "{:,.2f}".format,
                "P&L (€)": "{:+,.2f}".format,
                "P&L (%)": "{:+.2f} %".format,
            }
        )
    )
    st.subheader("Posições")
    st.dataframe(estilo, width="stretch", hide_index=True)
    st.plotly_chart(grafico_pl(carteira), width="stretch")

    st.subheader(f"📈 Evolução ({rotulo_periodo})")
    if not cobertos:
        st.info("Não consegui obter o historial de nenhum activo da carteira.")
    elif simbolo_bench not in historico.columns:
        st.info(f"Não consegui obter o historial do benchmark {simbolo_bench}.")
    else:
        curva_modo = ((1 + retornos_do_modo(historico[cobertos])).cumprod() - 1) * 100
        par = alinhar_benchmark(curva_modo, historico[simbolo_bench])
        if par is None:
            st.info("O benchmark não tem datas em comum com a carteira.")
        else:
            curva_c, curva_b = par
            ret_c, ret_b = curva_c.iloc[-1], curva_b.iloc[-1]
            k1, k2, k3 = st.columns(3)
            k1.metric(f"Carteira ({rotulo_periodo})", f"{ret_c:+.2f} %")
            k2.metric(nome_bench, f"{ret_b:+.2f} %")
            k3.metric("Diferença", f"{ret_c - ret_b:+.2f} p.p.", delta=f"{ret_c - ret_b:+.2f} p.p.")
            if ret_c >= ret_b:
                st.success("A carteira bateu o benchmark neste período.")
            else:
                st.warning("A carteira ficou abaixo do benchmark neste período.")
            st.plotly_chart(grafico_evolucao(curva_c, curva_b, nome_bench, rotulo_periodo), width="stretch")
            st.caption(
                f"{texto_metodo} Dividendos incluídos. " + texto_cobertura
            )

# ------------------------------------------------------ Alocação Setor/País
with tab_aloc:
    valor_col = "valor_atual" if base_graficos == "Valor actual" else "valor_investido"
    st.subheader(f"Alocação ({base_graficos.lower()})")
    col_a, col_b = st.columns(2)
    col_a.plotly_chart(
        grafico_alocacao(carteira, "setor", "Por setor", tipo_grafico, valor_col),
        width="stretch",
    )
    col_b.plotly_chart(
        grafico_alocacao(carteira, "pais", "Por país", tipo_grafico, valor_col),
        width="stretch",
    )
    st.plotly_chart(
        grafico_alocacao(carteira, "tipo", "Por tipo de activo", tipo_grafico, valor_col),
        width="stretch",
    )

# ------------------------------------------------------------ Métricas de risco
with tab_risco:
    st.subheader(f"⚠️ Análise de risco ({rotulo_periodo})")
    taxa_pct = st.radio(
        "Taxa livre de risco (para o Sharpe Ratio)", [2, 3],
        format_func=lambda x: f"{x} %", horizontal=True,
    )
    if not historico_ok:
        st.info("Preciso do historial da carteira e do benchmark para calcular o risco.")
    else:
        datas_bench = historico[simbolo_bench].dropna().index
        ret_carteira = retornos_do_modo(historico[cobertos].ffill().reindex(datas_bench))
        ret_bench = historico[simbolo_bench].dropna().pct_change()
        r = metricas_risco(ret_carteira, ret_bench, taxa_pct / 100)
        if r is None:
            st.info("Há menos de 30 dias de preços em comum. É pouco para calcular o risco.")
        else:
            c, b = r["carteira"], r["benchmark"]
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Volatilidade anualizada", f"{c['volatilidade'] * 100:.2f} %",
                      help="Quanto o valor da carteira oscila ao longo de um ano. Quanto maior, mais instável.")
            r2.metric("Beta vs benchmark", f"{r['beta']:.2f}",
                      help="1 = move-se como o benchmark. Acima de 1 = amplifica os movimentos. "
                           "Abaixo de 1 = amortece. Negativo = move-se ao contrário.")
            r3.metric("Sharpe Ratio", f"{c['sharpe']:.2f}",
                      help=f"Retorno acima da taxa livre de risco ({taxa_pct} %) por cada unidade de "
                           "volatilidade. Acima de 1 é bom. Abaixo de 0 é pior que a taxa livre de risco.")
            r4.metric("Queda máxima", f"{c['queda_maxima'] * 100:.2f} %",
                      help="A maior descida desde um máximo até ao mínimo seguinte, no período escolhido.")

            tabela = pd.DataFrame(
                {
                    "Métrica": ["Volatilidade anualizada", "Beta vs benchmark", "Sharpe Ratio", "Queda máxima"],
                    "A minha carteira": [
                        f"{c['volatilidade'] * 100:.2f} %", f"{r['beta']:.2f}",
                        f"{c['sharpe']:.2f}", f"{c['queda_maxima'] * 100:.2f} %",
                    ],
                    nome_bench: [
                        f"{b['volatilidade'] * 100:.2f} %", "1.00",
                        f"{b['sharpe']:.2f}", f"{b['queda_maxima'] * 100:.2f} %",
                    ],
                }
            )
            st.dataframe(tabela, hide_index=True, width="stretch")
            st.plotly_chart(grafico_quedas(c["queda"], b["queda"], nome_bench), width="stretch")
            st.caption(
                f"Calculado com {r['dias']} dias de negociação do benchmark, retornos diários e "
                f"{DIAS_BOLSA} dias por ano. {texto_metodo} Mede o passado e não prevê o futuro. "
                + texto_cobertura
            )
            if r["dias"] < 120:
                st.warning(
                    "Período curto: com menos de 6 meses, a volatilidade anualizada e o Sharpe "
                    "são pouco fiáveis. Use-os só como indicação."
                )
            with st.expander("O que significa cada métrica"):
                st.markdown(
                    "- **Volatilidade anualizada:** desvio-padrão dos retornos diários multiplicado "
                    "pela raiz de 252. Mede a oscilação.\n"
                    "- **Beta:** covariância dos retornos da carteira com os do benchmark, dividida "
                    "pela variância do benchmark. Mede a sensibilidade ao mercado.\n"
                    "- **Sharpe Ratio:** (retorno anual médio menos a taxa livre de risco) a dividir "
                    "pela volatilidade anualizada.\n"
                    "- **Queda máxima:** maior perda percentual desde um pico até ao fundo seguinte."
                )

# ------------------------------------------------------------------ Notícias
with tab_noticias:
    simbolos_noticias = tuple(s for s in simbolos if not s.endswith("=X"))
    with st.spinner("A procurar notícias..."):
        noticias = buscar_noticias(simbolos_noticias)

    st.subheader("📰 Últimas 3 notícias da carteira")
    recentes = sorted(
        (n for n in noticias if not pd.isna(n["data"])),
        key=lambda n: n["data"],
        reverse=True,
    )[:3]
    if not recentes:
        st.info("Sem notícias disponíveis neste momento.")
    for n in recentes:
        st.caption(n["simbolo"])
        mostrar_noticia(n)

    st.subheader("Notícias por activo")
    for s in simbolos_noticias:
        do_simbolo = [n for n in noticias if n["simbolo"] == s]
        if do_simbolo:
            with st.expander(s, expanded=False):
                for n in do_simbolo:
                    mostrar_noticia(n)
