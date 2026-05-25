import pytest

from engine import config
from engine.prioritizer import build_action_plan, estimate_monthly_premium
from engine.schemas import (
    AccidentDisabilityNeed,
    Child,
    CityTier,
    Gender,
    HealthCoverNeed,
    LifeCoverNeed,
    PolicyType,
    Spouse,
    TaxRegime,
    UserProfile,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def family_profile():
    """Married, two children, ₹18L income — default priority order applies (term first)."""
    return UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=18_00_000,
        monthly_expenses=50_000,
        monthly_insurance_budget=10_000,
        tax_regime=TaxRegime.NEW,
        spouse=Spouse(age=32, annual_income=0),
        children=[Child(age=5), Child(age=3)],
    )


@pytest.fixture
def single_profile():
    """No spouse, no children, no dependent parents — no-dependents override applies."""
    return UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=18_00_000,
        monthly_expenses=50_000,
        monthly_insurance_budget=10_000,
        tax_regime=TaxRegime.NEW,
    )


def _needs(
    life_gap: float = 1_50_00_000,
    health_gap: float = 20_00_000,
    health_existing: float = 5_00_000,
    accident_gap: float = 15_00_000,
):
    """Build LifeCoverNeed / HealthCoverNeed / AccidentDisabilityNeed with given gaps."""
    life_need = LifeCoverNeed(
        hlv_based_cover=2_00_00_000,
        nba_based_cover=1_50_00_000,
        recommended_cover=2_00_00_000,
        existing_cover=max(0.0, 2_00_00_000 - life_gap),
        gap=life_gap,
        heuristic_10x_cover=1_80_00_000,
    )
    health_need = HealthCoverNeed(
        recommended_cover=25_00_000,
        existing_cover=health_existing,
        gap=health_gap,
        city_tier_floor=25_00_000,
        family_size_adjustment=0,
        age_adjustment=0,
    )
    ad_need = AccidentDisabilityNeed(
        recommended_accident_cover=15_00_000,
        existing_accident_cover=0,
        accident_gap=accident_gap,
        recommended_disability_cover=9_00_000,
        existing_disability_cover=0,
        disability_gap=9_00_000,
        disability_via_rider_suggested=True,
    )
    return life_need, health_need, ad_need


def _ordered_types(plan):
    """Return policy types from a plan in priority order (within first, then beyond)."""
    return [i.policy_type for i in plan.items_within_budget + plan.items_beyond_budget]


# ---------------------------------------------------------------------------
# estimate_monthly_premium
# ---------------------------------------------------------------------------


# Term scales with sum_assured: double the cover → double the premium (within rounding)
def test_term_premium_scales_with_sum_assured(family_profile):
    small = estimate_monthly_premium(PolicyType.TERM, 50_00_000, family_profile)
    large = estimate_monthly_premium(PolicyType.TERM, 1_00_00_000, family_profile)
    assert large == pytest.approx(small * 2, abs=0.02)


# ₹1 crore term: (100 × ₹10/lakh/yr) / 12 ≈ ₹83.33/month
def test_term_premium_known_value(family_profile):
    result = estimate_monthly_premium(PolicyType.TERM, 1_00_00_000, family_profile)
    expected = (100 * config.TERM_PREMIUM_PER_LAKH_ANNUAL) / 12
    assert result == pytest.approx(expected, abs=0.01)


# Health is a flat bucket — two different sum_assured values give the same premium
def test_health_premium_does_not_scale_with_sum_assured(family_profile):
    low = estimate_monthly_premium(PolicyType.HEALTH, 5_00_000, family_profile)
    high = estimate_monthly_premium(PolicyType.HEALTH, 25_00_000, family_profile)
    assert low == high


# Profile with spouse/children → family floater bucket
def test_health_premium_uses_family_floater_for_family(family_profile):
    result = estimate_monthly_premium(PolicyType.HEALTH, 25_00_000, family_profile)
    expected = config.HEALTH_PREMIUM_ANNUAL_APPROX["family_floater"] / 12
    assert result == pytest.approx(expected, abs=0.01)


# Single, age 35 → individual_mid bucket (35 ≤ age ≤ 45)
def test_health_premium_uses_individual_mid_for_single_age_35(single_profile):
    result = estimate_monthly_premium(PolicyType.HEALTH, 25_00_000, single_profile)
    expected = config.HEALTH_PREMIUM_ANNUAL_APPROX["individual_mid"] / 12
    assert result == pytest.approx(expected, abs=0.01)


# Single, age < 35 → individual_young bucket
def test_health_premium_uses_individual_young_for_age_under_35():
    young_profile = UserProfile(
        age=30,
        gender=Gender.FEMALE,
        city_tier=CityTier.TIER_1,
        annual_income=10_00_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    result = estimate_monthly_premium(PolicyType.HEALTH, 25_00_000, young_profile)
    expected = config.HEALTH_PREMIUM_ANNUAL_APPROX["individual_young"] / 12
    assert result == pytest.approx(expected, abs=0.01)


# Single, age > 45 → individual_senior bucket
def test_health_premium_uses_individual_senior_for_age_over_45():
    senior_profile = UserProfile(
        age=50,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=20_00_000,
        monthly_expenses=60_000,
        monthly_insurance_budget=15_000,
        tax_regime=TaxRegime.NEW,
    )
    result = estimate_monthly_premium(PolicyType.HEALTH, 25_00_000, senior_profile)
    expected = config.HEALTH_PREMIUM_ANNUAL_APPROX["individual_senior"] / 12
    assert result == pytest.approx(expected, abs=0.01)


# Disability is a rider — never a standalone purchase
def test_disability_premium_is_always_zero(family_profile):
    assert (
        estimate_monthly_premium(PolicyType.DISABILITY, 9_00_000, family_profile) == 0.0
    )


# Zero sum_assured → zero premium
def test_zero_sum_assured_returns_zero(family_profile):
    assert estimate_monthly_premium(PolicyType.TERM, 0, family_profile) == 0.0


# ---------------------------------------------------------------------------
# build_action_plan — default priority order (family, existing health cover present)
# ---------------------------------------------------------------------------


# Term must appear before health in the default order
def test_default_priority_term_before_health(family_profile):
    life_need, health_need, ad_need = _needs(health_existing=5_00_000)
    plan = build_action_plan(life_need, health_need, ad_need, family_profile)
    types = _ordered_types(plan)
    assert types.index(PolicyType.TERM) < types.index(PolicyType.HEALTH)


# Health must appear before accident in the default order
def test_default_priority_health_before_accident(family_profile):
    life_need, health_need, ad_need = _needs(health_existing=5_00_000)
    plan = build_action_plan(life_need, health_need, ad_need, family_profile)
    types = _ordered_types(plan)
    assert types.index(PolicyType.HEALTH) < types.index(PolicyType.ACCIDENT)


# Disability never appears in the action plan — it is always a rider
def test_disability_never_appears_in_action_plan(family_profile):
    life_need, health_need, ad_need = _needs()
    plan = build_action_plan(life_need, health_need, ad_need, family_profile)
    types = _ordered_types(plan)
    assert PolicyType.DISABILITY not in types


# ---------------------------------------------------------------------------
# build_action_plan — health-first override
# ---------------------------------------------------------------------------


# When existing_cover == 0, health must come before term
def test_health_first_override_triggers_when_no_existing_health_cover(family_profile):
    life_need, health_need, ad_need = _needs(health_existing=0)
    plan = build_action_plan(life_need, health_need, ad_need, family_profile)
    types = _ordered_types(plan)
    assert types.index(PolicyType.HEALTH) < types.index(PolicyType.TERM)


# When existing_cover > 0, override does NOT trigger — term stays first
def test_health_first_override_does_not_trigger_with_existing_health_cover(
    family_profile,
):
    life_need, health_need, ad_need = _needs(health_existing=5_00_000)
    plan = build_action_plan(life_need, health_need, ad_need, family_profile)
    types = _ordered_types(plan)
    assert types.index(PolicyType.TERM) < types.index(PolicyType.HEALTH)


# ---------------------------------------------------------------------------
# build_action_plan — no-dependents override
# ---------------------------------------------------------------------------


# Single person with no health cover: both overrides apply → HEALTH, ACCIDENT, TERM
def test_no_dependents_override_term_appears_last_with_no_health_cover(single_profile):
    life_need, health_need, ad_need = _needs(health_existing=0)
    plan = build_action_plan(life_need, health_need, ad_need, single_profile)
    types = _ordered_types(plan)
    assert types[-1] == PolicyType.TERM


# Single person with existing health cover: ACCIDENT before TERM
def test_no_dependents_override_accident_before_term_when_health_covered(
    single_profile,
):
    life_need, health_need, ad_need = _needs(health_existing=25_00_000, health_gap=0)
    plan = build_action_plan(life_need, health_need, ad_need, single_profile)
    types = _ordered_types(plan)
    assert types.index(PolicyType.ACCIDENT) < types.index(PolicyType.TERM)


# Family profile does NOT get the no-dependents override
def test_family_profile_does_not_drop_term_to_last(family_profile):
    life_need, health_need, ad_need = _needs(health_existing=5_00_000)
    plan = build_action_plan(life_need, health_need, ad_need, family_profile)
    types = _ordered_types(plan)
    assert types[0] == PolicyType.TERM


# ---------------------------------------------------------------------------
# build_action_plan — budget constraint
# ---------------------------------------------------------------------------


# With ₹500 budget:
#   Term: (150 × ₹10/lakh/yr) / 12 = ₹125/month → fits
#   Health (family floater): ₹20,000/12 = ₹1,667/month → pushes total over ₹500
def test_budget_split_term_within_health_beyond():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=18_00_000,
        monthly_expenses=50_000,
        monthly_insurance_budget=500,  # tight budget
        tax_regime=TaxRegime.NEW,
        spouse=Spouse(age=32, annual_income=0),
        children=[Child(age=5)],
    )
    life_need, health_need, ad_need = _needs(health_existing=5_00_000)
    plan = build_action_plan(life_need, health_need, ad_need, profile)

    within_types = [i.policy_type for i in plan.items_within_budget]
    beyond_types = [i.policy_type for i in plan.items_beyond_budget]
    assert PolicyType.TERM in within_types
    assert PolicyType.HEALTH in beyond_types


# Cumulative on every within-budget item must not exceed the monthly budget
def test_within_budget_cumulative_never_exceeds_budget():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=18_00_000,
        monthly_expenses=50_000,
        monthly_insurance_budget=500,
        tax_regime=TaxRegime.NEW,
        spouse=Spouse(age=32, annual_income=0),
        children=[Child(age=5)],
    )
    life_need, health_need, ad_need = _needs(health_existing=5_00_000)
    plan = build_action_plan(life_need, health_need, ad_need, profile)

    for item in plan.items_within_budget:
        assert item.cumulative_premium <= profile.monthly_insurance_budget


# total_monthly_premium_required equals sum of all individual item premiums
def test_total_premium_required_matches_sum_of_all_items(family_profile):
    life_need, health_need, ad_need = _needs(health_existing=5_00_000)
    plan = build_action_plan(life_need, health_need, ad_need, family_profile)

    all_items = plan.items_within_budget + plan.items_beyond_budget
    total = sum(i.estimated_monthly_premium for i in all_items)
    assert plan.total_monthly_premium_required == pytest.approx(total, abs=0.01)


# monthly_shortfall = max(0, total_required - budget)
def test_monthly_shortfall_equals_excess_over_budget():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=18_00_000,
        monthly_expenses=50_000,
        monthly_insurance_budget=500,
        tax_regime=TaxRegime.NEW,
        spouse=Spouse(age=32, annual_income=0),
        children=[Child(age=5)],
    )
    life_need, health_need, ad_need = _needs(health_existing=5_00_000)
    plan = build_action_plan(life_need, health_need, ad_need, profile)

    expected = max(0.0, plan.total_monthly_premium_required - 500)
    assert plan.monthly_shortfall == pytest.approx(expected, abs=0.01)


# priority_rank is sequential starting from 1 across all items
def test_priority_rank_is_sequential(family_profile):
    life_need, health_need, ad_need = _needs(health_existing=5_00_000)
    plan = build_action_plan(life_need, health_need, ad_need, family_profile)

    all_items = plan.items_within_budget + plan.items_beyond_budget
    ranks = [item.priority_rank for item in all_items]
    assert ranks == list(range(1, len(ranks) + 1))


# ---------------------------------------------------------------------------
# build_action_plan — zero gap case
# ---------------------------------------------------------------------------


def test_zero_gaps_produce_empty_plan(family_profile):
    life_need = LifeCoverNeed(
        hlv_based_cover=2_00_00_000,
        nba_based_cover=1_50_00_000,
        recommended_cover=2_00_00_000,
        existing_cover=2_00_00_000,
        gap=0,
        heuristic_10x_cover=1_80_00_000,
    )
    health_need = HealthCoverNeed(
        recommended_cover=25_00_000,
        existing_cover=25_00_000,
        gap=0,
        city_tier_floor=25_00_000,
        family_size_adjustment=0,
        age_adjustment=0,
    )
    ad_need = AccidentDisabilityNeed(
        recommended_accident_cover=15_00_000,
        existing_accident_cover=15_00_000,
        accident_gap=0,
        recommended_disability_cover=9_00_000,
        existing_disability_cover=9_00_000,
        disability_gap=0,
        disability_via_rider_suggested=True,
    )
    plan = build_action_plan(life_need, health_need, ad_need, family_profile)

    assert plan.items_within_budget == []
    assert plan.items_beyond_budget == []
    assert plan.total_monthly_premium_required == 0.0
    assert plan.monthly_shortfall == 0.0


# Zero budget → all items go beyond budget
def test_zero_budget_sends_all_items_beyond_budget():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=18_00_000,
        monthly_expenses=50_000,
        monthly_insurance_budget=0,
        tax_regime=TaxRegime.NEW,
        spouse=Spouse(age=32, annual_income=0),
        children=[Child(age=5)],
    )
    life_need, health_need, ad_need = _needs(health_existing=5_00_000)
    plan = build_action_plan(life_need, health_need, ad_need, profile)

    assert plan.items_within_budget == []
    assert len(plan.items_beyond_budget) > 0
