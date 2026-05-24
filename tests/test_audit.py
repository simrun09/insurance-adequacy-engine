import pytest

from engine.audit import audit_all_policies, compute_irr, compute_opportunity_cost
from engine import config
from engine.schemas import (
    AccidentDisabilityNeed,
    CityTier,
    EfficiencyFlag,
    ExistingPolicy,
    Gender,
    HealthCoverNeed,
    LifeCoverNeed,
    PolicyType,
    TaxRegime,
    UserProfile,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_life_need():
    return LifeCoverNeed(
        hlv_based_cover=2_00_00_000,
        nba_based_cover=1_50_00_000,
        recommended_cover=2_00_00_000,
        existing_cover=0,
        gap=2_00_00_000,
        heuristic_10x_cover=1_80_00_000,
    )


@pytest.fixture
def base_health_need():
    return HealthCoverNeed(
        recommended_cover=25_00_000,
        existing_cover=0,
        gap=25_00_000,
        city_tier_floor=25_00_000,
        family_size_adjustment=0,
        age_adjustment=0,
    )


@pytest.fixture
def base_ad_need():
    return AccidentDisabilityNeed(
        recommended_accident_cover=15_00_000,
        existing_accident_cover=0,
        accident_gap=15_00_000,
        recommended_disability_cover=9_00_000,
        existing_disability_cover=0,
        disability_gap=9_00_000,
        disability_via_rider_suggested=True,
    )


def _profile_with(*policies: ExistingPolicy) -> UserProfile:
    """Minimal profile carrying the given existing policies."""
    return UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=18_00_000,
        monthly_expenses=40_000,
        monthly_insurance_budget=10_000,
        tax_regime=TaxRegime.NEW,
        existing_policies=list(policies),
    )


# ---------------------------------------------------------------------------
# compute_irr — basic correctness
# ---------------------------------------------------------------------------

# Maturity value derived from annuity PV formula at exactly 5% so NPV(5%) ≈ 0.
# pv_premiums(5%) = 50000 × 12.4622 = 623,110 → maturity = 623,110 × 1.05^20 = 1,653,298
def test_irr_known_value_5_percent():
    irr = compute_irr(50_000, 20, 16_53_298)
    assert irr is not None
    assert irr == pytest.approx(0.05, abs=1e-3)


# Same approach at 10% over 30 years → maturity = 8,224,701
def test_irr_known_value_10_percent():
    irr = compute_irr(50_000, 30, 82_24_701)
    assert irr is not None
    assert irr == pytest.approx(0.10, abs=1e-3)


def test_irr_returns_none_when_maturity_value_missing():
    assert compute_irr(50_000, 20, None) is None


def test_irr_returns_none_when_years_is_zero():
    assert compute_irr(50_000, 0, 10_00_000) is None


def test_irr_returns_none_when_premium_is_zero():
    assert compute_irr(0, 20, 10_00_000) is None


# ₹30,000/yr · 20yr · maturity ₹9L → IRR ≈ 4%, well below the 7% INEFFICIENT threshold
def test_irr_low_return_policy_is_below_mixed_threshold():
    irr = compute_irr(30_000, 20, 9_00_000)
    assert irr is not None
    assert irr < config.IRR_THRESHOLD_MIXED


# ₹50,000/yr · 20yr · maturity ₹35L → IRR ≈ 11.7%, above the 9% EFFICIENT threshold
def test_irr_high_return_policy_is_above_efficient_threshold():
    irr = compute_irr(50_000, 20, 35_00_000)
    assert irr is not None
    assert irr >= config.IRR_THRESHOLD_EFFICIENT


# Higher maturity value → higher IRR (monotonicity check)
def test_irr_higher_maturity_produces_higher_irr():
    irr_low = compute_irr(50_000, 20, 10_00_000)
    irr_high = compute_irr(50_000, 20, 30_00_000)
    assert irr_high > irr_low


# ---------------------------------------------------------------------------
# compute_opportunity_cost
# ---------------------------------------------------------------------------

# Inefficient policy (IRR ≈ 4%) vs 11% index fund — opportunity cost must be positive
def test_opportunity_cost_positive_for_inefficient_policy():
    irr = compute_irr(50_000, 20, 9_00_000)
    opp_cost = compute_opportunity_cost(50_000, 15, irr)
    assert opp_cost > 0


# Policy IRR (15%) exceeds alternative rate (11%) — user is better off; cost = 0
def test_opportunity_cost_zero_when_policy_beats_alternative():
    opp_cost = compute_opportunity_cost(50_000, 15, policy_irr=0.15)
    assert opp_cost == 0.0


def test_opportunity_cost_zero_when_years_is_zero():
    assert compute_opportunity_cost(50_000, 0, policy_irr=0.05) == 0.0


# Annual premium at or below term estimate → investable ≤ 0 → nothing to compare
def test_opportunity_cost_zero_when_premium_not_above_term_estimate():
    assert compute_opportunity_cost(
        config.TERM_PREMIUM_ANNUAL_ESTIMATE, 10, policy_irr=0.05
    ) == 0.0


# Higher policy IRR → lower opportunity cost (monotonicity)
def test_opportunity_cost_decreases_as_policy_irr_increases():
    base_premium, years = 50_000, 15
    cost_low_irr = compute_opportunity_cost(base_premium, years, policy_irr=0.03)
    cost_high_irr = compute_opportunity_cost(base_premium, years, policy_irr=0.08)
    assert cost_low_irr > cost_high_irr


# ---------------------------------------------------------------------------
# audit_all_policies — term policy (no IRR fields expected)
# ---------------------------------------------------------------------------

def test_term_policy_has_no_irr_or_efficiency_fields(
    base_life_need, base_health_need, base_ad_need
):
    profile = _profile_with(
        ExistingPolicy(
            policy_type=PolicyType.TERM,
            sum_assured=50_00_000,
            annual_premium=14_000,
            start_year=2020,
        )
    )
    audits = audit_all_policies(profile, base_life_need, base_health_need, base_ad_need)
    audit = audits[0]
    assert audit.efficiency_flag is None
    assert audit.implied_irr is None
    assert audit.opportunity_cost is None


# sum_assured exactly equals recommended → adequate, gap = 0
def test_term_policy_adequate_when_sum_assured_meets_recommendation(
    base_health_need, base_ad_need
):
    cover = 2_00_00_000
    life_need = LifeCoverNeed(
        hlv_based_cover=cover, nba_based_cover=1_50_00_000,
        recommended_cover=cover, existing_cover=cover,
        gap=0, heuristic_10x_cover=1_80_00_000,
    )
    profile = _profile_with(
        ExistingPolicy(
            policy_type=PolicyType.TERM,
            sum_assured=cover,
            annual_premium=18_000,
            start_year=2020,
        )
    )
    audits = audit_all_policies(profile, life_need, base_health_need, base_ad_need)
    assert audits[0].is_adequate is True
    assert audits[0].adequacy_gap == 0.0


# sum_assured below recommended → inadequate, gap > 0
def test_term_policy_inadequate_when_sum_assured_below_recommendation(
    base_health_need, base_ad_need
):
    life_need = LifeCoverNeed(
        hlv_based_cover=2_00_00_000, nba_based_cover=1_50_00_000,
        recommended_cover=2_00_00_000, existing_cover=50_00_000,
        gap=1_50_00_000, heuristic_10x_cover=1_80_00_000,
    )
    profile = _profile_with(
        ExistingPolicy(
            policy_type=PolicyType.TERM,
            sum_assured=50_00_000,
            annual_premium=8_000,
            start_year=2022,
        )
    )
    audits = audit_all_policies(profile, life_need, base_health_need, base_ad_need)
    assert audits[0].is_adequate is False
    assert audits[0].adequacy_gap == pytest.approx(1_50_00_000)


# ---------------------------------------------------------------------------
# audit_all_policies — endowment / ULIP verdict
# ---------------------------------------------------------------------------

# Endowment: ₹50,000/yr · 30yr (2010→2040) · maturity ₹33.2L → IRR ≈ 5% → INEFFICIENT
def test_inefficient_endowment_gets_inefficient_flag(
    base_life_need, base_health_need, base_ad_need
):
    profile = _profile_with(
        ExistingPolicy(
            policy_type=PolicyType.ENDOWMENT,
            sum_assured=10_00_000,
            annual_premium=50_000,
            start_year=2010,
            maturity_year=2040,
            maturity_value=33_20_000,   # implied IRR ≈ 5% < 7%
        )
    )
    audits = audit_all_policies(profile, base_life_need, base_health_need, base_ad_need)
    assert audits[0].efficiency_flag == EfficiencyFlag.INEFFICIENT
    assert audits[0].implied_irr < config.IRR_THRESHOLD_MIXED


# Endowment: ₹50,000/yr · 30yr (2010→2040) · maturity ₹82.2L → IRR ≈ 10% → EFFICIENT
def test_efficient_endowment_gets_efficient_flag(
    base_life_need, base_health_need, base_ad_need
):
    profile = _profile_with(
        ExistingPolicy(
            policy_type=PolicyType.ENDOWMENT,
            sum_assured=10_00_000,
            annual_premium=50_000,
            start_year=2010,
            maturity_year=2040,
            maturity_value=82_24_701,   # implied IRR ≈ 10% >= 9%
        )
    )
    audits = audit_all_policies(profile, base_life_need, base_health_need, base_ad_need)
    assert audits[0].efficiency_flag == EfficiencyFlag.EFFICIENT
    assert audits[0].implied_irr >= config.IRR_THRESHOLD_EFFICIENT


# Inefficient policy → opportunity_cost must be a positive rupee amount
def test_inefficient_endowment_has_positive_opportunity_cost(
    base_life_need, base_health_need, base_ad_need
):
    profile = _profile_with(
        ExistingPolicy(
            policy_type=PolicyType.ENDOWMENT,
            sum_assured=10_00_000,
            annual_premium=50_000,
            start_year=2010,
            maturity_year=2040,
            maturity_value=33_20_000,
        )
    )
    audits = audit_all_policies(profile, base_life_need, base_health_need, base_ad_need)
    assert audits[0].opportunity_cost is not None
    assert audits[0].opportunity_cost > 0


# Missing maturity data → efficiency cannot be computed → all IRR fields are None
def test_endowment_without_maturity_data_has_no_efficiency_flag(
    base_life_need, base_health_need, base_ad_need
):
    profile = _profile_with(
        ExistingPolicy(
            policy_type=PolicyType.ENDOWMENT,
            sum_assured=10_00_000,
            annual_premium=50_000,
            start_year=2015,
        )
    )
    audits = audit_all_policies(profile, base_life_need, base_health_need, base_ad_need)
    assert audits[0].efficiency_flag is None
    assert audits[0].implied_irr is None
    assert audits[0].opportunity_cost is None


# ULIP gets the same IRR treatment as endowment
def test_ulip_with_low_irr_gets_inefficient_flag(
    base_life_need, base_health_need, base_ad_need
):
    profile = _profile_with(
        ExistingPolicy(
            policy_type=PolicyType.ULIP,
            sum_assured=10_00_000,
            annual_premium=60_000,
            start_year=2012,
            maturity_year=2040,
            maturity_value=40_00_000,   # IRR will be < 7%
        )
    )
    audits = audit_all_policies(profile, base_life_need, base_health_need, base_ad_need)
    assert audits[0].efficiency_flag in (EfficiencyFlag.INEFFICIENT, EfficiencyFlag.MIXED)


# ---------------------------------------------------------------------------
# audit_all_policies — list handling
# ---------------------------------------------------------------------------

# One result per policy in the profile
def test_returns_one_audit_per_policy(base_life_need, base_health_need, base_ad_need):
    profile = _profile_with(
        ExistingPolicy(
            policy_type=PolicyType.TERM,
            sum_assured=50_00_000,
            annual_premium=12_000,
            start_year=2020,
        ),
        ExistingPolicy(
            policy_type=PolicyType.HEALTH,
            sum_assured=5_00_000,
            annual_premium=12_000,
            start_year=2021,
        ),
    )
    audits = audit_all_policies(profile, base_life_need, base_health_need, base_ad_need)
    assert len(audits) == 2


# Empty policy list → empty audit list
def test_empty_policies_returns_empty_list(base_life_need, base_health_need, base_ad_need):
    profile = UserProfile(
        age=35, gender=Gender.MALE, city_tier=CityTier.TIER_1,
        annual_income=18_00_000, monthly_expenses=40_000,
        monthly_insurance_budget=10_000, tax_regime=TaxRegime.NEW,
    )
    assert audit_all_policies(profile, base_life_need, base_health_need, base_ad_need) == []


# Adequacy gap is always non-negative
def test_adequacy_gap_never_negative(base_life_need, base_health_need, base_ad_need):
    profile = _profile_with(
        ExistingPolicy(
            policy_type=PolicyType.TERM,
            sum_assured=10_00_00_000,   # 10 crore — far exceeds any recommendation
            annual_premium=1_00_000,
            start_year=2018,
        )
    )
    audits = audit_all_policies(profile, base_life_need, base_health_need, base_ad_need)
    assert audits[0].adequacy_gap == 0.0
    assert audits[0].is_adequate is True
