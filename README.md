# Portefólio de investimentos

Aplicação pessoal em Python (Streamlit) para analisar uma carteira de investimentos. Lê um ficheiro CSV, procura preços e notícias reais no Yahoo Finance e calcula o valor actual, o P&L, a alocação e o risco.

> Mede o passado e não prevê o futuro. Não é aconselhamento financeiro.

## O que faz

- **Dashboard Geral:** valor investido, valor actual, P&L (€ e %) por posição e global, e a evolução da carteira contra um benchmark (S&P 500, VWCE ou MSCI World).
- **Alocação por Setor/País:** gráficos interactivos (Pie Chart ou Treemap) por setor, país e tipo de activo.
- **Métricas de Risco:** volatilidade anualizada, beta, Sharpe Ratio (taxa livre de risco de 2 % ou 3 %) e queda máxima.
- **Notícias do Mercado:** as notícias mais recentes de cada activo, com título, fonte e ligação.
- **Período de análise:** 3 meses, 12 meses ou 5 anos.

## Instalação (Windows)

1. Instala o Python em python.org/downloads. No instalador, marca a caixa **Add python.exe to PATH** antes de clicar em *Install Now*.
2. Descarrega os ficheiros deste repositório para uma pasta, por exemplo `Documentos\portefolio`.
3. Abre essa pasta no Explorador de Ficheiros, clica na barra de endereço, escreve `cmd` e carrega em Enter.
4. Instala as bibliotecas (só uma vez):
   ```
   pip install -r requirements.txt
   ```
5. Arranca a aplicação:
   ```
   streamlit run app.py
   ```
   Se aparecer "streamlit não é reconhecido", usa `python -m streamlit run app.py`.
6. O browser abre em `localhost:8501`. Para fechar, carrega em Ctrl+C na janela preta.

**Mac:** usa o Terminal, `cd` para a pasta, `pip3 install -r requirements.txt` e `python3 -m streamlit run app.py`.

## Formato do CSV

| Coluna | Obrigatória | Exemplo |
|---|---|---|
| Ticker | sim | `AAPL`, `EDP.LS`, `VWCE.DE`, `BTC` |
| Quantidade | sim | `10` |
| Preço Médio de Compra | sim | `150.50` (em euros) |
| Tipo de Activo | sim | `Ações`, `ETF`, `Crypto` ou `P2P` |
| Setor | sim | `Tecnologia` |
| País | sim | `Estados Unidos` |
| Data de Compra | não | `15/03/2024` (dd/mm/aaaa) |

O ficheiro `portefolio_exemplo.csv` serve de modelo. Aceita vírgula ou ponto e vírgula como separador e vírgula como separador decimal.

### Símbolos do Yahoo Finance

O Yahoo exige o sufixo da bolsa nos títulos europeus: `.LS` (Lisboa), `.DE` (Xetra), `.AS` (Amesterdão), `.PA` (Paris). As criptomoedas dispensam o sufixo (`BTC` passa a `BTC-EUR`). O P2P não tem cotação e conta ao preço de compra.

## Curva da carteira

Na barra lateral escolhes entre dois modos:

- **Pesos actuais (simulação):** aplica os pesos de hoje aos preços do período. Responde à pergunta "como teria corrido com a carteira que tenho hoje".
- **Compras reais:** usa as quantidades e as datas de compra do CSV. Cada compra entra na carteira à data indicada. Precisa da coluna *Data de Compra*; os lotes sem data contam desde o início do período.

## Limites

- Os preços do Yahoo Finance têm cerca de 15 minutos de atraso e o serviço não é oficial. Pode falhar ou limitar pedidos.
- O Preço Médio de Compra é lido em euros. Os preços de mercado são convertidos para euros.
- Em períodos curtos (menos de 6 meses), a volatilidade anualizada e o Sharpe Ratio são pouco fiáveis.
- Activos sem historial no Yahoo ficam de fora das curvas e das métricas de risco. A aplicação indica quanto da carteira está coberto.

## Privacidade

Não envies para o GitHub o CSV com as tuas posições reais. O `.gitignore` bloqueia todos os ficheiros `.csv`, excepto `portefolio_exemplo.csv`.
