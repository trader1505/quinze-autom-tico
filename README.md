# LAPS Bot - VPS (Futuros)

Implementacao inicial de um bot para operar futuros com regras fixas:

- timeframe **15m**
- medias moveis exponenciais (EMA) **12 e 26**
- entrada com **1% do saldo livre de futuros (margem usada)**
- alvo de fechamento no **ROI +100%**
- rebalanceamento de capital **80% spot / 20% futuros**
- protecao por topup de margem em queda
- logica de reforco **3x** apos confirmacao de tendencia
- suporte a multiplas operacoes simultaneas por simbolo (`LAPS_MAX_POSITIONS`)

> Aviso tecnico: nenhum sistema de trading garante "zero erro". Este codigo foi estruturado com validacoes, logs e controles defensivos, mas voce deve testar primeiro em sandbox e usar monitoramento continuo.

## Estrategia implementada

1. O bot calcula tendencia no M15 com EMA(12) e EMA(26):
   - EMA12 > EMA26 => tendencia LONG
   - EMA12 < EMA26 => tendencia SHORT
2. Se nao houver posicao aberta, abre imediatamente uma operacao na direcao atual.
3. Tamanho da entrada:
   - usa **1% do saldo livre de futuros**
   - calcula notional com base em alavancagem (`LAPS_LEVERAGE`)
   - tenta executar margem com valor **exato**
   - se o simbolo principal nao suporta exato por regra de lote/notional, escaneia simbolos de fallback definidos em `LAPS_SYMBOLS`.
4. Quando ROI da posicao atingir **+100%**, fecha 100% da posicao.
5. Apos fechar no TP, executa rebalanceamento para manter **80/20 (spot/futuros)**.
6. Se ROI cair ate **-60%**, transfere **20% do spot livre** para futuros (maximo de 4 topups).
7. Regra 3x:
   - exige cruzamento EMA contra a direcao da entrada (alerta)
   - depois exige novo cruzamento EMA voltando para a direcao original
   - somente apos essa sequencia de cruzamentos executa reforco de **3x** sobre a entrada inicial
   - apos reforco, quando ROI voltar para >= 0, fecha 100% para liberar margem

> O bot nao faz rebalance continuo por tempo/ciclo. Movimentacao de capital ocorre apenas em TP e topup de emergencia.

## Estrutura

```text
.
├── run_bot.py
├── run_panel.py
├── requirements.txt
├── .env.example
└── src
    ├── laps_bot
    │   ├── bot.py
    │   ├── config.py
    │   ├── exchange.py
    │   ├── indicators.py
    │   ├── logger.py
    │   ├── models.py
    │   ├── rebalance.py
    │   ├── risk.py
    │   ├── strategy.py
    │   └── telemetry.py
    └── laps_panel
        ├── server.py
        └── static/index.html
```

## Instalar no VPS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edite o `.env` com sua API:

- `LAPS_API_KEY`
- `LAPS_API_SECRET`

## Rodar

Sandbox (recomendado primeiro):

```bash
export LAPS_SANDBOX=true
python run_bot.py
```

Live:

```bash
export LAPS_SANDBOX=false
python run_bot.py
```

Painel web (preto/dourado estilo Bloomberg):

```bash
python run_panel.py
```

Depois acesse:

`http://IP_DO_VPS:8080`

## Principais variaveis

- `LAPS_SYMBOLS`: simbolo principal e fallback (ex.: `BTC/USDT:USDT,ETH/USDT:USDT`)
- `LAPS_MAX_POSITIONS`: quantidade maxima de operacoes simultaneas (nao pode ultrapassar o numero de simbolos em `LAPS_SYMBOLS`)
- `LAPS_BALANCE_RISK_PCT`: `%` da entrada inicial (default `1`)
- `LAPS_LEVERAGE`: alavancagem usada para transformar alvo de margem em notional (default `125`)
- `LAPS_TARGET_ROI_PCT`: alvo de fechamento (default `100`)
- `LAPS_ADD_MARGIN_TRIGGER_PCT`: gatilho topup (default `-60`)
- `LAPS_MARGIN_RATIO_TRIGGER_PCT`: gatilho minimo de margem (% da conta/posicao) para permitir topup (default `60`)
- `LAPS_REINFORCEMENT_MULTIPLIER`: multiplicador do reforco (default `3`)
- `LAPS_SPOT_TARGET_PCT` / `LAPS_FUTURES_TARGET_PCT`: alvo 80/20
- `LAPS_MARGIN_TOPUP_PCT`: percentual transferido no topup (default `20`)
- `LAPS_MAX_TOPUPS`: quantidade de "vidas" (default `4`)
- `LAPS_TELEMETRY_DIR`: pasta de eventos/estado para painel (default `runtime`)
- `LAPS_PANEL_HOST`: host do painel (default `0.0.0.0`)
- `LAPS_PANEL_PORT`: porta do painel (default `8080`)

## Painel Bloomberg Pro (preto/dourado)

O painel mostra em tempo real:

- status operacional do bot
- contagem de operacoes abertas + split long/short
- lucro fechado total (TP + recuperacoes 3x fechadas)
- TPs fechados e valor acumulado
- recuperacoes 3x em andamento e concluidas
- volume de topups de margem
- status atual do rebalance spot/futuros e alvo 80/20
- saldo total e saldo livre de spot/futuros em USDT
- tabela detalhada de posicoes ativas
- timeline completa de funcoes executadas

### Sons no painel

- `tp_hit`: som de TP
- `reinforcement_recovered_close`: som de 3x recuperado
- `cash_rebalance`: som de cash (moeda caindo estridente)

> O navegador exige clique do usuario para liberar audio. Clique em **Ativar som** no canto superior do painel.

## Operacao segura (obrigatorio)

1. Rode em sandbox por varios ciclos completos (entrada, fechamento, rebalance e topup).
2. Ative monitoramento de processo no VPS (systemd, supervisor ou pm2).
3. Use chave de API sem permissao de saque.
4. Defina alertas externos de erro e latencia.
5. Comece com saldo minimo de teste antes de escalar.
6. Se aparecer log de "No symbol can place an order with exactly the configured margin target", ajuste os simbolos de fallback ou o saldo/alavancagem.
