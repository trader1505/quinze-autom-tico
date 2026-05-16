# LAPS Bot - VPS (Futuros)

Implementacao inicial de um bot para operar futuros com regras fixas:

- timeframe **15m**
- medias moveis simples **12 e 26**
- entrada com **1% do saldo livre de futuros**
- alvo de fechamento no **ROI +100%**
- rebalanceamento de capital **80% spot / 20% futuros**
- protecao por topup de margem em queda
- logica de reforco **3x** apos confirmacao de tendencia
- versao atual com **1 operacao simultanea** (base para subir para 30)

> Aviso tecnico: nenhum sistema de trading garante "zero erro". Este codigo foi estruturado com validacoes, logs e controles defensivos, mas voce deve testar primeiro em sandbox e usar monitoramento continuo.

## Estrategia implementada

1. O bot calcula tendencia no M15 com SMA(12) e SMA(26):
   - SMA12 > SMA26 => tendencia LONG
   - SMA12 < SMA26 => tendencia SHORT
2. Se nao houver posicao aberta, abre imediatamente uma operacao na direcao atual.
3. Tamanho da entrada:
   - usa **1% do saldo livre de futuros**
   - tenta executar com valor **exato**
   - se o simbolo principal nao suporta exato por regra de lote/notional, escaneia simbolos de fallback definidos em `LAPS_SYMBOLS`.
4. Quando ROI da posicao atingir **+100%**, fecha 100% da posicao.
5. Apos fechar, executa rebalanceamento para manter **80/20 (spot/futuros)**.
6. Se ROI cair ate **-60%**, transfere **20% do spot livre** para futuros (maximo de 4 topups).
7. Quando recuperar acima de **-31%**, rebalanceia imediatamente para 80/20.
8. Regra 3x:
   - se a tendencia virar contra a posicao, entra em alerta
   - quando a tendencia voltar para a mesma direcao original, executa reforco de **3x** sobre a entrada inicial
   - apos reforco, quando ROI voltar para >= 0, fecha 100% para liberar margem

## Estrutura

```text
.
├── run_bot.py
├── requirements.txt
├── .env.example
└── src/laps_bot
    ├── bot.py
    ├── config.py
    ├── exchange.py
    ├── indicators.py
    ├── logger.py
    ├── models.py
    ├── rebalance.py
    ├── risk.py
    └── strategy.py
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

## Principais variaveis

- `LAPS_SYMBOLS`: simbolo principal e fallback (ex.: `BTC/USDT:USDT,ETH/USDT:USDT`)
- `LAPS_MAX_POSITIONS`: nesta versao deve ficar `1`
- `LAPS_BALANCE_RISK_PCT`: `%` da entrada inicial (default `1`)
- `LAPS_TARGET_ROI_PCT`: alvo de fechamento (default `100`)
- `LAPS_ADD_MARGIN_TRIGGER_PCT`: gatilho topup (default `-60`)
- `LAPS_REBALANCE_RECOVERY_PCT`: gatilho de recuperacao (default `-31`)
- `LAPS_REINFORCEMENT_MULTIPLIER`: multiplicador do reforco (default `3`)
- `LAPS_SPOT_TARGET_PCT` / `LAPS_FUTURES_TARGET_PCT`: alvo 80/20
- `LAPS_MARGIN_TOPUP_PCT`: percentual transferido no topup (default `20`)
- `LAPS_MAX_TOPUPS`: quantidade de "vidas" (default `4`)

## Operacao segura (obrigatorio)

1. Rode em sandbox por varios ciclos completos (entrada, fechamento, rebalance e topup).
2. Ative monitoramento de processo no VPS (systemd, supervisor ou pm2).
3. Use chave de API sem permissao de saque.
4. Defina alertas externos de erro e latencia.
5. Comece com saldo minimo de teste antes de escalar.
