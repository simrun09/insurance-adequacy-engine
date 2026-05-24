# Insurance Adequacy Engine — Task Breakdown

Version: 1.0
Date: Day 2
Status: Active

Maps to: specs/01-spec.md and specs/02-plan.md

Each task is atomic (one verifiable change), has a clear "done" condition,
and is sized to fit within a single 1-hour daily working session.

---

## Day 2 — Today

- [x] T2.1: Install uv, set up venv, add dependencies (DONE in Block 1)
- [x] T2.2: Create project directory structure (DONE in Block 1)
- [x] T2.3: Write specs/02-plan.md (IN PROGRESS)
- [x] T2.4: Write specs/02-tasks.md (IN PROGRESS)
- [x] T2.5: Implement src/engine/schemas.py — all input and output Pydantic models
- [x] T2.6: Write tests/test_schemas.py — validation behavior tests
- [x] T2.7: Commit and push

Done when: schemas.py defines every Pydantic model named in the plan,
tests pass, code is committed and pushed.

---

## Day 3 — Adequacy Engine

- [x] T3.1: Implement src/engine/config.py with all constants and source citations
- [x] T3.2: Implement compute_hlv() in src/engine/adequacy.py
- [x] T3.3: Implement compute_nba() in src/engine/adequacy.py
- [x] T3.4: Implement recommend_life_cover() that returns max(HLV, NBA)
- [x] T3.5: Implement compute_health_cover_need() with city-tier logic
- [x] T3.6: Implement compute_accident_disability_need()
- [x] T3.7: Implement src/engine/tax.py with adjust_for_regime()
- [x] T3.8: Write tests/test_adequacy.py for every scorer
- [x] T3.9: Write tests/test_tax.py
- [x] T3.10: Commit and push

Done when: every functional requirement in spec sections FR-2 through
FR-5 has a corresponding tested function.

---

## Day 4 — Policy Audit and Prioritizer

- [x] T4.1: Implement src/engine/audit.py — IRR computation for endowment/ULIP
- [x] T4.2: Implement opportunity cost calculation (term + index fund alternative)
- [x] T4.3: Implement audit verdict logic (efficient/mixed/inefficient)
- [x] T4.4: Implement src/engine/prioritizer.py with default priority logic
- [x] T4.5: Implement priority overrides (no-health-cover, no-dependents)
- [x] T4.6: Implement budget-constrained sequence builder
- [x] T4.7: Write tests/test_audit.py
- [x] T4.8: Write tests/test_prioritizer.py
- [x] T4.9: Commit and push

Done when: FR-6 and FR-7 are fully implemented and tested.

---

## Day 5 — LLM Layer and Graceful Fallback

- [x] T5.1: Create .env.example with required keys listed
- [x] T5.2: Set up secrets loading via python-dotenv
- [x] T5.3: Implement src/engine/llm.py with generate_explanation()
- [x] T5.4: Implement template fallback function
- [x] T5.5: Implement try/except wrapper that selects path
- [x] T5.6: Write tests/test_llm.py with mocked Anthropic client
- [x] T5.7: Verify the system works fully with no API key (fallback path)
- [x] T5.8: Commit and push

Done when: FR-8 is implemented with both LLM and template paths working.

---

## Day 6 — FastAPI Backend

- [ ] T6.1: Implement src/engine/service.py — orchestrates the pipeline
- [ ] T6.2: Implement src/engine/api.py — FastAPI app with /assess endpoint
- [ ] T6.3: Wire up validation error handling (422 responses)
- [ ] T6.4: Wire up internal error handling (500 responses)
- [ ] T6.5: Add OpenAPI metadata (title, description, version)
- [ ] T6.6: Write tests/test_api.py using FastAPI TestClient
- [ ] T6.7: Manual smoke test with curl
- [ ] T6.8: Commit and push

Done when: FR-9 is implemented, OpenAPI docs are accessible at /docs,
and the endpoint returns valid AssessmentResult JSON.

---

## Day 7 — Dashboard and Polish

- [ ] T7.1: Implement dashboard/app.py with input form
- [ ] T7.2: Add gap visualization (current vs recommended)
- [ ] T7.3: Add policy audit table with traffic-light indicators
- [ ] T7.4: Add prioritized action plan display
- [ ] T7.5: Add LLM explanation panel
- [ ] T7.6: Add disclaimer footer
- [ ] T7.7: Rewrite README.md as a polished portfolio document
- [ ] T7.8: Practice the 30-second interview pitch out loud
- [ ] T7.9: Tag release v1.0.0 and push tags
- [ ] T7.10: Final commit

Done when: FR-10 is implemented, dashboard renders end-to-end, README
is portfolio-quality.

---

## Conventions for Marking Progress

- [ ] = not started
- [~] = in progress (use when starting a task)
- [x] = done

Update this file as you go. The tasks.md is the project's pulse —
glance at it to know where you are.
