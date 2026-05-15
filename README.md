# LAPS Crypto

Sistema modular de trading para Binance Futures com modo simulado (`paper`) e modo real (`live`).

## Segurança principal (não-negociável)

Antes de fechar qualquer posição, o sistema calcula:

- taxa de entrada
- taxa de saída
- custo de funding
- slippage estimado

O fechamento só é permitido quando:

- `NET_PROFIT >= +0.1%` (configurável por `LAPS_MIN_CLOSE_PROFIT_PCT`)

Se não atingir:

- fechamento é bloqueado

## Modos de execução

- `paper` (padrão): simulação local
- `live`: envia ordens reais para Binance Futures

## Configuração rápida

Crie variáveis de ambiente:

```bash
export LAPS_EXECUTION_MODE=paper
export LAPS_USE_BINANCE_TESTNET=true
export LAPS_DEFAULT_SYMBOL=BTCUSDT
export BINANCE_API_KEY="SUA_API_KEY"
export BINANCE_API_SECRET="SUA_API_SECRET"
```

### Para conta real

```bash
export LAPS_EXECUTION_MODE=live
export LAPS_USE_BINANCE_TESTNET=false
```

### Recomendado primeiro

Use `live` com `LAPS_USE_BINANCE_TESTNET=true` para validar tudo em ambiente de teste antes de operar na conta principal.

## Execução

```bash
python3 -m laps_crypto.app.main
```

## Testes

```bash
python3 -m pytest -q
```
