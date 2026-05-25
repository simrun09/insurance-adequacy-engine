from enum import Enum
from pydantic import BaseModel, Field


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    # Engine defaults to conservative (higher) premium estimate for OTHER
    OTHER = "other"


class CityTier(str, Enum):
    # Tier determines health cover floor — a surgery costs the same regardless of income
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class TaxRegime(str, Enum):
    # OLD regime: 80C/80D deductions apply, reducing effective premium cost
    # NEW regime (default post FY2024-25): no deductions, effective premium = nominal premium
    OLD = "old"
    NEW = "new"


class PolicyType(str, Enum):
    TERM = "term"
    ENDOWMENT = "endowment"
    ULIP = "ulip"
    HEALTH = "health"
    ACCIDENT = "accident"
    DISABILITY = "disability"


class EfficiencyFlag(str, Enum):
    # Verdict of IRR comparison for investment-linked policies (ULIP/endowment)
    # vs the "term insurance + index fund" alternative
    EFFICIENT = "efficient"
    MIXED = "mixed"
    INEFFICIENT = "inefficient"


class Spouse(BaseModel):
    age: int = Field(ge=18, le=80)
    # Non-earning spouse increases required cover; high earner reduces NBA obligation
    annual_income: float = Field(ge=0)


class Child(BaseModel):
    age: int = Field(ge=0, le=25)
    education_cost_estimate: float = Field(default=0.0, ge=0)
    marriage_cost_estimate: float = Field(default=0.0, ge=0)


class DependentParent(BaseModel):
    # Age >= 60 triggers higher Section 80D deduction limit (50k vs 25k)
    age: int = Field(ge=40, le=100)
    # Prevents double-counting: if parent already has cover, exclude from health gap
    has_own_health_cover: bool = Field(default=False)


class Loan(BaseModel):
    loan_type: str  # descriptive only; used by explanation layer (e.g. "home loan")
    outstanding_balance: float = Field(ge=0)
    remaining_tenure_years: int = Field(ge=0, le=30)


class FutureExpense(BaseModel):
    description: str
    estimated_amount: float = Field(ge=0)
    # Used to discount the expense to present value using config.DISCOUNT_RATE_DEFAULT
    target_year: int = Field(ge=2025)


class ExistingPolicy(BaseModel):
    policy_type: PolicyType
    sum_assured: float = Field(ge=0)
    annual_premium: float = Field(ge=0)
    start_year: int = Field(ge=1980, le=2025)
    # maturity_year and maturity_value are only relevant for ULIP/endowment policies;
    # set both or neither — audit.py uses them together for IRR analysis
    maturity_year: int | None = Field(default=None)
    maturity_value: float | None = Field(default=None)


class UserProfile(BaseModel):
    # Personal
    age: int = Field(ge=18, le=80)
    gender: Gender
    city_tier: CityTier
    annual_income: float = Field(ge=0)
    monthly_expenses: float = Field(ge=0)
    monthly_insurance_budget: float = Field(ge=0)
    tax_regime: TaxRegime

    # Family
    spouse: Spouse | None = Field(default=None)
    children: list[Child] = Field(default_factory=list)
    dependent_parents: list[DependentParent] = Field(default_factory=list)

    # Financial obligations
    loans: list[Loan] = Field(default_factory=list)
    future_expenses: list[FutureExpense] = Field(default_factory=list)

    # Existing assets — both subtracted from NBA to avoid over-insuring
    investable_assets: float = Field(default=0.0, ge=0)
    # Kept separate from investable_assets: EPF/PPF is illiquid and withdrawal-restricted
    epf_ppf_balance: float = Field(default=0.0, ge=0)

    # Existing policies
    existing_policies: list[ExistingPolicy] = Field(default_factory=list)


class LifeCoverNeed(BaseModel):
    # Stored separately for traceability — user can see which method drove the recommendation
    hlv_based_cover: (
        float  # present value of income family would lose (income replacement)
    )
    nba_based_cover: float  # sum of obligations minus existing assets (needs-based)
    recommended_cover: float  # max(hlv_based_cover, nba_based_cover)
    existing_cover: float
    gap: float
    # Stored for educational comparison only — never drives the recommendation
    heuristic_10x_cover: float


class HealthCoverNeed(BaseModel):
    recommended_cover: float  # floor + family_size_adjustment + age_adjustment
    existing_cover: float
    gap: float
    # Stored separately so the user can see exactly how the recommendation was built
    city_tier_floor: float
    family_size_adjustment: float  # 5 lakh per additional family member
    age_adjustment: float  # 20% buffer added if user age > 45


class AccidentDisabilityNeed(BaseModel):
    recommended_accident_cover: (
        float  # 10x monthly income (lump sum on death/disability)
    )
    existing_accident_cover: float
    accident_gap: float
    recommended_disability_cover: float  # 50-60% of annual income (income replacement)
    existing_disability_cover: float
    disability_gap: float
    # True for most users — standalone disability products are rare in India;
    # prioritizer.py will suggest a rider on the term policy instead
    disability_via_rider_suggested: bool = Field(default=True)


class PolicyAudit(BaseModel):
    policy_type: PolicyType
    sum_assured: float
    is_adequate: bool
    adequacy_gap: float = Field(ge=0)
    # None for term/health/accident — IRR analysis only applies to investment-linked products
    efficiency_flag: EfficiencyFlag | None = Field(default=None)
    implied_irr: float | None = Field(default=None)
    # Rupee cost of staying in an inefficient policy vs term + index fund alternative
    opportunity_cost: float | None = Field(default=None)
    recommendation: str


class ActionItem(BaseModel):
    policy_type: PolicyType
    recommended_cover: float = Field(ge=0)
    estimated_monthly_premium: float = Field(ge=0)
    # Running total after this item — shows budget impact as user reads down the list
    cumulative_premium: float = Field(ge=0)
    remaining_budget: float
    priority_rank: int = Field(ge=1)


class ActionPlan(BaseModel):
    items_within_budget: list[ActionItem] = Field(default_factory=list)
    # Shown even if unaffordable — user sees the full gap picture, not just what fits
    items_beyond_budget: list[ActionItem] = Field(default_factory=list)
    total_monthly_premium_required: float = Field(ge=0)
    # Extra monthly budget needed to close all gaps; 0 means current budget is sufficient
    monthly_shortfall: float = Field(ge=0)


class AssessmentResult(BaseModel):
    life_cover_need: LifeCoverNeed
    health_cover_need: HealthCoverNeed
    accident_disability_need: AccidentDisabilityNeed
    policy_audits: list[PolicyAudit] = Field(default_factory=list)
    action_plan: ActionPlan
    explanation: str
    # False when LLM was unavailable and template fallback was used instead
    explanation_is_llm_generated: bool
    # Mandatory on every response — this tool is not financial advice
    disclaimer: str


__all__ = [
    "Gender",
    "CityTier",
    "TaxRegime",
    "PolicyType",
    "EfficiencyFlag",
    "Spouse",
    "Child",
    "DependentParent",
    "Loan",
    "FutureExpense",
    "ExistingPolicy",
    "UserProfile",
    "LifeCoverNeed",
    "HealthCoverNeed",
    "AccidentDisabilityNeed",
    "PolicyAudit",
    "ActionItem",
    "ActionPlan",
    "AssessmentResult",
]
