---
layout: default
---

# Insurance Adequacy Engine

A rule-based insurance adequacy assessment engine for the Indian market — budget-aware, existing-policy-aware, and grounded in standard actuarial frameworks (HLV + NBA).

[View on GitHub](https://github.com/simrun09/insurance-adequacy-engine){: .btn}

---

## Problem

About 60% of Indians carry no health insurance. Most who do hold ₹3–5 lakh policies that won't cover a serious hospitalization in a Tier 1 city. Life cover is worse: free calculators return a single "15× income" figure with no accounting for existing policies, household liabilities, dependents, or what a family can actually afford per month.

This engine does the full analysis: **what you need, what you have, what the gap is, and in what order to close it — given your budget.**

---

## What it does

- Computes **life cover need** via Human Life Value (HLV) and Need-Based Analysis (NBA) — takes the higher figure
- Computes **health cover need** with city-tier-adjusted floors (Tier 1: ₹25L; Tier 2: ₹15L; Tier 3: ₹10L)
- Computes **accident and disability cover need** based on income replacement
- **Audits existing policies** for adequacy; flags ULIP/endowment inefficiency via implied IRR vs term + index fund
- **Sequences the gap-closure plan** with budget constraints and override rules
- **Estimates monthly premiums** per recommended product
- Generates **plain-English explanations** via Anthropic Claude, with deterministic template fallback on failure
- Adjusts effective cost for **tax regime** (old: 80C/80D; new: no deductions)

---

## Architecture

```
Streamlit Dashboard
       │  HTTP POST /assess
       ▼
FastAPI API Layer
       │
       ▼
Service Layer
       │
       ├── adequacy.py    — HLV, NBA, health, accident/disability scorers
       ├── audit.py       — policy audit + IRR analysis
       ├── prioritizer.py — budget-constrained action plan
       └── llm.py         — Claude explanation + template fallback
```

Hexagonal architecture: the dashboard never imports engine modules directly. All communication goes through the HTTP API.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/assess` | Full assessment — needs, audit, action plan, explanation |
| `GET` | `/health` | Liveness check |
| `GET` | `/docs` | Auto-generated OpenAPI docs |

---

## Quick start

```bash
git clone https://github.com/simrun09/insurance-adequacy-engine.git
cd insurance-adequacy-engine

uv sync
cp .env.example .env   # add ANTHROPIC_API_KEY

# Terminal 1
uv run uvicorn src.engine.api:app --port 8000

# Terminal 2
uv run streamlit run dashboard/app.py
# Open http://localhost:8501
```

---

## Design decisions

| Decision | Why |
|----------|-----|
| **Rule-based, not ML** | Adequacy is normative — there is a defensible right answer. ML would obscure reasoning and make output unauditable. |
| **HLV and NBA, take the higher** | HLV underestimates for high-debt earners; NBA underestimates for long runways. Taking the max is conservative. |
| **City-tier floors for health** | Hospitalization costs in Tier 1 cities start at ₹5–10L. An income percentage ignores actual cost of care. |
| **IRR via bisection, no numpy** | Pure Python. Converges to 6 decimal places in 200 iterations — sufficient for a policy audit. |
| **LLM for explanation only** | Numbers come from deterministic logic. Mixing LLM judgment into calculations makes the system unauditable. |
| **Template fallback always exists** | API failure must never break the assessment. Every LLM output path has a deterministic fallback. |
| **Dashboard calls API over HTTP** | Enforces architecture boundary. Dashboard cannot bypass validation or call engine internals. |

---

## Tech stack

Python 3.11 · FastAPI · Pydantic v2 · Streamlit · Anthropic API · pytest (166 tests) · uv · ruff

---

## Disclaimer

Insurance Adequacy Engine is an educational tool. Output is for informational purposes only and does not constitute financial or insurance advice. Consult a SEBI-registered advisor or IRDAI-licensed agent before making coverage decisions.
