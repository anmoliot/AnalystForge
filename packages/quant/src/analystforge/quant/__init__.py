"""AnalystForge quantitative core.

Pure functions and data containers only: this package must never import web,
database or provider libraries. All monetary results use :class:`decimal.Decimal`.
"""

from analystforge.quant.dcf import (
    DCFAssumptions,
    DCFResult,
    ForecastYear,
    TerminalValueMethod as DCFTerminalValueMethod,
    project_fcff,
    run_dcf,
)
from analystforge.quant.ddm import (
    DividendYear,
    GordonGrowthResult,
    MultiStageDDMAssumptions,
    MultiStageDDMResult,
    gordon_growth_ddm,
    multi_stage_ddm,
)
from analystforge.quant.fcfe import (
    FCFEAssumptions,
    FCFEResult,
    FCFEYearForecast,
    TerminalValueMethod as FCFETerminalValueMethod,
    fcfe_valuation,
)
from analystforge.quant.football_field import (
    FootballFieldResult,
    ValuationRange,
    build_football_field,
)
from analystforge.quant.money import ONE, ZERO, discount_factor, quantize, to_decimal
from analystforge.quant.multiples import (
    MultipleInputs,
    MultipleResult,
    MultipleUnit,
    PeerStats,
    compute_multiples,
    implied_enterprise_value,
    implied_equity_value,
    implied_share_price,
    peer_statistics,
)
from analystforge.quant.precedents import (
    PrecedentAnalysisResult,
    PrecedentDeal,
    precedent_transactions_valuation,
)
from analystforge.quant.residual_income import (
    ResidualIncomeAssumptions,
    ResidualIncomeResult,
    ResidualIncomeTerminalMethod,
    ResidualIncomeYear,
    residual_income_valuation,
)
from analystforge.quant.sotp import (
    SegmentValuation,
    SOTPResult,
    sotp_valuation,
)
from analystforge.quant.wacc import (
    WACCResult,
    after_tax_cost_of_debt,
    blume_adjusted_beta,
    capm_cost_of_equity,
    compute_wacc,
    relever_beta,
    unlever_beta,
    wacc_from_capm,
)

__version__ = "0.1.0"

__all__ = [
    "DCFAssumptions",
    "DCFResult",
    "DCFTerminalValueMethod",
    "DividendYear",
    "FCFEAssumptions",
    "FCFEResult",
    "FCFETerminalValueMethod",
    "FCFEYearForecast",
    "FootballFieldResult",
    "ForecastYear",
    "GordonGrowthResult",
    "MultipleInputs",
    "MultipleResult",
    "MultipleUnit",
    "MultiStageDDMAssumptions",
    "MultiStageDDMResult",
    "ONE",
    "PeerStats",
    "PrecedentAnalysisResult",
    "PrecedentDeal",
    "ResidualIncomeAssumptions",
    "ResidualIncomeResult",
    "ResidualIncomeTerminalMethod",
    "ResidualIncomeYear",
    "SOTPResult",
    "SegmentValuation",
    "ValuationRange",
    "WACCResult",
    "ZERO",
    "after_tax_cost_of_debt",
    "blume_adjusted_beta",
    "build_football_field",
    "capm_cost_of_equity",
    "compute_multiples",
    "compute_wacc",
    "discount_factor",
    "fcfe_valuation",
    "gordon_growth_ddm",
    "implied_enterprise_value",
    "implied_equity_value",
    "implied_share_price",
    "multi_stage_ddm",
    "peer_statistics",
    "precedent_transactions_valuation",
    "project_fcff",
    "quantize",
    "relever_beta",
    "residual_income_valuation",
    "run_dcf",
    "sotp_valuation",
    "to_decimal",
    "unlever_beta",
    "wacc_from_capm",
]
