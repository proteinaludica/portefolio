# Portefólio de investimentos

Aplicação pessoal em Python (Streamlit) para analisar a tua carteira de investimentos. Lê um ficheiro CSV com as tuas operações, procura preços actuais no Yahoo Finance e calcula quanto valem os teus investimentos, quanto ganhaste ou perdeste e como se comparam com um índice de mercado.

> Mede o passado e não prevê o futuro. Não é aconselhamento financeiro nem consultoria fiscal.

## O que faz

- **Posições actuais:** quantidade, preço médio, valor actual e ganho ou perda não realizado, por activo.
- **Vendas realizadas:** ganho ou perda de cada venda, com as compras mais antigas consumidas primeiro.
- **Evolução:** valor da carteira em euros e rentabilidade ponderada pelo tempo, contra um índice de referência (S&P 500, VWCE ou MSCI World).
- **Rentabilidade anual pessoal:** calculada com base nas datas e nos valores das tuas operações. Precisa de pelo menos 90 dias de historial.
- **Alocação:** gráficos circulares ou treemaps por tipo de activo, setor e país.
- **Métricas de risco:** volatilidade, beta, Sharpe Ratio e queda máxima, nos últimos 12 meses.
- **Notícias:** as notícias mais recentes de cada activo.

## Formato do ficheiro CSV

Cada linha é uma operação: uma compra ou uma venda. Um activo com várias compras ocupa várias linhas.

| Coluna | Obrigatória | Exemplo | Notas |
|---|---|---|---|
| Ticker | Sim | `AAPL` | Símbolo no Yahoo Finance. Acções portuguesas levam `.LS`, por exemplo `EDP.LS`. |
| Operação | Não | `Compra` ou `Venda` | Se estiver vazia, conta como compra. |
| Quantidade | Sim | `10` | |
| Preço Unitário | Sim | `140,00` | Preço de uma unidade, na moeda indicada na coluna Moeda. |
| Data | Não | `15/03/2024` | Formato dd/mm/aaaa. Sem data, a operação conta desde o início do gráfico. |
| Comissões | Não | `2,00` | Na moeda indicada na coluna Moeda. |
| Tipo de Activo | Sim | `Ações` | Ações, ETF, Crypto ou P2P. |
| Setor | Sim | `Tecnologia` | |
| País | Sim | `Estados Unidos` | |
| Moeda | Não | `USD` | EUR, USD ou GBP. Se estiver vazia, conta como EUR. |

Os números podem ter vírgula ou ponto como separador decimal. O ficheiro pode ter ponto e vírgula ou vírgula como separador de colunas.

Preços e comissões são convertidos para euros com o câmbio do dia da operação. Se não houver câmbio para uma moeda, a linha fica de fora e a aplicação mostra o número da linha.

O P2P não tem cotação. Conta ao preço de compra.

## Instalação (Windows)

1. Instala o Python em python.org/downloads. No instalador, marca a caixa **Add python.exe to PATH** antes de carregar em *Install Now*.
2. Descarrega os ficheiros deste repositório para uma pasta, por exemplo `Documentos\portefolio`.
3. Abre essa pasta no Explorador de Ficheiros, carrega na barra de endereço, escreve `cmd` e carrega em Enter.
4. Instala as bibliotecas (só na primeira vez):
   ```
   pip install -r requirements.txt
   ```
5. Abre a aplicação:
   ```
   streamlit run app.py
   ```
6. O navegador abre sozinho. Para fechar, volta à janela preta e carrega em Ctrl + C.

## Instalação (Mac)

1. Instala o Python em python.org/downloads. No fim da instalação, abre a pasta "Python 3.x" e faz duplo clique em **Install Certificates.command**.
2. Cria uma pasta `Portefolio` em Documentos e copia para lá os ficheiros deste repositório.
3. Abre o Terminal, escreve `cd ` (com espaço), arrasta a pasta `Portefolio` para a janela e carrega em Enter.
4. Instala as bibliotecas (só na primeira vez):
   ```
   python3 -m pip install -r requirements.txt
   ```
5. Abre a aplicação:
   ```
   python3 -m streamlit run app.py
   ```
6. O Safari abre sozinho. Para fechar, volta ao Terminal e carrega em Ctrl + C.

## Usar os teus dados

1. Prepara um ficheiro CSV com as tuas operações, no formato descrito acima. O exemplo `portefolio_exemplo.csv` serve de modelo.
2. Na barra lateral da aplicação, carrega o ficheiro com o botão "Carregue o ficheiro CSV".
3. Para ver os preços mais recentes, carrega em "Actualizar preços e notícias".

## Limitações conhecidas

- Os preços vêm do Yahoo Finance, com um atraso típico de cerca de 15 minutos.
- A rentabilidade ponderada pelo tempo e as métricas de risco usam os pesos actuais da carteira.
- As vendas usam a regra das compras mais antigas primeiro. É uma estimativa e não substitui o apuramento para o IRS.
- Se o Yahoo Finance bloquear os pedidos durante algum tempo, a aplicação mostra os valores ao preço de compra.
