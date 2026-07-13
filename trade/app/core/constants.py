"""Centralized NLP signals, temporal patterns, and parsing delimiters for GDCE Trade Service."""

# Intent post-extraction correction signals
COMPARISON_SIGNALS: list[str] = [
    "compare",
    "comparison",
    "versus",
    "vs",
    "between",
    "difference",
    "relative to",
    "against",
]

TREND_SIGNALS: list[str] = [
    "over time",
    "monthly",
    "quarterly",
    "each year",
    "per month",
    "historical",
    "trajectory",
    "evolution",
]

TREND_OVERRIDE_SIGNALS: list[str] = [
    "over the years", "over time", "each year", "per year",
    "year by year", "year-on-year", "how has", "how did",
    "past 5 years", "past 10 years", "last 5 years", "last 10 years",
    "last decade", "over the decade", "since 20", "has it changed",
    "has changed", "has grown", "has declined", "performance over",
    "trajectory", "evolution of",
]

# Semester recognition patterns
SEMESTER_S1_PATTERNS: list[str] = [
    r"\bS1\b", r"\bH1\b",
    r"\bFIRST\s+HALF\b", r"\b1ST\s+HALF\b",
    r"\bFIRST\s+SEMESTER\b", r"\b1ST\s+SEMESTER\b",
    r"\bSEMESTER\s+1\b", r"\bSEM\s+1\b",
    r"\bSEMESTER1\b", r"\bSEM1\b"
]

# Semester 2 recognition patterns
SEMESTER_S2_PATTERNS: list[str] = [
    r"\bS2\b", r"\bH2\b",
    r"\bSECOND\s+HALF\b", r"\b2ND\s+HALF\b",
    r"\bSECOND\s+SEMESTER\b", r"\b2ND\s+SEMESTER\b",
    r"\bSEMESTER\s+2\b", r"\bSEM\s+2\b",
    r"\bSEMESTER2\b", r"\bSEM2\b"
]

# NLG Repeating queries and data coverage warnings
NLG_REPEATING_KEYWORDS: list[str] = [
    "each year",
    "every year",
    "each january",
    "every january",
    "each q1",
    "every q1",
    "each quarter",
    "every quarter",
]

# NLG Range keywords
NLG_RANGE_KEYWORDS: list[str] = [
    "decade",
    "5 years",
    "10 years",
    "past 5",
    "past 10",
    "past 5-years",
    "last 5",
    "last 10",
]

# Delimiters used in product resolver engine
PRODUCT_SPLIT_DELIMITERS: str = r"[,;]"
PRODUCT_PREPOSITION_DELIMITERS: str = r"\bfor\b|\bof\b|\bnot\b|\bwhether\b|\bexcluding\b"
PRODUCT_AND_DELIMITERS: str = r"\band\b"

# Global warnings
SUGGESTED_REPHRASE_WARNING: str = "Try rephrasing your question (e.g. 'What are Cambodia's top exports in 2025?')"
