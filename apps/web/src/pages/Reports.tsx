import { FileText } from "lucide-react";

import { ModuleScaffold } from "@/pages/ModuleScaffold";

export default function Reports() {
  return (
    <ModuleScaffold
      icon={FileText}
      title="Reports & exports"
      description="Company tear sheets, portfolio reviews and risk reports as PDF, Excel with live formulas, CSV and PowerPoint — scheduled or on demand."
      status="No reports have been generated. Reports become available once company, portfolio or valuation data exists."
      capabilities={[
        "Branded PDF and PowerPoint tear sheets",
        "Excel exports preserving formulas",
        "Scheduled email delivery",
        "Shareable read-only links",
      ]}
    />
  );
}
