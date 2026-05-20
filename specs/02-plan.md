# Insurance Adequacy Engine — Implementation Plan

Version: 1.0
Date: Day 2
Status: Draft

Maps to: specs/01-spec.md

---

## 1. Architecture Overview

The system has four logical layers, with strict separation of concerns:

Layer 1: Presentation (Streamlit dashboard) — dashboard/app.py
Layer 2: API (FastAPI) — src/engine/api.py — validates input, calls service, returns JSON
Layer 3: Domain logic (the engine) — src/engine/{adequacy,audit,...}.py — pure functions, no I/O, no FastAPI imports
Layer 4: External services (LLM) — src/engine/llm.py — optional, with template fallback

Why this separation matters: the engine layer can be tested without
HTTP, without Streamlit, without an LLM. The API layer can be swapped
(FastAPI to Flask, etc.) without touching domain logic. This is the
"hexagonal architecture" pattern in a small form.

---

## 2. Technology Decisions and Rationale

### 2.1 Pydantic for data validation
Chosen because: validates at runtime (rejects bad input before it reaches
business logic), generates OpenAPI schemas automatically when combined with
FastAPI, type-safe, and the de facto standard in modern Python APIs.

Alternatives considered:
- Plain dataclasses: no runtime validation
- attrs: similar to Pydantic but less FastAPI integration
- Marshmallow: older, more verbose

### 2.2 FastAPI for the HTTP layer
Chosen because: validates request bodies against Pydantic models
automatically, generates OpenAPI/Swagger docs without extra code, supports
async natively, and rejects malformed requests with structured 422 errors.

Alternatives considered:
- Flask: would require manual validation for every endpoint
- Django REST: heavyweight for a single-endpoint service

### 2.3 Streamlit for the dashboard
Chosen because: pure-Python web UI suitable for a backend-focused project
where the dashboard is a demo surface, not a production frontend. No
JavaScript build pipeline needed.

Alternatives considered:
- React + Vite: too much frontend overhead for a 7-day project
- Gradio: similar to Streamlit but less customizable
- Plain Flask + HTML: more code for less visual quality

### 2.4 Anthropic API for LLM
Chosen because: high-quality text generation for personalized explanations,
structured output capability via JSON mode, generous free credits to start.

Alternatives considered:
- OpenAI: equally suitable; either works
- Local model (Ollama): no API key needed but adds GPU dependency and
  complicates deployment

### 2.5 uv for package management
Already justified in Day 2 setup notes.

### 2.6 pytest for testing
Industry standard. Fixture system allows test data reuse. Plays well
with pytest-cov for coverage reporting.

---

## 3. File Structure and Responsibilities

insurance-adequacy-engine/
  CLAUDE.md                  # Claude Code session context
  README.md                  # Project overview for GitHub
  pyproject.toml             # Dependencies and project metadata
  .env.example               # Template for required env vars (no secrets)
  .gitignore                 # Excludes .venv, .env, __pycache__, etc.
  specs/                     # Specifications, plans, tasks
  src/
    engine/
      __init__.py            # Package marker, exports public API
      schemas.py             # Pydantic models for all I/O
      config.py              # Constants: discount rates, thresholds
      adequacy.py            # Pure scorers: HLV, NBA, health, accident
      tax.py                 # Tax-regime-aware premium adjustments
      audit.py               # Existing policy audit (IRR analysis)
      prioritizer.py         # Budget-constrained gap sequencing
      llm.py                 # LLM call + template fallback
      service.py             # Orchestrates engine pipeline end-to-end
      api.py                 # FastAPI app with the single endpoint
  tests/
    __init__.py
    test_schemas.py
    test_adequacy.py
    test_audit.py
    test_prioritizer.py
    test_tax.py
    test_api.py
  dashboard/
    app.py                   # Streamlit dashboard
  data/
    (reserved for future product catalog if needed)

Each file has one responsibility. No file knows about more layers than
strictly necessary. Specifically:
- adequacy.py knows nothing about HTTP, Streamlit, or the LLM
- llm.py knows nothing about FastAPI
- api.py knows about schemas and service, nothing about scorers directly
- service.py is the only place where the full pipeline is composed

---

## 4. Data Flow (One Complete Request)

1. User fills out the Streamlit form
2. Streamlit dashboard POSTs JSON to FastAPI's /assess endpoint
3. FastAPI validates the JSON against UserProfile (Pydantic model)
   - If invalid: 422 with field-level error messages, never reaches engine
4. FastAPI calls service.assess(profile)
5. service.assess() orchestrates:
   a. adequacy.compute_life_cover_need(profile) returns LifeCoverNeed
   b. adequacy.compute_health_cover_need(profile) returns HealthCoverNeed
   c. adequacy.compute_accident_disability(profile) returns AccidentDisabilityNeed
   d. tax.adjust_premiums(profile, needs) returns effective premium estimates
   e. audit.audit_existing_policies(profile.policies) returns list of PolicyAudit
   f. prioritizer.build_plan(needs, audit, profile.budget) returns ActionPlan
   g. llm.generate_explanation(profile, results) returns Explanation
      - If LLM fails: template fallback returns same shape
6. service composes everything into an AssessmentResult Pydantic model
7. FastAPI serializes AssessmentResult to JSON and returns 200
8. Streamlit renders the result

---

## 5. Key Design Patterns

### 5.1 Pure functions in the engine
Every scorer (compute_hlv, compute_nba, etc.) is a pure function:
takes data, returns data, no side effects, no I/O. This makes them
trivially testable and easy to reason about.

### 5.2 Configuration over hardcoding
All tunable values (discount rates, city-tier floors, priority weights)
live in src/engine/config.py as named constants. Changing a threshold
should never require changing logic.

Example:
- Wrong: scattered "if income < 500000:" throughout code
- Right: "if income < config.LOW_INCOME_THRESHOLD:"

### 5.3 Service layer composition
Individual scorers don't call each other. The service layer composes
them. This means each scorer can be tested independently, and the
overall flow is explicit in one place (service.py).

### 5.4 Graceful degradation
The LLM module exposes a single function generate_explanation() that
internally tries the API call and falls back to a template on any
failure. The caller (service.py) doesn't know or care which path
was taken — same return type either way.

### 5.5 Schema-first thinking
We design Pydantic schemas before writing logic. This forces clarity
about what data flows where. The schemas become the contract between
layers.

---

## 6. Testing Strategy

- Unit tests for every scorer (test_adequacy.py)
- Unit tests for tax adjustments (test_tax.py)
- Unit tests for audit logic (test_audit.py)
- Unit tests for prioritizer (test_prioritizer.py)
- Schema validation tests (test_schemas.py) — confirm bad inputs are rejected
- Integration test for the API endpoint (test_api.py) — uses FastAPI's TestClient
- LLM tests use mocking to avoid real API calls

Target coverage: above 80 percent on engine code, less critical on dashboard.

---

## 7. Configuration Approach

A single Python module (src/engine/config.py) holds all tunable values
as named constants:

- DISCOUNT_RATE_DEFAULT = 0.06
- RETIREMENT_AGE = 60
- HEALTH_FLOOR_TIER1_METRO = 1_000_000   # 10 lakh
- HEALTH_FLOOR_TIER2 = 1_000_000
- HEALTH_FLOOR_TIER3 = 500_000
- SECTION_80C_LIMIT = 150_000
- SECTION_80D_SELF_LIMIT = 25_000
- SECTION_80D_PARENTS_LIMIT = 25_000
- SECTION_80D_PARENTS_SENIOR_LIMIT = 50_000

Every constant has a comment citing its source (IRDAI, Income Tax Act,
industry consensus). The source citation is what makes the value
defensible.

For a 7-day project, a Python module is sufficient. A production system
might externalize this to YAML or a config service for change without
deployment.

---

## 8. What This Plan Does NOT Cover

- Deployment (out of scope for 7-day local-only build)
- Authentication (out of scope per spec)
- Database persistence (stateless tool per spec)
- Frontend frameworks (Streamlit suffices)
- Performance optimization beyond defaults
- Internationalization

Being explicit about non-coverage is a maturity signal.
