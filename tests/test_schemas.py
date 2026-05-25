import pytest
from pydantic import TypeAdapter, ValidationError

from engine.schemas import (
    ActionItem,
    ActionPlan,
    AccidentDisabilityNeed,
    AssessmentResult,
    Child,
    CityTier,
    DependentParent,
    EfficiencyFlag,
    ExistingPolicy,
    FutureExpense,
    Gender,
    HealthCoverNeed,
    LifeCoverNeed,
    Loan,
    PolicyAudit,
    PolicyType,
    Spouse,
    TaxRegime,
    UserProfile,
)

# ---------------------------------------------------------------------------
# ENUM TESTS
# ---------------------------------------------------------------------------


# Gender accepts all three valid string values
def test_gender_valid_values_accepted():
    adapter = TypeAdapter(Gender)
    assert adapter.validate_python("male") == Gender.MALE
    assert adapter.validate_python("female") == Gender.FEMALE
    assert adapter.validate_python("other") == Gender.OTHER


# Invalid gender string must be rejected — prevents garbage data reaching the engine
def test_gender_invalid_value_raises_validation_error():
    adapter = TypeAdapter(Gender)
    with pytest.raises(ValidationError):
        adapter.validate_python("unknown")


# CityTier accepts all three tier strings
def test_city_tier_valid_values_accepted():
    adapter = TypeAdapter(CityTier)
    assert adapter.validate_python("tier_1") == CityTier.TIER_1
    assert adapter.validate_python("tier_2") == CityTier.TIER_2
    assert adapter.validate_python("tier_3") == CityTier.TIER_3


# Invalid tier must fail — health floor lookup would break silently otherwise
def test_city_tier_invalid_value_raises_validation_error():
    adapter = TypeAdapter(CityTier)
    with pytest.raises(ValidationError):
        adapter.validate_python("tier_4")


# TaxRegime accepts both regime strings
def test_tax_regime_valid_values_accepted():
    adapter = TypeAdapter(TaxRegime)
    assert adapter.validate_python("old") == TaxRegime.OLD
    assert adapter.validate_python("new") == TaxRegime.NEW


# Invalid regime must fail — wrong regime silently skips 80C/80D logic
def test_tax_regime_invalid_value_raises_validation_error():
    adapter = TypeAdapter(TaxRegime)
    with pytest.raises(ValidationError):
        adapter.validate_python("hybrid")


# PolicyType accepts all six product types
def test_policy_type_valid_values_accepted():
    adapter = TypeAdapter(PolicyType)
    for value in ("term", "endowment", "ulip", "health", "accident", "disability"):
        assert adapter.validate_python(value) is not None


# Invalid policy type must fail — audit.py branches on this value
def test_policy_type_invalid_value_raises_validation_error():
    adapter = TypeAdapter(PolicyType)
    with pytest.raises(ValidationError):
        adapter.validate_python("crypto")


# EfficiencyFlag accepts all three verdict strings
def test_efficiency_flag_valid_values_accepted():
    adapter = TypeAdapter(EfficiencyFlag)
    assert adapter.validate_python("efficient") == EfficiencyFlag.EFFICIENT
    assert adapter.validate_python("mixed") == EfficiencyFlag.MIXED
    assert adapter.validate_python("inefficient") == EfficiencyFlag.INEFFICIENT


# Invalid efficiency flag must fail — dashboard traffic-light depends on this value
def test_efficiency_flag_invalid_value_raises_validation_error():
    adapter = TypeAdapter(EfficiencyFlag)
    with pytest.raises(ValidationError):
        adapter.validate_python("bad")


# ---------------------------------------------------------------------------
# POSITIVE CONSTRUCTION TESTS
# ---------------------------------------------------------------------------


# Spouse with valid age and income constructs without error
def test_spouse_valid_construction():
    s = Spouse(age=32, annual_income=800000)
    assert s.age == 32
    assert s.annual_income == 800000


# Child with valid age and both cost estimates constructs without error
def test_child_valid_construction():
    c = Child(age=7, education_cost_estimate=1500000, marriage_cost_estimate=500000)
    assert c.age == 7


# DependentParent with valid age constructs; has_own_health_cover defaults to False
def test_dependent_parent_valid_construction():
    dp = DependentParent(age=65)
    assert dp.age == 65
    assert dp.has_own_health_cover is False


# Loan with all fields constructs without error
def test_loan_valid_construction():
    loan = Loan(
        loan_type="home loan", outstanding_balance=4500000, remaining_tenure_years=15
    )
    assert loan.outstanding_balance == 4500000


# FutureExpense with a valid future year constructs without error
def test_future_expense_valid_construction():
    fe = FutureExpense(
        description="daughter's education", estimated_amount=2000000, target_year=2035
    )
    assert fe.target_year == 2035


# ExistingPolicy (term) with no maturity fields constructs without error
def test_existing_policy_term_valid_construction():
    p = ExistingPolicy(
        policy_type=PolicyType.TERM,
        sum_assured=10000000,
        annual_premium=12000,
        start_year=2020,
    )
    assert p.maturity_year is None
    assert p.maturity_value is None


# ExistingPolicy (endowment) with maturity fields constructs without error
def test_existing_policy_endowment_valid_construction():
    p = ExistingPolicy(
        policy_type=PolicyType.ENDOWMENT,
        sum_assured=500000,
        annual_premium=50000,
        start_year=2015,
        maturity_year=2035,
        maturity_value=1500000,
    )
    assert p.maturity_year == 2035


# ---------------------------------------------------------------------------
# CONSTRAINT VIOLATION TESTS
# ---------------------------------------------------------------------------


# Spouse age below 18 is not a valid working adult — must be rejected
def test_spouse_age_below_minimum_rejected():
    with pytest.raises(ValidationError):
        Spouse(age=17, annual_income=0)


# Spouse age above 80 is outside the engine's supported range
def test_spouse_age_above_maximum_rejected():
    with pytest.raises(ValidationError):
        Spouse(age=81, annual_income=0)


# Child age below 0 is physically impossible
def test_child_age_below_minimum_rejected():
    with pytest.raises(ValidationError):
        Child(age=-1)


# Child age above 25 is outside the dependent child definition
def test_child_age_above_maximum_rejected():
    with pytest.raises(ValidationError):
        Child(age=26)


# DependentParent age below 40 is outside the realistic dependent parent range
def test_dependent_parent_age_below_minimum_rejected():
    with pytest.raises(ValidationError):
        DependentParent(age=39)


# Loan tenure above 30 years is beyond any standard Indian home loan product
def test_loan_tenure_above_maximum_rejected():
    with pytest.raises(ValidationError):
        Loan(
            loan_type="home loan",
            outstanding_balance=1000000,
            remaining_tenure_years=31,
        )


# FutureExpense target year before 2025 means the expense is already past — invalid input
def test_future_expense_target_year_below_minimum_rejected():
    with pytest.raises(ValidationError):
        FutureExpense(
            description="old expense", estimated_amount=100000, target_year=2024
        )


# ExistingPolicy start year before 1980 is implausibly old for a living policyholder
def test_existing_policy_start_year_below_minimum_rejected():
    with pytest.raises(ValidationError):
        ExistingPolicy(
            policy_type=PolicyType.TERM,
            sum_assured=1000000,
            annual_premium=5000,
            start_year=1979,
        )


# UserProfile age below 18 — engine only serves working-age adults
def test_user_profile_age_below_minimum_rejected():
    with pytest.raises(ValidationError):
        UserProfile(
            age=17,
            gender=Gender.MALE,
            city_tier=CityTier.TIER_1,
            annual_income=500000,
            monthly_expenses=20000,
            monthly_insurance_budget=3000,
            tax_regime=TaxRegime.NEW,
        )


# UserProfile age above 80 is outside the supported range
def test_user_profile_age_above_maximum_rejected():
    with pytest.raises(ValidationError):
        UserProfile(
            age=81,
            gender=Gender.MALE,
            city_tier=CityTier.TIER_1,
            annual_income=500000,
            monthly_expenses=20000,
            monthly_insurance_budget=3000,
            tax_regime=TaxRegime.NEW,
        )


# Negative income is nonsensical and must be rejected before reaching the engine
def test_user_profile_negative_income_rejected():
    with pytest.raises(ValidationError):
        UserProfile(
            age=35,
            gender=Gender.FEMALE,
            city_tier=CityTier.TIER_2,
            annual_income=-1,
            monthly_expenses=20000,
            monthly_insurance_budget=3000,
            tax_regime=TaxRegime.OLD,
        )


# ---------------------------------------------------------------------------
# USERPROFILE FULL TEST
# ---------------------------------------------------------------------------


# Complete realistic Indian profile — married, one child, dependent parent,
# home loan, term + endowment policy, some assets — all fields must be accessible
def test_user_profile_full_realistic_construction():
    profile = UserProfile(
        age=35,
        gender=Gender.MALE,
        city_tier=CityTier.TIER_1,
        annual_income=1500000,
        monthly_expenses=40000,
        monthly_insurance_budget=5000,
        tax_regime=TaxRegime.OLD,
        spouse=Spouse(age=32, annual_income=800000),
        children=[
            Child(age=5, education_cost_estimate=2000000, marriage_cost_estimate=500000)
        ],
        dependent_parents=[DependentParent(age=65, has_own_health_cover=False)],
        loans=[
            Loan(
                loan_type="home loan",
                outstanding_balance=5000000,
                remaining_tenure_years=18,
            )
        ],
        future_expenses=[
            FutureExpense(
                description="child education abroad",
                estimated_amount=3000000,
                target_year=2038,
            )
        ],
        investable_assets=800000,
        epf_ppf_balance=400000,
        existing_policies=[
            ExistingPolicy(
                policy_type=PolicyType.TERM,
                sum_assured=10000000,
                annual_premium=12000,
                start_year=2021,
            ),
            ExistingPolicy(
                policy_type=PolicyType.ENDOWMENT,
                sum_assured=500000,
                annual_premium=50000,
                start_year=2015,
                maturity_year=2035,
                maturity_value=1200000,
            ),
        ],
    )
    assert profile.spouse.annual_income == 800000
    assert len(profile.children) == 1
    assert len(profile.dependent_parents) == 1
    assert len(profile.loans) == 1
    assert len(profile.existing_policies) == 2
    assert profile.existing_policies[1].policy_type == PolicyType.ENDOWMENT


# ---------------------------------------------------------------------------
# USERPROFILE MINIMAL TEST
# ---------------------------------------------------------------------------


# Single user with no family, no loans, no policies — all list defaults must be empty,
# all optional fields must be None, asset defaults must be zero
def test_user_profile_minimal_defaults():
    profile = UserProfile(
        age=28,
        gender=Gender.FEMALE,
        city_tier=CityTier.TIER_2,
        annual_income=600000,
        monthly_expenses=15000,
        monthly_insurance_budget=2000,
        tax_regime=TaxRegime.NEW,
    )
    assert profile.spouse is None
    assert profile.children == []
    assert profile.dependent_parents == []
    assert profile.loans == []
    assert profile.future_expenses == []
    assert profile.existing_policies == []
    assert profile.investable_assets == 0.0
    assert profile.epf_ppf_balance == 0.0


# ---------------------------------------------------------------------------
# OPTIONAL FIELD TESTS
# ---------------------------------------------------------------------------


# spouse=None must be accepted — not every user is married
def test_user_profile_spouse_none_accepted():
    profile = UserProfile(
        age=30,
        gender=Gender.OTHER,
        city_tier=CityTier.TIER_3,
        annual_income=400000,
        monthly_expenses=12000,
        monthly_insurance_budget=1500,
        tax_regime=TaxRegime.NEW,
        spouse=None,
    )
    assert profile.spouse is None


# Term policy with both maturity fields as None must be accepted
def test_existing_policy_maturity_fields_none_accepted():
    p = ExistingPolicy(
        policy_type=PolicyType.TERM,
        sum_assured=5000000,
        annual_premium=8000,
        start_year=2022,
        maturity_year=None,
        maturity_value=None,
    )
    assert p.maturity_year is None
    assert p.maturity_value is None


# ---------------------------------------------------------------------------
# OUTPUT MODEL TESTS
# ---------------------------------------------------------------------------


# LifeCoverNeed with realistic HLV/NBA numbers constructs correctly
def test_life_cover_need_valid_construction():
    need = LifeCoverNeed(
        hlv_based_cover=12000000,
        nba_based_cover=15000000,
        recommended_cover=15000000,
        existing_cover=10000000,
        gap=5000000,
        heuristic_10x_cover=15000000,
    )
    assert need.recommended_cover == 15000000
    assert need.gap == 5000000


# HealthCoverNeed with city-tier floor and adjustments constructs correctly
def test_health_cover_need_valid_construction():
    need = HealthCoverNeed(
        recommended_cover=2500000,
        existing_cover=1000000,
        gap=1500000,
        city_tier_floor=1000000,
        family_size_adjustment=1000000,
        age_adjustment=500000,
    )
    assert need.gap == 1500000


# AccidentDisabilityNeed with realistic cover amounts constructs correctly
def test_accident_disability_need_valid_construction():
    need = AccidentDisabilityNeed(
        recommended_accident_cover=1250000,
        existing_accident_cover=0,
        accident_gap=1250000,
        recommended_disability_cover=750000,
        existing_disability_cover=0,
        disability_gap=750000,
        disability_via_rider_suggested=True,
    )
    assert need.disability_via_rider_suggested is True


# PolicyAudit for an inefficient ULIP constructs with all optional IRR fields populated
def test_policy_audit_ulip_inefficient_construction():
    audit = PolicyAudit(
        policy_type=PolicyType.ULIP,
        sum_assured=500000,
        is_adequate=False,
        adequacy_gap=500000,
        efficiency_flag=EfficiencyFlag.INEFFICIENT,
        implied_irr=0.042,
        opportunity_cost=800000,
        recommendation="Consult a fee-only advisor about this policy.",
    )
    assert audit.efficiency_flag == EfficiencyFlag.INEFFICIENT
    assert audit.implied_irr == pytest.approx(0.042)


# ActionItem with valid priority and budget fields constructs correctly
def test_action_item_valid_construction():
    item = ActionItem(
        policy_type=PolicyType.TERM,
        recommended_cover=15000000,
        estimated_monthly_premium=1100,
        cumulative_premium=1100,
        remaining_budget=3900,
        priority_rank=1,
    )
    assert item.priority_rank == 1
    assert item.remaining_budget == 3900


# ActionPlan with items in both buckets and a shortfall constructs correctly
def test_action_plan_valid_construction():
    item1 = ActionItem(
        policy_type=PolicyType.TERM,
        recommended_cover=15000000,
        estimated_monthly_premium=1100,
        cumulative_premium=1100,
        remaining_budget=900,
        priority_rank=1,
    )
    item2 = ActionItem(
        policy_type=PolicyType.HEALTH,
        recommended_cover=1500000,
        estimated_monthly_premium=1500,
        cumulative_premium=2600,
        remaining_budget=0,
        priority_rank=2,
    )
    plan = ActionPlan(
        items_within_budget=[item1],
        items_beyond_budget=[item2],
        total_monthly_premium_required=2600,
        monthly_shortfall=600,
    )
    assert len(plan.items_within_budget) == 1
    assert len(plan.items_beyond_budget) == 1
    assert plan.monthly_shortfall == 600


# AssessmentResult composing all output models constructs and fields are accessible
def test_assessment_result_valid_construction():
    result = AssessmentResult(
        life_cover_need=LifeCoverNeed(
            hlv_based_cover=12000000,
            nba_based_cover=15000000,
            recommended_cover=15000000,
            existing_cover=10000000,
            gap=5000000,
            heuristic_10x_cover=15000000,
        ),
        health_cover_need=HealthCoverNeed(
            recommended_cover=2500000,
            existing_cover=0,
            gap=2500000,
            city_tier_floor=1000000,
            family_size_adjustment=1000000,
            age_adjustment=500000,
        ),
        accident_disability_need=AccidentDisabilityNeed(
            recommended_accident_cover=1250000,
            existing_accident_cover=0,
            accident_gap=1250000,
            recommended_disability_cover=750000,
            existing_disability_cover=0,
            disability_gap=750000,
        ),
        policy_audits=[],
        action_plan=ActionPlan(
            items_within_budget=[],
            items_beyond_budget=[],
            total_monthly_premium_required=5000,
            monthly_shortfall=0,
        ),
        explanation="Your biggest gap is life cover. We recommend a term policy of ₹1.5 crore.",
        explanation_is_llm_generated=True,
        disclaimer="This assessment is for educational purposes only and does not constitute financial advice.",
    )
    assert result.explanation_is_llm_generated is True
    assert result.life_cover_need.gap == 5000000
    assert result.disclaimer != ""
