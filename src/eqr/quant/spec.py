"""Scoring spec frozen from the LSEG benchmark report (pp. 11-12). Doc and engine share these constants."""

SCORE_BANDS = {"positive": (8, 10), "neutral": (4, 7), "negative": (1, 3)}
MIN_COMPONENTS_FOR_AVERAGE = 4  # of 6

COMPONENTS = ["earnings", "fundamental", "relative_valuation", "risk", "price_momentum", "insider_trading"]

# Surprise: |actual - mean| / |mean| > 2% => positive/negative, else in-line
SURPRISE_THRESHOLD = 0.02

FUNDAMENTAL_PILLARS = {
    "profitability": {
        "revenue_growth": "(Net Sales - Previous Net Sales) / Previous Net Sales",
        "gross_margin": "Gross Profit / Net Sales",
        "return_on_equity": "Net Income / Total Equity",
        "net_margin": "Net Profit / Net Sales",
    },
    "debt": {
        "current_ratio": "Current Assets / Current Liabilities",
        "debt_to_capital": "Total Debt / Total Capital",
        "interest_funding": "(Interest Expense on Debt + Preferred Cash Dividends) / Funds from Operations",
        "interest_coverage": "EBIT / (Interest Expense on Debt + Preferred Cash Dividends)",
    },
    "earnings_quality": {
        "operating_cash_yield": "(Operating Cash Flow - Net Income) / Net Income",
        "accruals": "(Net Income - Operating CF - Investing CF) / Average Net Operating Assets",
        "days_sales_inventory": "365 / (COGS / Inventory)",
        "days_sales_receivables": "365 / (Net Sales / Receivables)",
    },
    "dividend": {  # requires a current dividend yield, else pillar dropped (not penalised)
        "dividend_growth": "(DPS - Previous DPS) / Previous DPS",
        "dividend_funding": "Dividends / Operating Cash Flow",
        "dividend_coverage": "(Pre-Tax Income + Interest Expense) / (Interest Expense + Dividends)",
        "dividend_yield": "Annual DPS / Current Price",
    },
}
PILLAR_WEIGHT = 0.25
MIN_FUNDAMENTAL_PILLARS = 2

# higher is better? (False => decile direction flipped). TODO: confirm directions for ambiguous ratios in calibration.
LOWER_IS_BETTER = {"debt_to_capital", "interest_funding", "accruals", "days_sales_inventory",
                   "days_sales_receivables", "dividend_funding"}

RELATIVE_VALUATION = {"price_to_sales": 1/3, "trailing_pe": 1/3, "forward_pe": 1/3}
RISK = {"magnitude_of_returns": .25, "volatility": .25, "beta": .25, "correlation": .25}
MIN_RISK_FACTORS = 2
MOMENTUM = {"relative_strength": .5, "seasonality": .5}
EARNINGS = {"surprises": 1/3, "estimate_revisions": 1/3, "recommendation_changes": 1/3}
MIN_EARNINGS_FACTORS = 2
INSIDER = {"short_term": .7, "long_term": .3}

# Mean-estimate trend: 30d for quarters, 90d for years; revisions window 4 weeks; rec changes 120 days.
REVISION_WINDOW_DAYS = 28
REC_CHANGE_WINDOW_DAYS = 120
# Surprise size buckets by market cap: Large top 5.55%, Mid next 13.87%, Small next 34.68%, Micro rest 45.9%
CAP_BUCKETS = [("Large", 0.0555), ("Mid", 0.1387), ("Small", 0.3468), ("Micro", 0.459)]
# Insider: open-market only, exclude derivative exercises; buys/sells >$100k flagged (verify in p.12 text)
