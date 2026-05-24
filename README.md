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

## Execution & Exchange Engine

The Execution & Exchange Engine is the real-market execution layer. It provides
exchange connector boundaries, resilient websocket health decisions, smart order
planning, order lifecycle validation, position reconciliation, event publishing,
audit records, and execution failsafe responses.

- Architecture: [docs/execution-exchange-engine.md](docs/execution-exchange-engine.md)
- Package: `backend/laps_hybrid/execution_exchange`
- Validation: `python3 -m unittest discover -s tests`

## Copy Trading & Investor Ecosystem

The Copy Trading & Investor Ecosystem turns the platform into scalable investor
infrastructure with master-account replication, investor subaccounts,
proportional scaling, investor DNA constraints, revenue distribution, referral
tracking, wallet ledgering, dashboard planning, and investor audit boundaries.

- Architecture: [docs/copy-trading-investor-ecosystem.md](docs/copy-trading-investor-ecosystem.md)
- Package: `backend/laps_hybrid/copy_trading`
- Validation: `python3 -m unittest discover -s tests`

## AI Intelligence & Learning System

The AI Intelligence & Learning System is the adaptive intelligence layer. It
scores confidence, evaluates strategy quality, detects degradation, calculates
market fear, understands session behavior, records shadow strategy evidence, and
recommends adaptive aggression while preserving survival-first constraints.

- Architecture: [docs/ai-intelligence-learning-system.md](docs/ai-intelligence-learning-system.md)
- Package: `backend/laps_hybrid/ai_intelligence`
- Validation: `python3 -m unittest discover -s tests`

