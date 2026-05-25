# Insurance Adequacy Engine

A rule-based insurance adequacy assessment engine for the Indian market — budget-aware, existing-policy-aware, and grounded in standard actuarial frameworks (HLV + NBA).

---

## Problem

About 60% of Indians carry no health insurance. Most who do hold ₹3–5 lakh policies that won't cover a serious hospitalization in a Tier 1 city. Life cover is worse: free calculators return a single "15× income" figure with no accounting for existing policies, household liabilities, dependents, or what a family can actually afford per month.

This engine does the full analysis: what you need, what you have, what the gap is, and in what order to close it — given your budget.

---

## What the system does

- Computes **life cover need** via two methods: Human Life Value (HLV) and Need-Based Analysis (NBA), takes the higher figure
- Computes **health cover need** with city-tier-adjusted floors (Tier 1: ₹25L minimum; Tier 2: ₹15L; Tier 3: ₹10L)
- Computes **accident and disability cover need** based on income replacement
- **Audits existing policies** for adequacy and flags ULIP/endowment inefficiency via implied IRR vs. term + index fund alternative
- **Sequences the gap-closure plan** with budget constraints and override rules (no health cover → health first; no dependents → term last)
- **Estimates monthly premiums** for each recommended product
- Generates **plain-English explanations** via the Anthropic API, with deterministic template fallback on failure
- Adjusts premium cost display for **tax regime** (old regime: 80C/80D deductions reduce effective cost; new regime: no deductions)

---

## Architecture

```
Streamlit Dashboard (dashboard/app.py)
        │  HTTP POST /assess
        ▼
FastAPI API Layer (src/engine/api.py)
        │
        ▼
Service Layer (src/engine/service.py)
        │
        ├── adequacy.py   — HLV, NBA, health, accident/disability scorers
        ├── audit.py      — existing policy audit + IRR analysis
        ├── prioritizer.py — budget-constrained action plan sequencing
        └── llm.py        — Anthropic API explanation + template fallback
```

Hexagonal architecture: the dashboard never imports engine modules directly. All communication goes through the HTTP API, which means the engine is independently testable and the dashboard is swappable.

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/assess` | Full assessment — life, health, accident, policy audit, action plan, explanation |
| `GET` | `/health` | Liveness check |
| `GET` | `/docs` | Auto-generated OpenAPI docs (FastAPI) |

---

## Quick start

**Prerequisites:** Python 3.11+, [uv](https://github.com/astral-sh/uv)

```bash
git clone <repo-url>
cd insurance-adequacy-engine

# Install dependencies
uv sync

# Copy environment template and add your Anthropic API key
cp .env.example .env
# edit .env: ANTHROPIC_API_KEY=sk-ant-...

# Start the API server
uv run uvicorn src.engine.api:app --port 8000

# In a second terminal, start the dashboard
uv run streamlit run dashboard/app.py
# Open http://localhost:8501 in your browser
```

**Try the API directly:**

```bash
curl -s -X POST http://localhost:8000/assess \
  -H "Content-Type: application/json" \
  -d '{
    "age": 35,
    "gender": "male",
    "city_tier": "tier_1",
    "annual_income": 1800000,
    "monthly_expenses": 50000,
    "monthly_insurance_budget": 10000,
    "tax_regime": "new",
    "spouse": {"age": 32, "annual_income": 0},
    "children": [{"age": 5}, {"age": 3}],
    "existing_policies": []
  }' | python3 -m json.tool
```

**Run tests:**

```bash
uv run pytest --tb=short -q
```

---

## Design decisions

| Decision | Why |
|----------|-----|
| **Rule-based, not ML** | Insurance adequacy is normative — there is a defensible right answer based on income, liabilities, and dependents. ML would obscure the reasoning and make the output unauditable. |
| **HLV and NBA, take the higher** | Neither method is universally correct. HLV (income replacement) underestimates for high-earners with large debts; NBA (debt + dependents) underestimates for stable earners with long runways. Taking the max is conservative. |
| **City-tier floors for health, not income %** | Hospitalization costs in Tier 1 cities start at ₹5–10L for serious conditions. An income percentage ignores the actual cost of care. |
| **IRR via bisection, no numpy** | The engine has no scientific computing dependency. Bisection converges to 6 decimal places in 200 iterations — more than sufficient for a policy audit. |
| **LLM for explanation only** | The numbers come from deterministic logic. The LLM's job is to translate them into plain English. Mixing LLM judgment into the calculation would make the system unauditable. |
| **Template fallback always exists** | An Anthropic API failure should never break the assessment. Every LLM output path has a deterministic template that fires on any exception. |
| **Dashboard calls API over HTTP** | Enforces the hexagonal architecture boundary. The dashboard cannot accidentally bypass validation or call engine internals directly. |
| **`uv` for package management** | Faster than pip, lockfile-based reproducibility, no virtualenv ceremony. |

---

## Project structure

```
insurance-adequacy-engine/
├── src/engine/
│   ├── schemas.py       # Pydantic input/output models — all domain types live here
│   ├── adequacy.py      # HLV, NBA, health, accident/disability scorers
│   ├── audit.py         # Existing policy audit: adequacy + IRR + opportunity cost
│   ├── prioritizer.py   # Budget-constrained action plan sequencing
│   ├── llm.py           # Anthropic API explanation + template fallback
│   ├── service.py       # Orchestrates the full pipeline — only file that imports everything
│   ├── api.py           # FastAPI endpoints
│   └── config.py        # All tunable constants (rates, thresholds, premium estimates)
├── tests/
│   ├── test_adequacy.py    # 50+ tests for HLV, NBA, health, accident scorers
│   ├── test_audit.py       # IRR computation, opportunity cost, policy verdict tests
│   ├── test_prioritizer.py # Priority ordering, budget split, override rule tests
│   └── test_api.py         # API integration tests (full request/response cycle)
├── dashboard/
│   └── app.py           # Streamlit dashboard — calls API over HTTP
├── specs/               # spec.md, plan.md, tasks.md — written before each feature
├── data/
│   └── products.json    # Simulated insurance product catalog
├── pyproject.toml
├── .env.example
└── CLAUDE.md
```

---

## What I learned building this

**Spec-first development actually works.** Writing `specs/spec.md` before touching code forced me to make decisions about the domain model upfront. When implementation started, there was almost no backtracking — the schemas matched the spec and the scorers matched the schemas.

**Pure functions are worth the discipline.** Every scorer in `adequacy.py` is a pure function: inputs in, output out, no side effects. This made the test suite fast to write and trivial to run — no mocking, no fixtures beyond the input data.

**The LLM layer is the easiest part to get wrong.** It's tempting to let the LLM influence the numbers ("what cover should I recommend?"). The discipline of "LLM sees the computed output, explains it, and nothing else" is harder to maintain than it sounds — especially when you're debugging a template and the LLM output looks smarter than your template.

**Budget-constrained sequencing has more edge cases than expected.** The "no dependents → term last" rule interacts with "no health cover → health first" in ways that only show up in tests. Writing tests first for the override rules caught three ordering bugs before they became user-visible.

**IRR analysis on endowments is genuinely useful.** A ₹50,000/year endowment policy maturing at ₹8L in 20 years has an implied IRR of about 4.5% — below inflation. The audit surfaces this with a specific number, not just "endowments are bad."

---

## Future improvements

- **Real premium data**: Replace heuristic premium estimates with actual product catalog prices
- **Dependent parent analysis**: Health and accident cover for dependent parents (current version notes the gap but doesn't quantify it)
- **PDF report generation**: Downloadable assessment summary
- **Multi-scenario comparison**: "What if my income grows 10% per year?" modelling
- **Direct policy links**: Connect gap recommendations to available products on Policybazaar/Ditto

---

## Built with

- [FastAPI](https://fastapi.tiangolo.com/) — API layer and OpenAPI docs
- [Pydantic v2](https://docs.pydantic.dev/) — data validation and schema definitions
- [Streamlit](https://streamlit.io/) — interactive dashboard
- [Anthropic API](https://docs.anthropic.com/) — LLM explanation layer (claude-haiku-4-5)
- [uv](https://github.com/astral-sh/uv) — package management
- [pytest](https://pytest.org/) — 166 tests across 4 test modules
- [ruff](https://docs.astral.sh/ruff/) — linting and formatting

---

## Disclaimer

Insurance Adequacy Engine is an educational tool. Output is for informational purposes only and does not constitute financial or insurance advice. Always consult a SEBI-registered financial advisor or IRDAI-licensed insurance agent before making coverage decisions.
