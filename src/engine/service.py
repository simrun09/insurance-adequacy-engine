"""
service.py — Orchestrates the full insurance adequacy assessment pipeline.

This is the only module that imports from every other engine module.
All other modules are independent and testable in isolation.
The API layer and dashboard both call assess() — they never touch scorers directly.
"""

from .adequacy import (
    compute_accident_disability_need,
    compute_health_cover_need,
    recommend_life_cover,
)
from .audit import audit_all_policies
from .llm import DISCLAIMER, generate_explanation
from .prioritizer import build_action_plan
from .schemas import AssessmentResult, UserProfile


def assess(profile: UserProfile) -> AssessmentResult:
    """
    Run the full insurance adequacy assessment for a validated user profile.

    Composes the engine pipeline in order:
      1. adequacy scorers  → coverage needs
      2. audit             → existing policy verdicts
      3. prioritizer       → budget-constrained action plan
      4. llm               → plain-English explanation (template fallback on failure)

    Exceptions from scorers propagate naturally — they are programming errors,
    not recoverable runtime conditions. The API layer handles 500s.
    LLM failures are handled inside generate_explanation(); this function
    never sees them.
    """
    life_need = recommend_life_cover(profile)
    health_need = compute_health_cover_need(profile)
    accident_disability_need = compute_accident_disability_need(profile)

    audits = audit_all_policies(
        profile, life_need, health_need, accident_disability_need
    )

    plan = build_action_plan(life_need, health_need, accident_disability_need, profile)

    explanation, used_llm = generate_explanation(
        profile, life_need, health_need, accident_disability_need, audits, plan
    )

    return AssessmentResult(
        life_cover_need=life_need,
        health_cover_need=health_need,
        accident_disability_need=accident_disability_need,
        policy_audits=audits,
        action_plan=plan,
        explanation=explanation,
        explanation_is_llm_generated=used_llm,
        disclaimer=DISCLAIMER,
    )
