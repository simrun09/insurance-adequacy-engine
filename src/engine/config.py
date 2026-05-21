"""
Configuration constants for the Insurance Adequacy Engine.

Every value has a source citation. If a value needs to change
(new IRDAI guidance, updated tax limits, revised medical costs),
change it here — not in the logic modules.
"""

# ──────────────────────────────────────────────
# Life cover — HLV parameters
# ──────────────────────────────────────────────

# IRDAI guidance suggests 5-8% for conservative HLV planning.
# 6% is the midpoint; conservative enough to not under-insure.
DISCOUNT_RATE = 0.06

# Standard Indian retirement age used by most financial planners
# and the Employees' Provident Fund Organisation (EPFO).
RETIREMENT_AGE = 60

# ──────────────────────────────────────────────
# Life cover — NBA parameters
# ──────────────────────────────────────────────

# Emergency corpus: 6 months of household expenses.
# CFP Institute of India recommends 3-6 months; we use 6
# because a single-income household losing the earner
# needs more runway than a dual-income one.
EMERGENCY_MONTHS = 6

# ──────────────────────────────────────────────
# Health cover — city-tier floors (in rupees)
# ──────────────────────────────────────────────
# Based on actual hospitalization costs:
# Tier-1 metro: major surgery with ICU = 5-10 lakh,
# cancer/cardiac/transplant = 15-25 lakh.
# Source: Niva Bupa, Ditto, ManipalCigna insurer publications.

HEALTH_FLOOR_TIER_1 = 10_00_000    # 10 lakh minimum
HEALTH_RECOMMENDED_TIER_1 = 25_00_000  # 25 lakh recommended

HEALTH_FLOOR_TIER_2 = 10_00_000    # 10 lakh
HEALTH_RECOMMENDED_TIER_2 = 10_00_000

HEALTH_FLOOR_TIER_3 = 5_00_000     # 5 lakh minimum
HEALTH_RECOMMENDED_TIER_3 = 10_00_000  # 10 lakh recommended

# Per additional family member added to floater.
# Simplified heuristic — real actuarial loading varies by age.
HEALTH_PER_MEMBER_ADDITION = 5_00_000  # 5 lakh

# Users above this age get a 20% buffer on health recommendation.
# Hospitalization probability increases meaningfully after 45.
# Source: IRDAI annual report — claims frequency by age band.
HEALTH_AGE_THRESHOLD = 45
HEALTH_AGE_BUFFER = 0.20  # 20%

# Healthcare costs in India rising at 12-15% annually.
# Source: Mercer Marsh Benefits Medical Trends report;
# Asia Pacific projected 14% for 2026.
MEDICAL_INFLATION_RATE = 0.14

# ──────────────────────────────────────────────
# Accident and disability
# ──────────────────────────────────────────────

# Personal accident cover: 10x monthly income as lump sum.
# Industry-standard heuristic across Indian insurers.
ACCIDENT_COVER_MULTIPLIER = 10

# Disability income replacement: 50-60% of annual income.
# We use 0.50 (conservative end) because standalone disability
# products are rare in India; we'll suggest a rider instead.
DISABILITY_INCOME_RATIO = 0.50

# ──────────────────────────────────────────────
# Tax — Section 80C and 80D limits (FY 2025-26)
# ──────────────────────────────────────────────
# Source: Income Tax Act, 1961 (as amended by Finance Act 2024).
# These apply ONLY under the old tax regime.

SECTION_80C_LIMIT = 1_50_000  # 1.5 lakh

SECTION_80D_SELF_LIMIT = 25_000  # self + spouse + dependent children
SECTION_80D_PARENTS_LIMIT = 25_000  # parents below 60
SECTION_80D_PARENTS_SENIOR_LIMIT = 50_000  # parents 60 and above

# ──────────────────────────────────────────────
# Tax slabs — old regime (FY 2025-26)
# ──────────────────────────────────────────────
# Used to estimate the user's marginal tax rate for
# computing effective premium under old regime.
# Source: Income Tax Act Schedule.

OLD_REGIME_SLABS = [
    (2_50_000, 0.00),     # up to 2.5 lakh: nil
    (5_00_000, 0.05),     # 2.5-5 lakh: 5%
    (10_00_000, 0.20),    # 5-10 lakh: 20%
    (float("inf"), 0.30), # above 10 lakh: 30%
]

# ──────────────────────────────────────────────
# Illustrative premium rates (per lakh of cover per year)
# ──────────────────────────────────────────────
# These are NOT real insurer quotes. They are rough averages
# for estimation only. Real premiums depend on age, health,
# smoking status, insurer, and policy terms.
# Source: PolicyBazaar and Ditto published premium comparisons.

TERM_PREMIUM_PER_LAKH_ANNUAL = 10  # ~₹10/lakh/year for age 30-35
HEALTH_PREMIUM_ANNUAL_APPROX = {
    "individual_young": 8_000,   # age < 35, individual
    "individual_mid": 15_000,    # age 35-45, individual
    "individual_senior": 25_000, # age > 45, individual
    "family_floater": 20_000,    # family of 3-4, primary < 40
}
ACCIDENT_PREMIUM_ANNUAL_APPROX = 3_000  # per 10 lakh cover
