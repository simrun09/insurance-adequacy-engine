# Specifications

This directory holds the specifications, plans, and tasks that drive development.

## Spec-driven development workflow

1. **`spec.md`** — describes *what* the system should do and *why*. No implementation detail.
2. **`plan.md`** — describes *how* it will be built: architecture, files, data flow.
3. **`tasks.md`** — atomic, verifiable units of work derived from the plan.

Code is written only after the relevant spec, plan, and task exist. Every line of code traces back to a stated requirement.

## Convention

Files are prefixed by day (e.g. `01-day1-spec.md`, `02-day2-schemas-plan.md`) so the sequence of decisions is preserved.
