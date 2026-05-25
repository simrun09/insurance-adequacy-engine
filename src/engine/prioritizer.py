"""
prioritizer.py — Budget-constrained gap closure sequencer.

Takes computed adequacy needs and produces an ordered ActionPlan: what to
buy first, what it costs, and what falls outside the user's budget.
All tunable values (premium rates, thresholds) come from config — no magic
numbers here.
"""

from . import config
from .schemas import (
    AccidentDisabilityNeed,
    ActionItem,
    ActionPlan,
    HealthCoverNeed,
    LifeCoverNeed,
    PolicyType,
    UserProfile,
)


def estimate_monthly_premium(
    policy_type: PolicyType,
    sum_assured: float,
    profile: UserProfile,
) -> float:
    """
    Rough monthly premium estimate for a given cover amount and policy type.

    Uses illustrative rates from config — NOT a real insurer quote. Intended
    only for budget planning inside build_action_plan.

    Health premium does not scale with sum_assured: the config only provides
    flat annual buckets (by age and family size), not a per-lakh rate.
    Disability and investment-linked types return 0.0 — they are not
    standalone purchase recommendations.
    """
    if sum_assured == 0:
        return 0.0

    if policy_type == PolicyType.TERM:
        annual = (sum_assured / 1_00_000) * config.TERM_PREMIUM_PER_LAKH_ANNUAL
        return round(annual / 12, 2)

    if policy_type == PolicyType.HEALTH:
        has_family = bool(profile.spouse or profile.children)
        if has_family:
            key = "family_floater"
        elif profile.age < 35:
            key = "individual_young"
        elif profile.age <= 45:
            key = "individual_mid"
        else:
            key = "individual_senior"
        return round(config.HEALTH_PREMIUM_ANNUAL_APPROX[key] / 12, 2)

    if policy_type == PolicyType.ACCIDENT:
        annual = (sum_assured / 10_00_000) * config.ACCIDENT_PREMIUM_ANNUAL_APPROX
        return round(annual / 12, 2)

    # DISABILITY: always a rider on term — no standalone premium
    # ENDOWMENT / ULIP: never recommended as new purchases
    return 0.0


def build_action_plan(
    life_need: LifeCoverNeed,
    health_need: HealthCoverNeed,
    accident_disability_need: AccidentDisabilityNeed,
    profile: UserProfile,
) -> ActionPlan:
    """
    Produce a budget-constrained, prioritised action plan to close coverage gaps.

    Default priority: term > health > accident > disability.

    Override rules (from FR-7):
      a. No existing health cover at all → health moves to priority 1.
         Rationale: a hospitalisation is more probable than death for a young
         person; one bill can wipe out savings.
      b. No dependents (no spouse, children, or dependent parents) → term
         drops to last. Rationale: term cover protects dependents; without
         any, the urgency is lower.
    """
    gaps = {
        PolicyType.TERM: life_need.gap,
        PolicyType.HEALTH: health_need.gap,
        PolicyType.ACCIDENT: accident_disability_need.accident_gap,
        PolicyType.DISABILITY: accident_disability_need.disability_gap,
    }

    # ── Priority ordering ──────────────────────────────────────────────────
    order: list[PolicyType] = [
        PolicyType.TERM,
        PolicyType.HEALTH,
        PolicyType.ACCIDENT,
        PolicyType.DISABILITY,
    ]

    # Override a: no existing health cover → health to front
    if health_need.existing_cover == 0:
        order = [PolicyType.HEALTH] + [t for t in order if t != PolicyType.HEALTH]

    # Override b: no dependents → term to back
    has_dependents = bool(
        profile.spouse or profile.children or profile.dependent_parents
    )
    if not has_dependents:
        order = [t for t in order if t != PolicyType.TERM] + [PolicyType.TERM]

    # ── Budget loop ────────────────────────────────────────────────────────
    items_within_budget: list[ActionItem] = []
    items_beyond_budget: list[ActionItem] = []
    running_total = 0.0
    priority_rank = 1

    for policy_type in order:
        gap = gaps[policy_type]
        if gap <= 0:
            continue

        # Disability is always a rider — no standalone action item
        if policy_type == PolicyType.DISABILITY:
            continue

        monthly_premium = estimate_monthly_premium(policy_type, gap, profile)
        running_total += monthly_premium

        item = ActionItem(
            policy_type=policy_type,
            recommended_cover=gap,
            estimated_monthly_premium=round(monthly_premium, 2),
            cumulative_premium=round(running_total, 2),
            remaining_budget=round(profile.monthly_insurance_budget - running_total, 2),
            priority_rank=priority_rank,
        )
        priority_rank += 1

        if running_total <= profile.monthly_insurance_budget:
            items_within_budget.append(item)
        else:
            items_beyond_budget.append(item)

    total_required = round(running_total, 2)
    shortfall = round(max(0.0, running_total - profile.monthly_insurance_budget), 2)

    return ActionPlan(
        items_within_budget=items_within_budget,
        items_beyond_budget=items_beyond_budget,
        total_monthly_premium_required=total_required,
        monthly_shortfall=shortfall,
    )
