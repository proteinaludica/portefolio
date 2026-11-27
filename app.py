"""Análise de portefólio de investimentos (Streamlit + Plotly + yfinance).

Como correr:  streamlit run app.py

O ficheiro CSV tem uma linha por operação (compra ou venda). As vendas
consomem primeiro as compras mais antigas, como na regra fiscal portuguesa.
"""

import io
import math
import unicodedata
from collections import deque
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
    "preco": [
        "preco unitario",
        "preco medio de compra",
        "preco medio",
        "preco de compra",
        "preco",
        "pmc",
    ],
    "tipo": ["tipo de activo", "tipo de ativo", "tipo", "classe"],
    "setor": ["setor", "sector"],
    "pais": ["pais", "country"],
}
# Colunas que podem faltar (o CSV antigo continua a funcionar).
OPCIONAIS = {
    "operacao": ["operacao", "tipo de operacao", "movimento"],
    "data": ["data", "data de compra", "data da operacao", "data de operacao"],
    "comissoes": ["comissoes", "comissao", "custos", "taxas"],
    "moeda": ["moeda", "moeda da operacao", "currency", "divisa"],
}
NOMES_BONITOS = {
    "ticker": "Ticker",
    "quantidade": "Quantidade",
    "preco": "Preço Unitário",
    "preco_medio": "Preço Médio de Compra",
    "tipo": "Tipo de Activo",
    "setor": "Setor",
    "pais": "País",
    "operacao": "Operação",
    "data": "Data",
    "comissoes": "Comissões",
    "moeda": "Moeda",
    "preco_atual": "Preço Actual (€)",
    "valor_investido": "Valor Investido (€)",
    "valor_atual": "Valor Actual (€)",
    "pl_abs": "P&L (€)",
    "pl_pct": "P&L (%)",
    "estado": "Estado do preço",
}
MOEDAS_SIMBOLO = {"€": "EUR", "$": "USD", "£": "GBP"}
FORMATOS_DATA = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y"]


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
    if texto == "":
        return float("nan")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return float("nan")


def para_data(valor):
    """Converte '15/03/2024', '15-03-2024' ou '2024-03-15' em data.

    Devolve None se a célula estiver vazia e NaT se a data for inválida.
    """
    if pd.isna(valor) or str(valor).strip() == "":
        return None
    texto = str(valor).strip().split(" ")[0]
    for formato in FORMATOS_DATA:
        try:
            return pd.Timestamp(datetime.strptime(texto, formato))
        except ValueError:
            continue
    return pd.NaT


def para_operacao(valor):
    texto = normalizar(valor) if not pd.isna(valor) else ""
    if texto in ("", "compra", "c", "buy", "compras"):
        return "Compra"
    if texto in ("venda", "v", "sell", "vendas"):
        return "Venda"
    return None


def ler_csv(ficheiro) -> pd.DataFrame:
    """Lê o CSV de operações (vírgula ou ponto e vírgula; UTF-8 ou Excel antigo)."""
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
        for interno, variantes in (COLUNAS | OPCIONAIS).items():
            if chave in variantes and interno not in mapa.values():
                mapa[coluna] = interno
    df = df.rename(columns=mapa)

    em_falta = [NOMES_BONITOS[c] for c in COLUNAS if c not in df.columns]
    if em_falta:
        raise ValueError("Faltam colunas no ficheiro: " + ", ".join(em_falta))
    for c in OPCIONAIS:
        if c not in df.columns:
            df[c] = None

    df = df[list(COLUNAS) + list(OPCIONAIS)].copy()
    df["linha"] = df.index + 2  # número da linha no ficheiro (1 = cabeçalho)
    df["quantidade"] = df["quantidade"].map(para_numero)
    df["preco"] = df["preco"].map(para_numero)
    df["comissoes"] = df["comissoes"].map(para_numero).fillna(0.0)
    df["operacao"] = df["operacao"].map(para_operacao)
    df["moeda"] = (
        df["moeda"].fillna("").astype(str).str.strip().str.upper()
        .replace("", "EUR").replace(MOEDAS_SIMBOLO)
    )
    texto_data = df["data"].fillna("").astype(str).str.strip()
    df["data"] = pd.to_datetime(texto_data.map(lambda t: para_data(t) or pd.NaT))
    data_invalida = (texto_data != "") & df["data"].isna()
    for c in ("ticker", "tipo", "setor", "pais"):
        df[c] = df[c].fillna("Sem indicação").str.strip()

    invalidas = (
        df["quantidade"].isna()
        | (df["quantidade"] <= 0)
        | df["preco"].isna()
        | df["operacao"].isna()
        | data_invalida
    )
    if invalidas.any():
        linhas = ", ".join(str(n) for n in df.loc[invalidas, "linha"])
        st.warning(
            f"{int(invalidas.sum())} linha(s) ignorada(s) por terem quantidade, preço, "
            f"operação ou data inválidos (linhas {linhas} do ficheiro)."
        )
        df = df[~invalidas]
    df = converter_para_euros(df)
    return df.reset_index(drop=True)


def converter_para_euros(df: pd.DataFrame) -> pd.DataFrame:
    """Passa o preço e as comissões de cada operação para euros.

    Usa o câmbio do dia da operação (ou o mais recente, se não houver data).
    As operações cuja moeda não tem câmbio ficam de fora, com um aviso.
    """
    df = df.copy()
    sem_cambio = []
    for i, linha in df[df["moeda"] != "EUR"].iterrows():
        data = "" if pd.isna(linha["data"]) else linha["data"].strftime("%Y-%m-%d")
        taxa = buscar_cambio(linha["moeda"], data)
        if taxa is None:
            sem_cambio.append(i)
            continue
        df.at[i, "preco"] = linha["preco"] * taxa
        df.at[i, "comissoes"] = linha["comissoes"] * taxa
    if sem_cambio:
        st.error(
            "Sem câmbio para converter para euros nas linhas "
            + ", ".join(str(n) for n in df.loc[sem_cambio, "linha"])
            + ". Essas operações ficam de fora. Confirme a moeda (EUR, USD ou GBP)."
        )
        df = df.drop(index=sem_cambio)
    return df


@st.cache_data(ttl=86400, show_spinner=False)
def buscar_cambio(moeda: str, data: str) -> float | None:
    """Quantos euros vale 1 unidade da moeda, no último fecho até à data (aaaa-mm-dd).

    Sem data, devolve o câmbio mais recente. Devolve None se o Yahoo não responder.
    """
    try:
        simbolo = f"{moeda}EUR=X"
        if data:
            dia = pd.Timestamp(data)
            hist = yf.Ticker(simbolo).history(start=dia - pd.Timedelta(days=10), end=dia + pd.Timedelta(days=1))
            serie = _limpar_serie(hist["Close"])
            serie = serie[serie.index <= dia]
        else:
            serie = _limpar_serie(yf.Ticker(simbolo).history(period="5d")["Close"])
        return float(serie.iloc[-1])
    except Exception:
        return None


# ------------------------------------------------------- compras e vendas
def processar_operacoes(ops: pd.DataFrame):
    """Aplica as compras e as vendas a cada activo pela ordem das datas.

    As vendas consomem primeiro as compras mais antigas. As comissões somam-se
    ao custo das compras e descontam-se no valor recebido nas vendas.
    Devolve (posições actuais, vendas realizadas, avisos).
    """
    posicoes, vendas, avisos = [], [], []
    ordenado = ops.assign(_venda=(ops["operacao"] == "Venda").astype(int))
    ordenado = ordenado.sort_values(["data", "_venda", "linha"], na_position="first", kind="stable")

    for ticker, g in ordenado.groupby("ticker", sort=False):
        lotes = deque()  # cada lote: [quantidade, custo por unidade]
        for _, op in g.iterrows():
            q, p, fee = op["quantidade"], op["preco"], op["comissoes"]
            if op["operacao"] == "Compra":
                lotes.append([q, (q * p + fee) / q])
                continue
            restante, custo = q, 0.0
            while restante > 1e-12 and lotes:
                usar = min(restante, lotes[0][0])
                custo += usar * lotes[0][1]
                lotes[0][0] -= usar
                restante -= usar
                if lotes[0][0] <= 1e-12:
                    lotes.popleft()
            vendida = q - restante
            if restante > 1e-9:
                avisos.append(
                    f"{ticker}: a venda da linha {op['linha']} é maior do que a quantidade "
                    f"detida. Contei só {vendida:,.4f} unidades."
                )
            if vendida <= 0:
                continue
            receita = vendida * p - fee
            vendas.append(
                {
                    "Ticker": ticker,
                    "Data": op["data"],
                    "Quantidade": vendida,
                    "Valor Recebido (€)": receita,
                    "Custo de Aquisição (€)": custo,
                    "Ganho Realizado (€)": receita - custo,
                }
            )

        quantidade = sum(l[0] for l in lotes)
        if quantidade > 1e-9:
            custo_total = sum(l[0] * l[1] for l in lotes)
            ultima = g.iloc[-1]
            posicoes.append(
                {
                    "ticker": ticker,
                    "tipo": ultima["tipo"],
                    "setor": ultima["setor"],
                    "pais": ultima["pais"],
                    "quantidade": quantidade,
                    "preco_medio": custo_total / quantidade,
                    "valor_investido": custo_total,
                }
            )

    carteira = pd.DataFrame(
        posicoes,
        columns=["ticker", "tipo", "setor", "pais", "quantidade", "preco_medio", "valor_investido"],
    )
    vendas = pd.DataFrame(
        vendas,
        columns=["Ticker", "Data", "Quantidade", "Valor Recebido (€)",
                 "Custo de Aquisição (€)", "Ganho Realizado (€)"],
    )
    return carteira, vendas, avisos


def fluxo_operacao(op) -> float:
    """Dinheiro que entra na carteira (compra, positivo) ou sai (venda, negativo)."""
    if op["operacao"] == "Compra":
        return op["quantidade"] * op["preco"] + op["comissoes"]
    return -(op["quantidade"] * op["preco"] - op["comissoes"])


def tir_anual(ops: pd.DataFrame, valor_final: float, hoje: pd.Timestamp, inicio: pd.Timestamp):
    """Rentabilidade anual ponderada pelo dinheiro (taxa interna de rentabilidade).

    Considera cada compra como dinheiro investido, cada venda como dinheiro
    recebido e o valor actual da carteira como se fosse vendida hoje.
    Devolve None com menos de 90 dias de historial ou sem solução.
    """
    fluxos = [
        (inicio if pd.isna(op["data"]) else op["data"], -fluxo_operacao(op))
        for _, op in ops.iterrows()
    ]
    fluxos.append((hoje, valor_final))
    t0 = min(d for d, _ in fluxos)
    if (hoje - t0).days < 90:
        return None
    pares = [((d - t0).days / 365.25, a) for d, a in fluxos]

    def valor_presente(taxa):
        return sum(a / (1 + taxa) ** t for t, a in pares)

    baixo, alto = -0.99, 10.0
    f_baixo, f_alto = valor_presente(baixo), valor_presente(alto)
    if f_baixo * f_alto > 0:
        return None
    for _ in range(200):
        meio = (baixo + alto) / 2
        f_meio = valor_presente(meio)
        if f_baixo * f_meio <= 0:
            alto = meio
        else:
            baixo, f_baixo = meio, f_meio
    return (baixo + alto) / 2


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
def buscar_historico(simbolos: tuple, inicio: str) -> pd.DataFrame:
    """Preços de fecho diários desde a data de início, em euros.

    Uma coluna por símbolo. Os símbolos sem dados ficam de fora. Os preços
    estão ajustados a dividendos e desdobramentos (retorno total).
    """
    series = {}
    taxas = {}
    for s in simbolos:
        try:
            ticker = yf.Ticker(s)
            hist = _limpar_serie(ticker.history(start=inicio, auto_adjust=True)["Close"])
            moeda = ticker.fast_info["currency"]
            if hist.empty:
                continue
            if moeda in ("GBp", "GBX"):
                hist, moeda = hist / 100, "GBP"
            if moeda != "EUR":
                if moeda not in taxas:
                    cambio = yf.Ticker(f"{moeda}EUR=X").history(start=inicio)["Close"]
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


def evolucao_real(ops: pd.DataFrame, historico: pd.DataFrame, datas: pd.DatetimeIndex):
    """Valor diário da carteira real, dinheiro investido e retornos diários.

    Cada activo só entra na carteira no dia da compra e sai no dia da venda.
    Uma operação feita num dia sem bolsa conta no dia de bolsa seguinte.
    Os activos sem cotação (P2P ou símbolo não encontrado) contam ao custo.
    O retorno diário retira o efeito do dinheiro que entra ou sai
    (rentabilidade ponderada pelo tempo).
    """
    n = len(datas)
    valor = pd.Series(0.0, index=datas)
    compras_dia = pd.Series(0.0, index=datas)  # dinheiro gasto em compras
    vendas_dia = pd.Series(0.0, index=datas)   # dinheiro recebido em vendas

    for _, g in ops.groupby("ticker"):
        simbolo = g["simbolo"].iloc[0]
        posicao = g["data"].map(
            lambda d: 0 if pd.isna(d) else min(int(datas.searchsorted(d)), n - 1)
        )
        sinal = g["operacao"].map({"Compra": 1.0, "Venda": -1.0})

        delta = (g["quantidade"] * sinal).groupby(posicao).sum()
        quantidade = pd.Series(0.0, index=range(n))
        quantidade.loc[delta.index] = delta.values
        quantidade = quantidade.cumsum().clip(lower=0)
        quantidade.index = datas

        if simbolo and simbolo in historico.columns:
            preco = historico[simbolo].reindex(datas).ffill().bfill()
        else:
            compras = g[g["operacao"] == "Compra"]
            unidades = compras["quantidade"].sum()
            custo = (compras["quantidade"] * compras["preco"] + compras["comissoes"]).sum()
            preco = pd.Series(custo / unidades if unidades else 0.0, index=datas)
        valor += quantidade * preco

        f = g.apply(fluxo_operacao, axis=1)
        for serie, parte in ((compras_dia, f.clip(lower=0)), (vendas_dia, -f.clip(upper=0))):
            soma = parte.groupby(posicao).sum()
            serie.iloc[soma.index] = serie.iloc[soma.index].values + soma.values

    # As compras contam no início do dia e as vendas no fim do dia. Assim, o
    # retorno diário nunca fica abaixo de -100 %.
    base = valor.shift(1).fillna(0.0) + compras_dia
    retornos = ((valor + vendas_dia) / base - 1).where(base > 0, 0.0).fillna(0.0)
    # O primeiro dia serve de ponto de partida. As operações sem data entram ao
    # preço de mercado desse dia, como na versão anterior da aplicação.
    if n:
        retornos.iloc[0] = 0.0
    return valor, compras_dia - vendas_dia, retornos


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


def grafico_evolucao(carteira_pct: pd.Series, bench_pct: pd.Series, nome_bench: str, titulo: str):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=carteira_pct.index, y=carteira_pct, name="A minha carteira",
                             mode="lines", line=dict(width=3, color="#1f77b4")))
    fig.add_trace(go.Scatter(x=bench_pct.index, y=bench_pct, name=nome_bench,
                             mode="lines", line=dict(width=2, color="#ff7f0e", dash="dot")))
    fig.add_hline(y=0, line_width=1, line_color="gray")
    fig.update_traces(hovertemplate="%{y:+.2f} %")
    fig.update_layout(
        title=titulo,
        hovermode="x unified",
        yaxis=dict(ticksuffix=" %", title="Retorno acumulado"),
        xaxis_title="",
        legend=dict(orientation="h", y=-0.15),
        margin=dict(t=60, l=10, r=10, b=10),
    )
    return fig


def grafico_valor(valor: pd.Series, investido: pd.Series):
    """Valor da carteira em euros contra o dinheiro líquido investido."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=valor.index, y=valor, name="Valor da carteira",
                             mode="lines", line=dict(width=3, color="#1f77b4"),
                             fill="tozeroy", fillcolor="rgba(31,119,180,0.08)"))
    fig.add_trace(go.Scatter(x=investido.index, y=investido, name="Dinheiro investido (líquido)",
                             mode="lines", line=dict(width=2, color="#555555", shape="hv", dash="dash")))
    fig.update_traces(hovertemplate="%{y:,.2f} €")
    fig.update_layout(
        title="Valor da carteira em euros",
        hovermode="x unified",
        yaxis=dict(ticksuffix=" €", title=""),
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


def mostrar_vendas(vendas: pd.DataFrame):
    estilo = vendas.style.map(cor_pl, subset=["Ganho Realizado (€)"]).format(
        {
            "Data": lambda d: "—" if pd.isna(d) else f"{d:%d/%m/%Y}",
            "Quantidade": "{:,.4f}".format,
            "Valor Recebido (€)": "{:,.2f}".format,
            "Custo de Aquisição (€)": "{:,.2f}".format,
            "Ganho Realizado (€)": "{:+,.2f}".format,
        }
    )
    st.dataframe(estilo, width="stretch", hide_index=True)
    st.caption(
        "As vendas consomem primeiro as compras mais antigas, como na regra fiscal "
        "portuguesa. O custo inclui as comissões de compra e o valor recebido já desconta "
        "as comissões de venda. É uma estimativa: não substitui o apuramento para o IRS."
    )


# ---------------------------------------------------------------- interface
st.title("📊 O meu portefólio de investimentos")

with st.sidebar:
    st.header("Dados")
    ficheiro = st.file_uploader("Carregue o ficheiro CSV", type=["csv"])
    usar_exemplo = st.checkbox("Usar dados de exemplo", disabled=not EXEMPLO.exists())
    tipo_grafico = st.radio("Tipo de gráfico", ["Pie Chart", "Treemap"])
    base_graficos = st.radio("Gráficos de alocação por", ["Valor actual", "Valor investido"])
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
        "Uma linha por operação. Colunas necessárias: Ticker, Quantidade, Preço Unitário, "
        "Tipo de Activo, Setor, País. Colunas opcionais: Operação (Compra ou Venda), "
        "Data (dd/mm/aaaa) e Comissões. Os preços e as comissões são lidos em euros."
    )

if ficheiro is None and not usar_exemplo:
    st.info("Carregue um ficheiro CSV na barra lateral para começar.")
    st.stop()

try:
    if ficheiro is not None:
        operacoes = ler_csv(ficheiro)
    else:
        operacoes = ler_csv(EXEMPLO.read_bytes())
except Exception as erro:
    st.error(f"Não consegui ler o ficheiro. {erro}")
    st.stop()

if operacoes.empty:
    st.error("O ficheiro não tem linhas válidas.")
    st.stop()

carteira, vendas, avisos = processar_operacoes(operacoes)
for aviso in avisos:
    st.warning(aviso)
operacoes["simbolo"] = [simbolo_yahoo(t, tp) for t, tp in zip(operacoes["ticker"], operacoes["tipo"])]
ganho_realizado = vendas["Ganho Realizado (€)"].sum()

if carteira.empty:
    st.warning("Todas as posições do ficheiro já foram vendidas. Fica só o ganho realizado.")
    st.metric("Ganho realizado", f"{ganho_realizado:+,.2f} €")
    mostrar_vendas(vendas)
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

# Datas: a curva começa na primeira operação; as operações sem data contam
# como feitas há 12 meses. As métricas de risco usam sempre os últimos 12 meses.
hoje = pd.Timestamp.today().normalize()
inicio_12m = hoje - pd.Timedelta(days=365)
datas_ops = operacoes["data"].dropna()
if datas_ops.empty:
    inicio_curva = inicio_12m
elif operacoes["data"].isna().any():
    inicio_curva = min(datas_ops.min(), inicio_12m)
else:
    inicio_curva = datas_ops.min()
inicio_download = min(inicio_curva, inicio_12m) - pd.Timedelta(days=10)

simbolos_hist = {s for s in operacoes["simbolo"] if isinstance(s, str) and s} | {simbolo_bench}
with st.spinner("A descarregar o historial de preços..."):
    historico = buscar_historico(tuple(sorted(simbolos_hist)), f"{inicio_download:%Y-%m-%d}")

if historico.empty:
    datas_curva = pd.bdate_range(inicio_curva, hoje)
else:
    datas_curva = historico.index[historico.index >= inicio_curva]
    if len(datas_curva) == 0:
        datas_curva = pd.bdate_range(inicio_curva, hoje)
valor_dia, fluxos_dia, retornos_dia = evolucao_real(operacoes, historico, datas_curva)

# Totais
investido = carteira["valor_investido"].sum()
atual = carteira["valor_atual"].sum()
pl_abs = atual - investido
pl_pct = pl_abs / investido * 100 if investido else 0.0
tir = tir_anual(operacoes, atual, hoje, inicio_curva)
ativo = valor_dia[valor_dia > 0]
twr_total = None
if not ativo.empty:
    twr_total = ((1 + retornos_dia.loc[ativo.index[0]:]).prod() - 1) * 100

# Pesos actuais e historial dos últimos 12 meses (Métricas de Risco)
hist_12m = historico[historico.index >= inicio_12m].dropna(axis=1, how="all") if not historico.empty else historico
pesos_valor = carteira.dropna(subset=["simbolo"]).groupby("simbolo")["valor_atual"].sum()
cobertos = [s for s in pesos_valor.index if s in hist_12m.columns]
historico_ok = bool(cobertos) and simbolo_bench in hist_12m.columns
pesos = pesos_valor[cobertos] / pesos_valor[cobertos].sum() if historico_ok else None
texto_cobertura = ""
if historico_ok:
    cobertura = pesos_valor[cobertos].sum() / atual * 100
    fora = [t for t, tp in zip(carteira["ticker"], carteira["tipo"]) if simbolo_yahoo(t, tp) not in cobertos]
    texto_cobertura = f"Cobre {cobertura:.0f} % do valor da carteira" + (
        f"; ficam de fora: {', '.join(fora)}." if fora else "."
    )

tab_dash, tab_aloc, tab_risco, tab_noticias = st.tabs(
    ["Dashboard Geral", "Alocação por Setor/País", "Métricas de Risco", "Notícias do Mercado"]
)

# ------------------------------------------------------------ Dashboard Geral
with tab_dash:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Valor investido", f"{investido:,.2f} €",
              help="Custo das unidades que ainda tens, com as comissões de compra.")
    m2.metric("Valor actual", f"{atual:,.2f} €")
    m3.metric("Ganho não realizado (€)", f"{pl_abs:+,.2f} €", delta=f"{pl_abs:+,.2f} €",
              help="Ganho ou perda das posições que ainda tens, ao preço de hoje.")
    m4.metric("Ganho não realizado (%)", f"{pl_pct:+.2f} %", delta=f"{pl_pct:+.2f} %")

    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Ganho realizado", f"{ganho_realizado:+,.2f} €",
              help="Ganho ou perda das vendas já feitas, depois das comissões.")
    n2.metric("Ganho total", f"{pl_abs + ganho_realizado:+,.2f} €",
              help="Ganho não realizado mais ganho realizado.")
    n3.metric("Rentabilidade anual pessoal", "—" if tir is None else f"{tir * 100:+.2f} % / ano",
              help="Rentabilidade ponderada pelo dinheiro (taxa interna de rentabilidade). "
                   "Tem em conta quando e quanto investiste. Precisa de pelo menos 90 dias "
                   "de historial.")
    n4.metric("Rentabilidade ponderada pelo tempo", "—" if twr_total is None else f"{twr_total:+.2f} %",
              help="Rentabilidade acumulada desde a primeira operação, sem o efeito dos "
                   "reforços e das vendas. É a medida que se compara com o benchmark.")
    st.caption(
        f"Preços obtidos às {hora:%H:%M} (atraso típico de cerca de 15 minutos; "
        "convertidos para euros). Posições sem cotação, como P2P, contam ao preço de compra."
    )

    mostrar = carteira[
        ["ticker", "tipo", "quantidade", "preco_medio", "preco_atual",
         "valor_investido", "valor_atual", "pl_abs", "pl_pct", "estado"]
    ].rename(columns=NOMES_BONITOS | {"preco_medio": "Preço Médio de Compra (€)"})
    estilo = (
        mostrar.style.map(cor_pl, subset=["P&L (€)", "P&L (%)"])
        .format(
            {
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
    st.subheader("Posições actuais")
    st.dataframe(estilo, width="stretch", hide_index=True)
    st.caption("O preço médio de compra é o das unidades que ainda tens, depois das vendas.")
    st.plotly_chart(grafico_pl(carteira), width="stretch")

    if not vendas.empty:
        with st.expander(f"Vendas realizadas ({len(vendas)})"):
            mostrar_vendas(vendas)

    st.subheader("📈 Evolução desde a primeira operação")
    if ativo.empty:
        st.info("Não há dados suficientes para desenhar a evolução da carteira.")
    else:
        inicio_real = ativo.index[0]
        investido_acum = fluxos_dia.cumsum()
        st.plotly_chart(
            grafico_valor(valor_dia.loc[inicio_real:], investido_acum.loc[inicio_real:]),
            width="stretch",
        )
        st.caption(
            "A linha a tracejado sobe em cada compra e desce em cada venda. A distância entre "
            "as duas linhas é o ganho ou a perda acumulados."
        )
        curva_twr = ((1 + retornos_dia.loc[inicio_real:]).cumprod() - 1) * 100
        if simbolo_bench not in historico.columns:
            st.info(f"Não consegui obter o historial do benchmark {simbolo_bench}.")
        else:
            par = alinhar_benchmark(curva_twr, historico[simbolo_bench])
            if par is None:
                st.info("O benchmark não tem datas em comum com a carteira.")
            else:
                curva_c, curva_b = par
                ret_c, ret_b = curva_c.iloc[-1], curva_b.iloc[-1]
                k1, k2, k3 = st.columns(3)
                k1.metric("Carteira", f"{ret_c:+.2f} %")
                k2.metric(nome_bench, f"{ret_b:+.2f} %")
                k3.metric("Diferença", f"{ret_c - ret_b:+.2f} p.p.", delta=f"{ret_c - ret_b:+.2f} p.p.")
                if ret_c >= ret_b:
                    st.success("A carteira bateu o benchmark neste período.")
                else:
                    st.warning("A carteira ficou abaixo do benchmark neste período.")
                st.plotly_chart(
                    grafico_evolucao(
                        curva_c, curva_b, nome_bench,
                        f"Rentabilidade ponderada pelo tempo desde {inicio_real:%d/%m/%Y} (em euros)",
                    ),
                    width="stretch",
                )
                st.caption(
                    "Usa as datas reais das operações e retira o efeito do dinheiro que entra "
                    "e sai. Assim, a comparação com o benchmark é justa. Os preços incluem "
                    "dividendos. Os activos sem cotação (P2P) contam ao custo, com rentabilidade "
                    "zero. As operações sem data contam como feitas no primeiro dia do gráfico, ao preço desse dia."
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
    st.subheader("⚠️ Análise de risco (últimos 12 meses)")
    taxa_pct = st.radio(
        "Taxa livre de risco (para o Sharpe Ratio)", [2, 3],
        format_func=lambda x: f"{x} %", horizontal=True,
    )
    if not historico_ok:
        st.info("Preciso do historial da carteira e do benchmark para calcular o risco.")
    else:
        datas_bench = hist_12m[simbolo_bench].dropna().index
        ret_carteira = retornos_carteira(hist_12m[cobertos].ffill().reindex(datas_bench), pesos)
        ret_bench = hist_12m[simbolo_bench].dropna().pct_change()
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
                      help="A maior descida desde um máximo até ao mínimo seguinte, no último ano.")

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
                f"{DIAS_BOLSA} dias por ano, com os pesos actuais constantes. Mede o passado e não "
                "prevê o futuro. " + texto_cobertura
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
