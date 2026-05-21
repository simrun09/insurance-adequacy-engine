# CLAUDE.md — Project Context for Claude Code

## Project
Insurance Adequacy Engine — a budget-constrained, existing-policy-aware insurance protection planning engine. Rule-based actuarial logic (HLV, NBA) with LLM-generated explanations and template fallback.

## Tech Stack
- Python 3.11+
- FastAPI (backend API)
- Pydantic (data validation and schemas)
- Streamlit (dashboard, Day 7)
- Anthropic API (LLM layer, Day 5)
- pytest (testing)
- uv (package management)
- git (version control)

## Development Approach
- Spec-driven: specs/ directory contains spec.md, plan.md, tasks.md
- Every feature starts with a spec, then a plan, then implementation
- No code without a stated requirement in the spec
- Every architectural decision must be defensible ("why this, not that")

## Project Structure (target)
insurance-adequacy-engine/
  CLAUDE.md
  README.md
  .gitignore
  .env.example          # template for environment variables (no real secrets)
  pyproject.toml         # project metadata and dependencies
  specs/                 # specifications, plans, tasks
  src/
    engine/
      __init__.py
      schemas.py         # Pydantic input/output models
      adequacy.py        # HLV, NBA, health, accident, disability scorers
      audit.py           # existing policy audit (ULIP/endowment trap detection)
      prioritizer.py     # budget-constrained gap closure sequencing
      llm.py             # LLM integration + template fallback
      api.py             # FastAPI app and endpoints
  tests/                 # pytest tests mirroring src/ structure
  dashboard/
    app.py               # Streamlit dashboard
  data/
    products.json        # simulated insurance product catalog

## Conventions
- Type hints on all function signatures
- Docstrings on all public functions explaining WHAT and WHY
- Functions should be pure where possible (input in, output out, no side effects)
- Each scorer in adequacy.py is its own function with documented formula and source
- Config values (discount rates, city tier thresholds, etc.) live in a config file or constants module, not hardcoded in logic
- Secrets (.env) never committed — use .env.example as a template
- Commit messages: imperative tense, descriptive ("Add HLV scorer with IRDAI discount rate" not "updated stuff")

## Key Domain Rules
- Adequacy is normative, not predictive — no ML for coverage recommendations
- Life cover recommendation = max(HLV, NBA)
- Health cover floors are city-tier-adjusted, not income-percentage-based
- Tax regime (old vs new) affects effective premium cost via 80C/80D
- ULIP/endowment audit uses implied IRR comparison against term plus index fund alternative
- LLM generates explanations only — never influences the numbers
- Template fallback must always exist for every LLM-generated output

## Current State
- [x] Day 1: Project setup, git, CLAUDE.md, initial spec
- [x] Day 2: Pydantic schemas (input/output models)
- [x] Day 3: Adequacy engine (HLV, NBA, health, accident, disability)
- [ ] Day 4: Policy audit + budget-constrained prioritizer
- [ ] Day 5: LLM layer + graceful degradation
- [ ] Day 6: FastAPI endpoints
- [ ] Day 7: Streamlit dashboard + README polish
