import { Sparkles } from "lucide-react";

import { ModuleScaffold } from "@/pages/ModuleScaffold";

export default function Research() {
  return (
    <ModuleScaffold
      icon={Sparkles}
      title="Research assistant"
      description="Ask grounded questions over filings, news, transcripts and your own documents. Every answer cites the exact source passage or refuses when evidence is insufficient."
      status="The document corpus is empty. Ingest filings and news, or upload your own documents, before asking research questions."
      capabilities={[
        "Retrieval-augmented answers with passage citations",
        "FinBERT sentiment per article and per ticker over time",
        "Filing diff reader for risk factors and MD&A",
        "Audited tool calls: ratios, prices, screens and DCF",
      ]}
    />
  );
}
