# Insurance Adequacy Engine

A budget-constrained, existing-policy-aware insurance protection planning engine for the Indian market.

Built with spec-driven development. Uses FastAPI for the backend, Streamlit for the dashboard, and an LLM layer for personalized explanation with graceful fallback to templates.

**Status:** 🚧 In active development — Day 1 of 7.

## What this is

About 60% of Indians have no health insurance, and most who do are carrying ₹3–5 lakh policies that won't cover a serious hospitalization. Existing free calculators give one-line answers like "15× your income" — ignoring existing policies, budget constraints, and the post-2024 tax-regime reality.

This project builds a self-serve adequacy engine grounded in standard actuarial frameworks (Human Life Value, Need-Based Analysis), with multi-product coverage analysis (term, health, accident, disability), budget-aware sequencing, existing-policy audit, and an LLM layer for plain-English explanation.

## Build progress

- [x] Day 1: Setup, spec, repo
- [ ] Day 2: Data schemas
- [ ] Day 3: Adequacy engine
- [ ] Day 4: Policy audit + prioritizer
- [ ] Day 5: LLM layer + fallback
- [ ] Day 6: FastAPI endpoints
- [ ] Day 7: Streamlit dashboard + polish

## Disclaimer

Insurance Adequacy Engine is an educational tool. It is not insurance or financial advice. Consult a licensed advisor or certified financial planner before making policy decisions.
