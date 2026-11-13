import { Briefcase } from "lucide-react";

import { ModuleScaffold } from "@/pages/ModuleScaffold";

export default function Portfolios() {
  return (
    <ModuleScaffold
      icon={Briefcase}
      title="Portfolios"
      description="Transaction ledger, multi-currency cost basis, time- and money-weighted performance, Brinson attribution, risk analytics and constrained optimisation."
      status="No portfolios exist. Create a portfolio and import transactions to unlock analytics."
      capabilities={[
        "TWR, XIRR and benchmark-relative attribution",
        "VaR/CVaR, stress tests and rolling risk statistics",
        "Mean-variance, risk-parity and Black-Litterman optimisation",
        "CSV/Excel import with validation report",
      ]}
    />
  );
}
