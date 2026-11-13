import { Calculator } from "lucide-react";

import { ModuleScaffold } from "@/pages/ModuleScaffold";

export default function Valuation() {
  return (
    <ModuleScaffold
      icon={Calculator}
      title="Valuation workbench"
      description="Driver-based DCF and WACC models, comparable companies, precedent transactions, scenario analysis, Monte Carlo and Excel-native exports."
      status="No valuation models exist yet. Open a company with fundamental data to start a model."
      capabilities={[
        "FCFF/FCFE DCF with full assumption audit trail",
        "WACC builder with regression beta and FRED risk-free rate",
        "Bear/base/bull scenarios and WACC × growth sensitivity",
        "Excel export with live formulas and model versioning",
      ]}
    />
  );
}
