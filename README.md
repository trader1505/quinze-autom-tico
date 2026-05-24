# LAPS HYBRID

LAPS HYBRID is an adaptive crypto trading infrastructure concept focused on
survivability, modular quantitative decisioning, live and shadow strategy
competition, dynamic risk, and exchange-safe execution.

## Adaptive Core Engine

The first backend module in this repository is the Adaptive Core Engine: the
central asynchronous orchestration layer responsible for reading market state,
detecting market regimes, evaluating live and shadow strategies, scoring
confidence, enforcing risk priority, and routing approved intents to execution
gateways.

- Architecture: [docs/adaptive-core-engine.md](docs/adaptive-core-engine.md)
- Package: `backend/laps_hybrid/adaptive_core`
- Validation: `python3 -m unittest discover -s tests`

## Risk & Survival Engine

The Risk & Survival Engine is the platform's highest-priority protection layer.
It evaluates portfolio exposure, drawdown, exchange stability, liquidity,
strategy degradation, hidden BTC correlation, failsafe incidents, and watchdog
signals to produce enforceable safe-mode budgets.

- Architecture: [docs/risk-survival-engine.md](docs/risk-survival-engine.md)
- Package: `backend/laps_hybrid/risk_survival`
- Validation: `python3 -m unittest discover -s tests`

