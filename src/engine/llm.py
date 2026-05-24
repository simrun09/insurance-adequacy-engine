"""
llm.py — LLM explanation layer with graceful degradation.

The single public function generate_explanation() tries the Anthropic API
first and falls back to a high-quality template on any failure.
The caller always receives the same return type regardless of which path ran.
"""

import os

from dotenv import load_dotenv

from engine.schemas import (
    AccidentDisabilityNeed,
    ActionPlan,
    EfficiencyFlag,
    HealthCoverNeed,
    LifeCoverNeed,
    PolicyAudit,
    PolicyType,
    UserProfile,
)

load_dotenv()

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024
_DISCLAIMER = (
    "This assessment is for educational purposes only and does not constitute "
    "financial advice. Consult a SEBI-registered investment adviser or "
    "IRDAI-licensed insurance adviser before making any insurance decisions."
)


# ──────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────

def _fmt(amount: float) -> str:
    """Format a rupee amount in readable Indian units (lakh / crore)."""
    if amount >= 1_00_00_000:
        return f"₹{amount / 1_00_00_000:.1f} crore"
    if amount >= 1_00_000:
        return f"₹{amount / 1_00_000:.1f} lakh"
    return f"₹{amount:,.0f}"


def _family_context(profile: UserProfile) -> str:
    """One-line family description for use in explanations."""
    parts = []
    if profile.spouse:
        parts.append("married")
    if profile.children:
        n = len(profile.children)
        parts.append(f"{n} child{'ren' if n > 1 else ''}")
    if profile.dependent_parents:
        n = len(profile.dependent_parents)
        parts.append(f"{n} dependent parent{'s' if n > 1 else ''}")
    return ", ".join(parts) if parts else "single with no dependents"


def _biggest_gap(
    life_need: LifeCoverNeed,
    health_need: HealthCoverNeed,
    accident_disability_need: AccidentDisabilityNeed,
) -> str:
    """Return the label of the largest absolute coverage gap."""
    gaps = {
        "life cover": life_need.gap,
        "health cover": health_need.gap,
        "accident cover": accident_disability_need.accident_gap,
    }
    return max(gaps, key=lambda k: gaps[k])


# ──────────────────────────────────────────────
# 1. API key loading
# ──────────────────────────────────────────────

def _load_api_key() -> str | None:
    """
    Return the Anthropic API key from the environment, or None if absent.

    None is not an error — it signals generate_explanation() to use the
    template path. The system must work fully without an API key.
    """
    return os.environ.get("ANTHROPIC_API_KEY") or None


# ──────────────────────────────────────────────
# 2. Prompt construction
# ──────────────────────────────────────────────

def _build_prompt(
    profile: UserProfile,
    life_need: LifeCoverNeed,
    health_need: HealthCoverNeed,
    accident_disability_need: AccidentDisabilityNeed,
    policy_audits: list[PolicyAudit],
    action_plan: ActionPlan,
) -> str:
    """
    Build the structured prompt sent to the LLM.

    Structured prompts outperform vague ones because they give the model
    all necessary facts (preventing hallucination) and explicit constraints
    (preventing product recommendations, number contradictions, and advice
    that could create legal liability).
    """
    city = profile.city_tier.value.replace("_", "-").upper()
    family = _family_context(profile)
    urgent = _biggest_gap(life_need, health_need, accident_disability_need)

    investment_audits = [
        a for a in policy_audits
        if a.policy_type in (PolicyType.ULIP, PolicyType.ENDOWMENT)
        and a.efficiency_flag is not None
    ]

    prompt = f"""You are a friendly financial educator helping an Indian family understand their insurance coverage gaps. Explain numbers in plain English. Be warm but direct. Never recommend specific insurers or product names.

USER SITUATION:
- Age: {profile.age} | City: {city} | Family: {family}
- Annual income: {_fmt(profile.annual_income)}
- Monthly insurance budget: {_fmt(profile.monthly_insurance_budget)}

COVERAGE GAPS (do not change these numbers):
Life cover     — Recommended: {_fmt(life_need.recommended_cover)} | Current: {_fmt(life_need.existing_cover)} | Gap: {_fmt(life_need.gap)}
Health cover   — Recommended: {_fmt(health_need.recommended_cover)} | Current: {_fmt(health_need.existing_cover)} | Gap: {_fmt(health_need.gap)}
Accident cover — Recommended: {_fmt(accident_disability_need.recommended_accident_cover)} | Current: {_fmt(accident_disability_need.existing_accident_cover)} | Gap: {_fmt(accident_disability_need.accident_gap)}
"""

    if investment_audits:
        prompt += "\nEXISTING POLICY FINDINGS:\n"
        for a in investment_audits:
            prompt += (
                f"- {a.policy_type.value.title()} policy: implied IRR {a.implied_irr:.1%} "
                f"({a.efficiency_flag.value})"
            )
            if a.opportunity_cost and a.opportunity_cost > 0:
                prompt += f", opportunity cost vs term+index fund: {_fmt(a.opportunity_cost)}"
            prompt += "\n"

    within = action_plan.items_within_budget
    beyond = action_plan.items_beyond_budget

    if within:
        prompt += "\nACTION PLAN — within budget:\n"
        for item in within:
            prompt += (
                f"- {item.policy_type.value.title()} cover {_fmt(item.recommended_cover)} "
                f"(~{_fmt(item.estimated_monthly_premium)}/month)\n"
            )

    if beyond:
        prompt += "\nACTION PLAN — beyond current budget:\n"
        for item in beyond:
            prompt += f"- {item.policy_type.value.title()} cover {_fmt(item.recommended_cover)}\n"
        prompt += f"Additional monthly budget needed: {_fmt(action_plan.monthly_shortfall)}\n"

    prompt += f"""
RULES — follow exactly:
1. Lead with the most urgent gap: {urgent}
2. Never name specific insurers, policies, or products
3. Never contradict or change any of the numbers above
4. No legal or tax advice
5. Under 300 words
6. Write in second person ("you", "your family")
7. End with this exact disclaimer:
   "{_DISCLAIMER}"

Write the explanation now."""

    return prompt


# ──────────────────────────────────────────────
# 3. LLM call
# ──────────────────────────────────────────────

def _call_llm(prompt: str, api_key: str) -> str | None:
    """
    Call the Anthropic API and return the response text.

    Returns None on ANY failure — network error, API error, rate limit,
    empty response, or unexpected exception. Never raises.
    Catching all exceptions is intentional: any failure must trigger the
    template fallback, never crash the assessment pipeline.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        return text if text else None
    except Exception:
        return None


# ──────────────────────────────────────────────
# 4. Template explanation
# ──────────────────────────────────────────────

def _generate_template_explanation(
    profile: UserProfile,
    life_need: LifeCoverNeed,
    health_need: HealthCoverNeed,
    accident_disability_need: AccidentDisabilityNeed,
    policy_audits: list[PolicyAudit],
    action_plan: ActionPlan,
) -> str:
    """
    High-quality template fallback — not a placeholder or apology.

    Covers every output the LLM would generate in a fixed but readable
    structure. Must be genuinely useful to ship on its own.
    """
    city = profile.city_tier.value.replace("_", "-").upper()
    family = _family_context(profile)
    urgent = _biggest_gap(life_need, health_need, accident_disability_need)

    lines: list[str] = []

    # Opening
    lines.append(
        f"You are {profile.age} years old, {family}, living in a {city} city "
        f"with an annual income of {_fmt(profile.annual_income)}."
    )
    lines.append(
        f"Your most urgent coverage gap is {urgent}. "
        "Here is your complete insurance picture."
    )
    lines.append("")

    # Life cover
    lines.append("LIFE COVER")
    if life_need.gap > 0:
        lines.append(
            f"Your family needs {_fmt(life_need.recommended_cover)} in life cover. "
            f"You currently have {_fmt(life_need.existing_cover)}, leaving a gap of "
            f"{_fmt(life_need.gap)}. Without adequate life cover, your family would "
            "struggle to maintain their lifestyle and meet financial obligations "
            "if you were no longer around."
        )
    else:
        lines.append(
            f"Your life cover of {_fmt(life_need.existing_cover)} meets the recommended "
            "level. No action needed here."
        )
    lines.append("")

    # Health cover
    lines.append("HEALTH COVER")
    if health_need.gap > 0:
        lines.append(
            f"In a {city} city, the recommended health cover is "
            f"{_fmt(health_need.recommended_cover)}. You have "
            f"{_fmt(health_need.existing_cover)}, a gap of {_fmt(health_need.gap)}. "
            f"A single major hospitalisation can cost {_fmt(health_need.city_tier_floor)} "
            "or more. With healthcare inflation running at 12-15% annually, "
            "this gap will widen if left unaddressed."
        )
    else:
        lines.append(
            f"Your health cover of {_fmt(health_need.existing_cover)} meets the "
            "recommended level for your city and family size."
        )
    lines.append("")

    # Accident cover
    lines.append("ACCIDENT COVER")
    if accident_disability_need.accident_gap > 0:
        lines.append(
            f"You need {_fmt(accident_disability_need.recommended_accident_cover)} in "
            f"personal accident cover. You have "
            f"{_fmt(accident_disability_need.existing_accident_cover)}, "
            f"a gap of {_fmt(accident_disability_need.accident_gap)}. "
            "Personal accident cover is typically very affordable — "
            "under ₹500/month for meaningful protection."
        )
    else:
        lines.append(
            f"Your accident cover of "
            f"{_fmt(accident_disability_need.existing_accident_cover)} is adequate."
        )
    lines.append("")

    # Policy audit findings
    investment_audits = [
        a for a in policy_audits
        if a.policy_type in (PolicyType.ULIP, PolicyType.ENDOWMENT)
        and a.efficiency_flag is not None
    ]
    if investment_audits:
        lines.append("EXISTING POLICY REVIEW")
        for a in investment_audits:
            if a.efficiency_flag == EfficiencyFlag.INEFFICIENT:
                verdict = (
                    "is earning significantly less than a term insurance + "
                    "index fund alternative"
                )
            elif a.efficiency_flag == EfficiencyFlag.MIXED:
                verdict = "is earning mediocre returns compared to market alternatives"
            else:
                verdict = "is earning reasonable returns"

            lines.append(
                f"Your {a.policy_type.value} policy {verdict} "
                f"(implied annual return: {a.implied_irr:.1%})."
            )
            if a.opportunity_cost and a.opportunity_cost > 0:
                lines.append(
                    f"Staying in this policy may cost you approximately "
                    f"{_fmt(a.opportunity_cost)} compared to a term + index fund strategy. "
                    "Consult a fee-only financial adviser before making any changes — "
                    "do not surrender it without professional guidance on exit charges "
                    "and tax implications."
                )
        lines.append("")

    # Action plan
    lines.append("YOUR ACTION PLAN")
    within = action_plan.items_within_budget
    beyond = action_plan.items_beyond_budget

    if not within and not beyond:
        lines.append(
            "All your coverage gaps are already closed. "
            "Review this assessment every 2-3 years or after any major life event."
        )
    else:
        if within:
            lines.append(
                f"Within your {_fmt(profile.monthly_insurance_budget)}/month budget, "
                "start with:"
            )
            for item in within:
                lines.append(
                    f"  {item.priority_rank}. {item.policy_type.value.title()} cover "
                    f"of {_fmt(item.recommended_cover)} "
                    f"(~{_fmt(item.estimated_monthly_premium)}/month)"
                )
        if beyond:
            lines.append("")
            lines.append(
                "The following gaps require a larger budget — address these "
                "as your income grows:"
            )
            for item in beyond:
                lines.append(
                    f"  - {item.policy_type.value.title()} cover "
                    f"of {_fmt(item.recommended_cover)}"
                )
            lines.append(
                f"An additional {_fmt(action_plan.monthly_shortfall)}/month would "
                "close all remaining gaps."
            )
    lines.append("")

    # Disclaimer
    lines.append(_DISCLAIMER)

    return "\n".join(lines)


# ──────────────────────────────────────────────
# 5. Public function
# ──────────────────────────────────────────────

def generate_explanation(
    profile: UserProfile,
    life_need: LifeCoverNeed,
    health_need: HealthCoverNeed,
    accident_disability_need: AccidentDisabilityNeed,
    policy_audits: list[PolicyAudit],
    action_plan: ActionPlan,
) -> tuple[str, bool]:
    """
    Generate a plain-English explanation of the insurance assessment.

    Returns (explanation_text, used_llm_flag).
    used_llm_flag is True if the Anthropic API produced the text,
    False if the template fallback was used.

    The return type is identical on both paths — the caller (service.py)
    never needs to know which path ran. This is the graceful degradation
    contract: same interface, best available quality.
    """
    api_key = _load_api_key()
    if api_key:
        prompt = _build_prompt(
            profile, life_need, health_need,
            accident_disability_need, policy_audits, action_plan,
        )
        result = _call_llm(prompt, api_key)
        if result:
            return result, True

    fallback = _generate_template_explanation(
        profile, life_need, health_need,
        accident_disability_need, policy_audits, action_plan,
    )
    return fallback, False
