"""
audit.py — Existing policy audit module.

Evaluates each existing policy for adequacy and, for investment-linked
products (ULIP/endowment), computes the implied IRR and opportunity cost
to flag inefficiency against the "term + index fund" alternative.
"""

import datetime

from engine import config
from engine.schemas import (
    AccidentDisabilityNeed,
    EfficiencyFlag,
    ExistingPolicy,
    HealthCoverNeed,
    LifeCoverNeed,
    PolicyAudit,
    PolicyType,
    UserProfile,
)


# ──────────────────────────────────────────────
# 1. IRR computation
# ──────────────────────────────────────────────

def _npv(r: float, annual_premium: float, years: int, maturity_value: float) -> float:
    """NPV of policy cash flows at rate r. Equals zero at the IRR.

    Handles r ≈ 0 explicitly: limit of P×(1-(1+r)^-n)/r as r→0 is P×n.
    """
    if abs(r) < 1e-9:
        pv_premiums = annual_premium * years
        pv_maturity = maturity_value
    else:
        pv_premiums = annual_premium * (1 - (1 + r) ** (-years)) / r
        pv_maturity = maturity_value / (1 + r) ** years
    return pv_maturity - pv_premiums


def compute_irr(
    annual_premium: float,
    years: int,
    maturity_value: float | None,
) -> float | None:
    """
    Implied IRR of an investment-linked policy via bisection.

    Returns the annual rate as a decimal (0.05 = 5%), or None if not
    computable (missing maturity data, zero tenure, zero premium).
    Pure Python — no numpy dependency.
    """
    if maturity_value is None or years == 0 or annual_premium == 0:
        return None

    r_low, r_high = -0.50, 0.50
    r_mid = 0.0
    for _ in range(200):
        r_mid = (r_low + r_high) / 2
        if _npv(r_mid, annual_premium, years, maturity_value) > 0:
            r_low = r_mid
        else:
            r_high = r_mid
        if (r_high - r_low) < 1e-6:
            break

    return round(r_mid, 6)


# ──────────────────────────────────────────────
# 2. Opportunity cost
# ──────────────────────────────────────────────

def compute_opportunity_cost(
    annual_premium: float,
    years: int,
    policy_irr: float,
    alternative_rate: float = config.INDEX_FUND_RETURN_RATE,
) -> float:
    """
    Rupee cost of staying in a ULIP/endowment vs the term + index fund alternative.

    Alternative: subtract a flat term premium estimate (config.TERM_PREMIUM_ANNUAL_ESTIMATE)
    from the annual premium and invest the remainder at alternative_rate.
    Policy: the same annual premium compounds at policy_irr.

    Formula — FV of annuity: P × [(1+r)^n − 1] / r
    opportunity_cost = max(0, FV_alternative − FV_policy)
    """
    if years == 0:
        return 0.0

    investable = annual_premium - config.TERM_PREMIUM_ANNUAL_ESTIMATE
    if investable <= 0:
        return 0.0

    def _fv(p: float, r: float, n: int) -> float:
        if abs(r) < 1e-9:
            return p * n
        return p * ((1 + r) ** n - 1) / r

    fv_alternative = _fv(investable, alternative_rate, years)
    fv_policy = _fv(annual_premium, policy_irr, years)

    return round(max(0.0, fv_alternative - fv_policy), 2)


# ──────────────────────────────────────────────
# 3. Private audit helpers
# ──────────────────────────────────────────────

def _efficiency_flag(irr: float) -> EfficiencyFlag:
    if irr >= config.IRR_THRESHOLD_EFFICIENT:
        return EfficiencyFlag.EFFICIENT
    if irr >= config.IRR_THRESHOLD_MIXED:
        return EfficiencyFlag.MIXED
    return EfficiencyFlag.INEFFICIENT


def _build_recommendation(
    policy_type: PolicyType,
    is_adequate: bool,
    adequacy_gap: float,
    efficiency_flag: EfficiencyFlag | None,
    implied_irr: float | None,
) -> str:
    """Plain-English verdict for the audit output. Never recommends surrendering."""
    if policy_type in (PolicyType.ULIP, PolicyType.ENDOWMENT):
        if efficiency_flag is None:
            return "Maturity data unavailable — efficiency cannot be assessed."
        if efficiency_flag == EfficiencyFlag.INEFFICIENT:
            return (
                f"Implied IRR of {implied_irr:.1%} is below 7% — lags a simple "
                "term + index fund alternative. Consult a fee-only advisor about this policy."
            )
        if efficiency_flag == EfficiencyFlag.MIXED:
            return (
                f"Implied IRR of {implied_irr:.1%} is mediocre. "
                "Returns trail a term + index fund strategy."
            )
        return f"Implied IRR of {implied_irr:.1%} is reasonable. Continue holding."

    if is_adequate:
        return "Coverage is adequate."
    return f"Coverage gap of ₹{adequacy_gap:,.0f}. Consider increasing cover."


def _recommended_cover_for(
    policy_type: PolicyType,
    life_need: LifeCoverNeed,
    health_need: HealthCoverNeed,
    accident_disability_need: AccidentDisabilityNeed,
) -> float:
    """Map a policy type to the relevant recommended cover from pre-computed needs."""
    if policy_type in (PolicyType.TERM, PolicyType.ENDOWMENT, PolicyType.ULIP):
        return life_need.recommended_cover
    if policy_type == PolicyType.HEALTH:
        return health_need.recommended_cover
    if policy_type == PolicyType.ACCIDENT:
        return accident_disability_need.recommended_accident_cover
    if policy_type == PolicyType.DISABILITY:
        return accident_disability_need.recommended_disability_cover
    return 0.0


def _audit_one(
    policy: ExistingPolicy,
    recommended_cover: float,
    current_year: int,
) -> PolicyAudit:
    """Core audit logic — pure and testable. No I/O, no datetime calls."""
    is_adequate = policy.sum_assured >= recommended_cover
    adequacy_gap = round(max(0.0, recommended_cover - policy.sum_assured), 2)

    efficiency_flag = None
    implied_irr = None
    opportunity_cost = None

    if policy.policy_type in (PolicyType.ULIP, PolicyType.ENDOWMENT):
        if (
            policy.maturity_year is not None
            and policy.maturity_value is not None
            and policy.maturity_year > current_year
        ):
            total_years = policy.maturity_year - policy.start_year
            remaining_years = policy.maturity_year - current_year

            implied_irr = compute_irr(policy.annual_premium, total_years, policy.maturity_value)

            if implied_irr is not None:
                efficiency_flag = _efficiency_flag(implied_irr)
                opportunity_cost = compute_opportunity_cost(
                    policy.annual_premium, remaining_years, implied_irr
                )

    recommendation = _build_recommendation(
        policy.policy_type, is_adequate, adequacy_gap, efficiency_flag, implied_irr
    )

    return PolicyAudit(
        policy_type=policy.policy_type,
        sum_assured=policy.sum_assured,
        is_adequate=is_adequate,
        adequacy_gap=adequacy_gap,
        efficiency_flag=efficiency_flag,
        implied_irr=implied_irr,
        opportunity_cost=opportunity_cost,
        recommendation=recommendation,
    )


# ──────────────────────────────────────────────
# 4. Public audit functions
# ──────────────────────────────────────────────

def audit_single_policy(
    policy: ExistingPolicy,
    profile: UserProfile,
) -> PolicyAudit:
    """
    Audit one policy in isolation — computes recommended cover from the profile.

    Use audit_all_policies when adequacy needs are already computed by service.py;
    this function recomputes them, which is redundant in that flow.
    """
    from engine.adequacy import (
        compute_accident_disability_need,
        compute_health_cover_need,
        recommend_life_cover,
    )

    life_need = recommend_life_cover(profile)
    health_need = compute_health_cover_need(profile)
    ad_need = compute_accident_disability_need(profile)
    current_year = datetime.date.today().year

    recommended_cover = _recommended_cover_for(policy.policy_type, life_need, health_need, ad_need)
    return _audit_one(policy, recommended_cover, current_year)


def audit_all_policies(
    profile: UserProfile,
    life_need: LifeCoverNeed,
    health_need: HealthCoverNeed,
    accident_disability_need: AccidentDisabilityNeed,
) -> list[PolicyAudit]:
    """
    Audit all existing policies using pre-computed adequacy needs.

    Called by service.py after adequacy scorers have run — reuses their
    output rather than recomputing it for each policy.
    """
    current_year = datetime.date.today().year
    return [
        _audit_one(
            policy,
            _recommended_cover_for(
                policy.policy_type, life_need, health_need, accident_disability_need
            ),
            current_year,
        )
        for policy in profile.existing_policies
    ]
