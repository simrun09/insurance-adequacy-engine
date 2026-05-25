import pytest

from engine.adequacy import (
    compute_accident_disability_need,
    compute_health_cover_need,
    compute_hlv,
    compute_nba,
    recommend_life_cover,
)
from engine.schemas import (
    Child,
    CityTier,
    ExistingPolicy,
    FutureExpense,
    Gender,
    Loan,
    PolicyType,
    Spouse,
    TaxRegime,
    UserProfile,
)


# ---------------------------------------------------------------------------
# FIXTURES — reusable profiles
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_profile():
    """Single earner, no family, no loans, no policies — the bare minimum."""
    return UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,  # 12 lakh/year
        monthly_expenses=30_000,
        monthly_insurance_budget=10_000,
        tax_regime=TaxRegime.NEW,
    )


@pytest.fixture
def full_profile():
    """Married, two kids, home loan, future expenses, existing term + health policy."""
    return UserProfile(
        age=38,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_800_000,  # 18 lakh/year
        monthly_expenses=60_000,
        monthly_insurance_budget=15_000,
        tax_regime=TaxRegime.OLD,
        spouse=Spouse(age=35, annual_income=0),  # non-earning spouse
        children=[Child(age=8), Child(age=5)],
        loans=[
            Loan(
                loan_type="home loan",
                outstanding_balance=6_000_000,
                remaining_tenure_years=18,
            )
        ],
        future_expenses=[
            FutureExpense(
                description="elder child education",
                estimated_amount=2_000_000,
                target_year=2035,
            ),
        ],
        investable_assets=1_000_000,
        epf_ppf_balance=500_000,
        existing_policies=[
            ExistingPolicy(
                policy_type=PolicyType.TERM,
                sum_assured=5_000_000,
                annual_premium=14_000,
                start_year=2021,
            ),
            ExistingPolicy(
                policy_type=PolicyType.HEALTH,
                sum_assured=500_000,
                annual_premium=18_000,
                start_year=2020,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# compute_hlv
# ---------------------------------------------------------------------------


# Standard mid-career professional: 12L income, 3.6L personal spend, 25 years to retire
# surplus = 8.4L/year; PV annuity at 6% over 25 years ≈ 1.07 crore
def test_hlv_standard_profile_returns_expected_range(minimal_profile):
    result = compute_hlv(minimal_profile)
    assert 10_000_000 <= result <= 11_500_000  # ~1.0–1.15 crore


# HLV is always a non-negative float
def test_hlv_returns_float(minimal_profile):
    result = compute_hlv(minimal_profile)
    assert isinstance(result, float)
    assert result >= 0


# Zero income → no family income stream to replace → HLV = 0
def test_hlv_zero_income_returns_zero():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=0,
        monthly_expenses=0,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    assert compute_hlv(profile) == 0.0


# Expenses equal to income → surplus ≤ 0 → nothing for family → HLV = 0
def test_hlv_expenses_exceed_income_returns_zero():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=600_000,  # 6L income
        monthly_expenses=60_000,  # 7.2L annual expenses
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    assert compute_hlv(profile) == 0.0


# Age at retirement → 0 working years → HLV = 0
def test_hlv_at_retirement_age_returns_zero():
    profile = UserProfile(
        age=60,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    assert compute_hlv(profile) == 0.0


# Age past retirement → still 0, not negative
def test_hlv_past_retirement_age_returns_zero():
    profile = UserProfile(
        age=65,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    assert compute_hlv(profile) == 0.0


# Higher income → higher HLV (monotonicity check)
def test_hlv_higher_income_produces_higher_value():
    base = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    richer = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=2_400_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    assert compute_hlv(richer) > compute_hlv(base)


# Younger user has more working years → higher HLV than older user with same income
def test_hlv_younger_user_produces_higher_value():
    young = UserProfile(
        age=30,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    older = UserProfile(
        age=50,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    assert compute_hlv(young) > compute_hlv(older)


# ---------------------------------------------------------------------------
# compute_nba
# ---------------------------------------------------------------------------


# Home loan + future expense + emergency corpus − assets → positive NBA
def test_nba_standard_profile_returns_positive(full_profile):
    result = compute_nba(full_profile)
    assert result > 0


# NBA is always a non-negative float (never below zero)
def test_nba_returns_non_negative_float(full_profile):
    result = compute_nba(full_profile)
    assert isinstance(result, float)
    assert result >= 0


# When assets comfortably cover all obligations, NBA is clamped to 0
def test_nba_wealthy_profile_returns_zero():
    profile = UserProfile(
        age=45,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=5_000_000,
        monthly_expenses=100_000,
        monthly_insurance_budget=20_000,
        tax_regime=TaxRegime.NEW,
        investable_assets=50_000_000,  # 5 crore — covers everything
        epf_ppf_balance=10_000_000,
    )
    assert compute_nba(profile) == 0.0


# Non-earning spouse adds a retirement corpus; removing them must lower the NBA
def test_nba_non_earning_spouse_increases_nba():
    base = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=40_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
        loans=[
            Loan(
                loan_type="home loan",
                outstanding_balance=3_000_000,
                remaining_tenure_years=15,
            )
        ],
    )
    with_spouse = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=40_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
        loans=[
            Loan(
                loan_type="home loan",
                outstanding_balance=3_000_000,
                remaining_tenure_years=15,
            )
        ],
        spouse=Spouse(age=30, annual_income=0),  # non-earning
    )
    assert compute_nba(with_spouse) > compute_nba(base)


# Earning spouse does NOT add a retirement corpus (they are financially independent)
def test_nba_earning_spouse_does_not_add_corpus():
    without_spouse = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=40_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    with_earning_spouse = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=40_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
        spouse=Spouse(age=33, annual_income=900_000),  # earns own income
    )
    assert compute_nba(with_earning_spouse) == compute_nba(without_spouse)


# More loans → higher NBA (monotonicity for liabilities)
def test_nba_larger_loan_produces_higher_nba():
    small_loan = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
        loans=[
            Loan(
                loan_type="home loan",
                outstanding_balance=2_000_000,
                remaining_tenure_years=10,
            )
        ],
    )
    large_loan = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
        loans=[
            Loan(
                loan_type="home loan",
                outstanding_balance=8_000_000,
                remaining_tenure_years=20,
            )
        ],
    )
    assert compute_nba(large_loan) > compute_nba(small_loan)


# No loans, no future expenses, no spouse, no assets → NBA = emergency corpus only
def test_nba_minimal_profile_equals_emergency_corpus():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    # emergency corpus = 30,000 × 6 = 1,80,000
    expected = 30_000 * 6
    assert compute_nba(profile) == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# recommend_life_cover
# ---------------------------------------------------------------------------


# recommended_cover must equal max(HLV, NBA)
def test_recommend_life_cover_is_max_of_hlv_and_nba(minimal_profile):
    result = recommend_life_cover(minimal_profile)
    assert result.recommended_cover == max(
        result.hlv_based_cover, result.nba_based_cover
    )


# With a large home loan, NBA should dominate over HLV for a typical profile
def test_recommend_life_cover_nba_dominates_with_large_loan():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=600_000,  # modest income → low HLV
        monthly_expenses=20_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
        loans=[
            Loan(
                loan_type="home loan",
                outstanding_balance=8_000_000,
                remaining_tenure_years=20,
            )
        ],
    )
    result = recommend_life_cover(profile)
    assert result.nba_based_cover > result.hlv_based_cover
    assert result.recommended_cover == result.nba_based_cover


# Existing TERM policy reduces the gap correctly
def test_recommend_life_cover_existing_term_reduces_gap():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=10_000,
        tax_regime=TaxRegime.NEW,
        existing_policies=[
            ExistingPolicy(
                policy_type=PolicyType.TERM,
                sum_assured=5_000_000,
                annual_premium=12_000,
                start_year=2022,
            )
        ],
    )
    result = recommend_life_cover(profile)
    assert result.existing_cover == 5_000_000
    assert result.gap == pytest.approx(
        max(0.0, result.recommended_cover - 5_000_000), rel=1e-4
    )


# ULIP and endowment policies must NOT be counted as existing life cover
def test_recommend_life_cover_excludes_ulip_and_endowment():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=10_000,
        tax_regime=TaxRegime.NEW,
        existing_policies=[
            ExistingPolicy(
                policy_type=PolicyType.ULIP,
                sum_assured=1_000_000,
                annual_premium=50_000,
                start_year=2018,
                maturity_year=2030,
                maturity_value=1_800_000,
            ),
            ExistingPolicy(
                policy_type=PolicyType.ENDOWMENT,
                sum_assured=500_000,
                annual_premium=30_000,
                start_year=2015,
                maturity_year=2035,
                maturity_value=1_200_000,
            ),
        ],
    )
    result = recommend_life_cover(profile)
    assert result.existing_cover == 0.0


# When existing cover exceeds recommendation, gap must be 0 (never negative)
def test_recommend_life_cover_gap_never_negative():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=10_000,
        tax_regime=TaxRegime.NEW,
        existing_policies=[
            ExistingPolicy(
                policy_type=PolicyType.TERM,
                sum_assured=100_000_000,  # 10 crore
                annual_premium=80_000,
                start_year=2020,
            )
        ],
    )
    result = recommend_life_cover(profile)
    assert result.gap == 0.0


# 10x heuristic must always be annual_income × 10, regardless of HLV/NBA
def test_recommend_life_cover_heuristic_is_ten_times_income(minimal_profile):
    result = recommend_life_cover(minimal_profile)
    assert result.heuristic_10x_cover == pytest.approx(
        minimal_profile.annual_income * 10
    )


# ---------------------------------------------------------------------------
# compute_health_cover_need
# ---------------------------------------------------------------------------


# Tier-1, single user, age ≤ 45 → base = 25 lakh, no adjustments
def test_health_cover_tier1_single_young_returns_25_lakh():
    profile = UserProfile(
        age=35,
        gender=Gender.FEMALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_000_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=8_000,
        tax_regime=TaxRegime.NEW,
    )
    result = compute_health_cover_need(profile)
    assert result.recommended_cover == 2_500_000
    assert result.age_adjustment == 0.0
    assert result.family_size_adjustment == 0.0


# Tier-2, single user, age ≤ 45 → base = 10 lakh
def test_health_cover_tier2_single_young_returns_10_lakh():
    profile = UserProfile(
        age=35,
        gender=Gender.FEMALE,
        city_tier=CityTier.TIER_2,
        annual_income=800_000,
        monthly_expenses=25_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    result = compute_health_cover_need(profile)
    assert result.recommended_cover == 1_000_000


# Tier-3, single user, age ≤ 45 → base = 10 lakh (recommended, not floor)
def test_health_cover_tier3_single_young_returns_10_lakh():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_3,
        annual_income=500_000,
        monthly_expenses=15_000,
        monthly_insurance_budget=3_000,
        tax_regime=TaxRegime.NEW,
    )
    result = compute_health_cover_need(profile)
    assert result.recommended_cover == 1_000_000


# Spouse + 2 children → 3 additional members × 5L = 15L family adjustment
def test_health_cover_family_adjustment_correct():
    profile = UserProfile(
        age=38,
        gender=Gender.FEMALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_500_000,
        monthly_expenses=60_000,
        monthly_insurance_budget=15_000,
        tax_regime=TaxRegime.NEW,
        spouse=Spouse(age=40, annual_income=0),
        children=[Child(age=10), Child(age=7)],
    )
    result = compute_health_cover_need(profile)
    assert result.family_size_adjustment == 1_500_000  # 3 × 5L
    assert result.recommended_cover == 4_000_000  # 25L + 15L


# Age > 45 triggers 20% buffer on running subtotal
def test_health_cover_age_buffer_applied_above_45():
    profile = UserProfile(
        age=50,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=2_000_000,
        monthly_expenses=70_000,
        monthly_insurance_budget=20_000,
        tax_regime=TaxRegime.NEW,
    )
    result = compute_health_cover_need(profile)
    # base = 25L, no family → 20% of 25L = 5L buffer → total 30L
    assert result.age_adjustment == pytest.approx(500_000)
    assert result.recommended_cover == pytest.approx(3_000_000)


# Age exactly 45 does NOT get the buffer (threshold is strictly > 45)
def test_health_cover_age_45_has_no_buffer():
    profile = UserProfile(
        age=45,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_500_000,
        monthly_expenses=50_000,
        monthly_insurance_budget=10_000,
        tax_regime=TaxRegime.NEW,
    )
    result = compute_health_cover_need(profile)
    assert result.age_adjustment == 0.0


# Existing health cover reduces the gap
def test_health_cover_existing_policy_reduces_gap():
    profile = UserProfile(
        age=35,
        gender=Gender.FEMALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=40_000,
        monthly_insurance_budget=10_000,
        tax_regime=TaxRegime.NEW,
        existing_policies=[
            ExistingPolicy(
                policy_type=PolicyType.HEALTH,
                sum_assured=1_000_000,
                annual_premium=12_000,
                start_year=2022,
            )
        ],
    )
    result = compute_health_cover_need(profile)
    assert result.existing_cover == 1_000_000
    assert result.gap == pytest.approx(result.recommended_cover - 1_000_000)


# Gap is never negative even when existing cover exceeds recommendation
def test_health_cover_gap_never_negative():
    profile = UserProfile(
        age=35,
        gender=Gender.FEMALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=40_000,
        monthly_insurance_budget=10_000,
        tax_regime=TaxRegime.NEW,
        existing_policies=[
            ExistingPolicy(
                policy_type=PolicyType.HEALTH,
                sum_assured=50_000_000,
                annual_premium=100_000,
                start_year=2020,
            )
        ],
    )
    result = compute_health_cover_need(profile)
    assert result.gap == 0.0


# ---------------------------------------------------------------------------
# compute_accident_disability_need
# ---------------------------------------------------------------------------


# 12L income → accident = 10L (10× monthly), disability = 6L (50% annual)
def test_accident_disability_standard_income(minimal_profile):
    result = compute_accident_disability_need(minimal_profile)
    assert result.recommended_accident_cover == pytest.approx(
        1_000_000
    )  # 10 × (12L/12)
    assert result.recommended_disability_cover == pytest.approx(600_000)  # 50% × 12L


# Zero income → both covers are 0 (no income to replace)
def test_accident_disability_zero_income_returns_zero():
    profile = UserProfile(
        age=35,
        gender=Gender.FEMALE,
        city_tier=CityTier.TIER_1,
        annual_income=0,
        monthly_expenses=0,
        monthly_insurance_budget=0,
        tax_regime=TaxRegime.NEW,
    )
    result = compute_accident_disability_need(profile)
    assert result.recommended_accident_cover == 0.0
    assert result.recommended_disability_cover == 0.0


# Existing accident policy reduces accident gap
def test_accident_disability_existing_accident_reduces_gap():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
        existing_policies=[
            ExistingPolicy(
                policy_type=PolicyType.ACCIDENT,
                sum_assured=500_000,
                annual_premium=3_000,
                start_year=2023,
            )
        ],
    )
    result = compute_accident_disability_need(profile)
    assert result.existing_accident_cover == 500_000
    assert result.accident_gap == pytest.approx(1_000_000 - 500_000)


# Existing disability policy reduces disability gap
def test_accident_disability_existing_disability_reduces_gap():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
        existing_policies=[
            ExistingPolicy(
                policy_type=PolicyType.DISABILITY,
                sum_assured=600_000,
                annual_premium=5_000,
                start_year=2023,
            )
        ],
    )
    result = compute_accident_disability_need(profile)
    assert result.existing_disability_cover == 600_000
    assert result.disability_gap == 0.0  # fully covered


# Accident gap is never negative even when over-covered
def test_accident_gap_never_negative():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1_200_000,
        monthly_expenses=30_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
        existing_policies=[
            ExistingPolicy(
                policy_type=PolicyType.ACCIDENT,
                sum_assured=10_000_000,
                annual_premium=30_000,
                start_year=2020,
            )
        ],
    )
    result = compute_accident_disability_need(profile)
    assert result.accident_gap == 0.0


# disability_via_rider_suggested is always True — standalone products are rare in India
def test_accident_disability_rider_always_suggested(minimal_profile):
    result = compute_accident_disability_need(minimal_profile)
    assert result.disability_via_rider_suggested is True


# Higher income → proportionally higher accident and disability cover (monotonicity)
def test_accident_disability_higher_income_produces_higher_cover():
    low = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=600_000,
        monthly_expenses=20_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    high = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=2_400_000,
        monthly_expenses=20_000,
        monthly_insurance_budget=5_000,
        tax_regime=TaxRegime.NEW,
    )
    low_result = compute_accident_disability_need(low)
    high_result = compute_accident_disability_need(high)
    assert (
        high_result.recommended_accident_cover > low_result.recommended_accident_cover
    )
    assert (
        high_result.recommended_disability_cover
        > low_result.recommended_disability_cover
    )
