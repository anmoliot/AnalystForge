import { SlidersHorizontal } from "lucide-react";

import { ModuleScaffold } from "@/pages/ModuleScaffold";

export default function Screener() {
  return (
    <ModuleScaffold
      icon={SlidersHorizontal}
      title="Screener"
      description="Build nested fundamental, technical and growth filters, save screens, run them on a schedule and export the full result set."
      status="Screens need an instrument universe with computed fundamentals. Load the data pipeline before creating a screen."
      capabilities={[
        "AND/OR filter groups across every computed metric",
        "Saved screens with scheduled refresh and alerts",
        "Sortable, exportable result grid",
        "Universe and exchange selection",
      ]}
    />
  );
}
