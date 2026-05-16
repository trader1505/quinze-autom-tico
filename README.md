# LAPS 1505 - Bot Binance Futures

Bot profissional para operar **Binance Futures** com:

- Timeframe **M15**
- Médias móveis exponenciais **EMA 12 / EMA 26**
- Regra de tendência: **EMA12 acima = LONG**, **EMA12 abaixo = SHORT**
- Entrada com **1% do capital livre em Futures** (com teto por operação)
- Gestão de capital com rebalanceamento automático **80% Spot / 20% Futures**
- Take profit em **100% ROI** (fecha operação inteira)
- Lógica de recuperação **3x**
- Painel web com status em tempo real, tabela de operações abertas/pendentes e som para `TP` e para execução do `3x`

## Como a estratégia está modelada

### 1) Motor de sinal
- Lê candles de 15 minutos.
- Calcula EMA 12 e EMA 26.
- Processa somente **candle fechado** (evita ruído intrabar).
- Somente considera sinal quando há **confirmação** (cruzamento mantido em 2 candles seguidos).

### 2) Motor de entrada
- O bot mantém até `BOT_MAX_CONCURRENT_OPS` posições simultâneas (padrão `30`).
- Escolhe símbolos de uma lista de altcoins (`BOT_TRADING_SYMBOLS`) e abre novas posições conforme margem livre.
- Tamanho de cada operação:
  - base: `1%` do saldo livre em Futures (`availableBalance`);
  - mínimo: `BOT_MIN_NOTIONAL`;
  - máximo: `BOT_MAX_NOTIONAL_PER_OP` (proteção para não entrar com valor grande).

### 3) Motor TP (100% ROI)
- Se `ROI >= 100%`:
  - envia fechamento total com `reduceOnly`;
  - divide execução em 3 fatias (`order_slices = 3`) para tentar melhor preço;
  - dispara evento sonoro "cash" no painel.

### 4) Motor de recuperação 3x
- Se houver posição aberta e aparecer tendência confirmada oposta:
  - arma o modo de recuperação (`pending_3x = true`).
- Quando a tendência voltar e confirmar novamente para o lado âncora:
  - entra com `3x` do notional base da operação;
  - também em 3 fatias;
  - dispara evento sonoro de recuperação.
- Ao iniciar o bot, se já existir posição aberta na Binance, o estado interno é sincronizado automaticamente para gerenciar essa posição existente.

### 5) Motor de tesouraria e risco (Spot/Futures)
- Objetivo contínuo: manter **80/20** no capital total.
- Se entrar novo saldo em Spot, o motor rebalanceia automaticamente.
- Defesa de margem:
  - se `margin_ratio >= 60%`, transfere **+20% do capital total atual** para Futures;
  - se `margin_ratio <= 30%`, normaliza novamente para 80/20.

## Estrutura do projeto

```text
src/laps1505_bot/
  api.py         # API FastAPI + rotas do painel
  config.py      # parâmetros e env vars
  engine.py      # orquestração dos motores
  gateway.py     # Binance live + simulação
  indicators.py  # EMA e detecção de tendência
  models.py      # modelos de domínio
  risk.py        # motor de risco/rebalanceamento
  strategy.py    # motor de entrada/TP/3x
  main.py        # entrypoint
static/
  dashboard.html # painel web
tests/
  test_*.py      # testes unitários e integração leve
```

## Instalação local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuração

Copie o arquivo `.env.example` para `.env` e ajuste:

```bash
cp .env.example .env
```

Variáveis principais:
- `BOT_DRY_RUN=true` para simulação
- `BOT_DRY_RUN=false` para operar real
- `BINANCE_API_KEY`, `BINANCE_API_SECRET` para modo live
- `BOT_SYMBOL=BTCUSDT`
- `BOT_INTERVAL=15m`
- `BOT_MAX_CONCURRENT_OPS=30`
- `BOT_MAX_NOTIONAL_PER_OP=5.0`
- `BOT_TRADING_SYMBOLS=...` (lista de altcoins em CSV)

## Rodando

```bash
python -m laps1505_bot.main
```

Painel:

- `http://localhost:8080/`

API:

- `GET /api/status`
- `POST /api/start`
- `POST /api/stop`
- `POST /api/cycle`

## Deploy em VPS (Docker)

### Instalação em 1 comando (modo real com API segura)

Este comando baixa e executa o instalador completo.  
As chaves `BINANCE_API_KEY` e `BINANCE_API_SECRET` são solicitadas com entrada oculta (não aparecem na tela).

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/trader1505/quinze-autom-tico/cursor/laps1505-bot-binance-5cc7/scripts/install_real.sh)"
```

O instalador:
- instala Docker + Compose (se necessário)
- clona/atualiza o projeto em `/opt/laps1505`
- cria `.env` com permissão `600`
- para serviços antigos conflitantes
- sobe containers e inicia o motor automaticamente

### Deploy manual

```bash
docker compose up -d --build
```

## Testes internos

```bash
pytest -q
```

## Observações importantes

- Este bot foi estruturado para execução profissional, mas **todo setup live exige validação em conta de teste** primeiro.
- Em modo live, conferir permissões da API Binance (Futures + Transfer).
- Sempre iniciar em `dry_run` antes de liberar ordens reais.
