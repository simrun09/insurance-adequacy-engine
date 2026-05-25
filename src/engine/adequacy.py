"""
Adequacy scorers for the Insurance Adequacy Engine.

All functions are pure: they take data, return data, no side effects, no I/O.
All tunable values are imported from config — no magic numbers in this module.
"""

import datetime

from . import config
from .schemas import (
    AccidentDisabilityNeed,
    CityTier,
    HealthCoverNeed,
    LifeCoverNeed,
    PolicyType,
    UserProfile,
)


def compute_hlv(profile: UserProfile) -> float:
    """
    Human Life Value (HLV) — Income Replacement Method.

    Computes the present value of the income stream the user's family would
    lose if the user died today. Uses the Present Value of Annuity formula.

    Formula (FR-2):
        surplus        = annual_income - (monthly_expenses × 12)
        working_years  = RETIREMENT_AGE - age
        HLV            = surplus × [1 - (1 + r)^(-n)] / r

    Source: IRDAI consumer education guidelines; CFP Institute of India.
    Discount rate r = 6% (config.DISCOUNT_RATE), IRDAI midpoint guidance.
    """
    working_years = config.RETIREMENT_AGE - profile.age
    if working_years <= 0:
        return 0.0

    annual_surplus = profile.annual_income - (profile.monthly_expenses * 12)
    if annual_surplus <= 0:
        return 0.0

    r = config.DISCOUNT_RATE
    pv_annuity = annual_surplus * (1 - (1 + r) ** (-working_years)) / r
    return round(pv_annuity, 2)


def compute_nba(profile: UserProfile) -> float:
    """
    Need-Based Analysis (NBA) — Obligation Coverage Method.

    Sums all financial obligations the family must meet if the user dies today,
    then subtracts existing assets. The result is the net funding gap.

    Formula (FR-2):
        gross = liabilities + pv(future_expenses) + emergency_corpus
                + spouse_retirement_corpus
        NBA   = max(0, gross - investable_assets - epf_ppf_balance)

    Future expenses are discounted to PV at config.DISCOUNT_RATE because a
    rupee needed 10 years from now is worth less than a rupee today.
    Spouse retirement corpus is added only for non-earning spouses — an
    earning spouse can support themselves.
    """
    current_year = datetime.date.today().year
    r = config.DISCOUNT_RATE

    # Step 1: outstanding loan balances (already in present-value rupees)
    liabilities = sum(loan.outstanding_balance for loan in profile.loans)

    # Step 2: future obligations discounted to present value
    obligations = 0.0
    for expense in profile.future_expenses:
        years_away = expense.target_year - current_year
        if years_away > 0:
            obligations += expense.estimated_amount / (1 + r) ** years_away
        else:
            obligations += expense.estimated_amount  # already due; no discount

    # Step 3: emergency corpus — 6 months of household expenses
    emergency_corpus = profile.monthly_expenses * config.EMERGENCY_MONTHS

    # Step 4: spouse retirement corpus for non-earning surviving spouse
    spouse_corpus = 0.0
    if profile.spouse and profile.spouse.annual_income == 0:
        spouse_retirement_years = max(0, config.RETIREMENT_AGE - profile.spouse.age)
        annual_household_expenses = profile.monthly_expenses * 12
        spouse_corpus = annual_household_expenses * spouse_retirement_years

    gross_need = liabilities + obligations + emergency_corpus + spouse_corpus
    net_nba = gross_need - profile.investable_assets - profile.epf_ppf_balance
    return round(max(0.0, net_nba), 2)


def recommend_life_cover(profile: UserProfile) -> LifeCoverNeed:
    """
    Aggregate life cover recommendation — takes max(HLV, NBA) per FR-2.

    Existing cover is the sum of all declared TERM policies only. Endowment
    and ULIP policies are excluded: their primary purpose is investment, not
    protection, and their death benefit is unreliable as a cover proxy.

    The 10x heuristic is stored for educational display only — it never
    influences the recommendation.
    """
    hlv = compute_hlv(profile)
    nba = compute_nba(profile)
    recommended = max(hlv, nba)

    existing_cover = sum(
        p.sum_assured
        for p in profile.existing_policies
        if p.policy_type == PolicyType.TERM
    )

    return LifeCoverNeed(
        hlv_based_cover=hlv,
        nba_based_cover=nba,
        recommended_cover=recommended,
        existing_cover=existing_cover,
        gap=round(max(0.0, recommended - existing_cover), 2),
        heuristic_10x_cover=profile.annual_income * 10,
    )


def compute_health_cover_need(profile: UserProfile) -> HealthCoverNeed:
    """
    Health cover recommendation — city-tier-anchored, family-size-scaled (FR-3).

    Base is the recommended floor for the user's city tier, not a percentage of
    income. Each additional family member on the floater adds 5 lakh. Users
    above age 45 receive a 20% buffer on the running subtotal.

    Sources: Niva Bupa, Ditto, ManipalCigna insurer publications for tier floors;
    IRDAI annual report (claims frequency by age band) for the age buffer.
    """
    # Step 1: city-tier base
    if profile.city_tier == CityTier.TIER_1:
        base = config.HEALTH_RECOMMENDED_TIER_1
    elif profile.city_tier == CityTier.TIER_2:
        base = config.HEALTH_RECOMMENDED_TIER_2
    else:
        base = config.HEALTH_RECOMMENDED_TIER_3

    # Step 2: family size adjustment — user is the base; each dependent adds 5L
    additional_members = (
        (1 if profile.spouse else 0)
        + len(profile.children)
        + len(profile.dependent_parents)
    )
    family_adjustment = additional_members * config.HEALTH_PER_MEMBER_ADDITION

    # Step 3: age adjustment — 20% buffer on running subtotal if age > 45
    age_adjustment = 0.0
    if profile.age > config.HEALTH_AGE_THRESHOLD:
        age_adjustment = (base + family_adjustment) * config.HEALTH_AGE_BUFFER

    recommended = base + family_adjustment + age_adjustment

    # Step 4: gap against existing health policies
    existing_cover = sum(
        p.sum_assured
        for p in profile.existing_policies
        if p.policy_type == PolicyType.HEALTH
    )

    return HealthCoverNeed(
        recommended_cover=round(recommended, 2),
        existing_cover=existing_cover,
        gap=round(max(0.0, recommended - existing_cover), 2),
        city_tier_floor=base,
        family_size_adjustment=family_adjustment,
        age_adjustment=round(age_adjustment, 2),
    )


def compute_accident_disability_need(profile: UserProfile) -> AccidentDisabilityNeed:
    """
    Accident and disability cover recommendations (FR-4).

    Accident cover: 10x monthly income as a lump sum (Personal Accident policy).
    Disability cover: 50% of annual income as income replacement.

    Both are flat income-derived heuristics — no city-tier or age adjustment,
    as the product pricing and availability are uniform across demographics.

    disability_via_rider_suggested is always True: standalone disability income
    products are rare in India; a rider on the term policy is the practical route.
    """
    monthly_income = profile.annual_income / 12

    recommended_accident = monthly_income * config.ACCIDENT_COVER_MULTIPLIER
    recommended_disability = profile.annual_income * config.DISABILITY_INCOME_RATIO

    existing_accident = sum(
        p.sum_assured
        for p in profile.existing_policies
        if p.policy_type == PolicyType.ACCIDENT
    )
    existing_disability = sum(
        p.sum_assured
        for p in profile.existing_policies
        if p.policy_type == PolicyType.DISABILITY
    )

    return AccidentDisabilityNeed(
        recommended_accident_cover=round(recommended_accident, 2),
        existing_accident_cover=existing_accident,
        accident_gap=round(max(0.0, recommended_accident - existing_accident), 2),
        recommended_disability_cover=round(recommended_disability, 2),
        existing_disability_cover=existing_disability,
        disability_gap=round(max(0.0, recommended_disability - existing_disability), 2),
        disability_via_rider_suggested=True,
    )
