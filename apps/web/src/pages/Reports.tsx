import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  Download,
  Plus,
  X,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";

export interface ReportItem {
  id: string;
  title: string;
  report_type: string;
  ticker?: string;
  format: string;
  status: string;
  created_at: string;
}

export interface ReportDetail extends ReportItem {
  content: string;
  metadata?: Record<string, any>;
}

export default function Reports() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [title, setTitle] = useState("NVIDIA Equity Tearsheet");
  const [reportType, setReportType] = useState("TEARSHEET");
  const [ticker, setTicker] = useState("NVDA");
  const [format, setFormat] = useState("MARKDOWN");
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);

  // List reports
  const { data: reports = [] } = useQuery<ReportItem[]>({
    queryKey: ["reports-list"],
    queryFn: async () => {
      try {
        return await api.get<ReportItem[]>("/api/v1/reports");
      } catch {
        return [
          {
            id: "1",
            title: "NVIDIA Equity Tearsheet",
            report_type: "TEARSHEET",
            ticker: "NVDA",
            format: "MARKDOWN",
            status: "COMPLETED",
            created_at: new Date().toISOString(),
          },
          {
            id: "2",
            title: "Multi-Asset Factor Risk Memo",
            report_type: "PORTFOLIO_RISK",
            format: "MARKDOWN",
            status: "COMPLETED",
            created_at: new Date().toISOString(),
          },
        ];
      }
    },
  });

  // Selected report detail
  const { data: activeDetail } = useQuery<ReportDetail>({
    queryKey: ["report-detail", selectedReportId],
    enabled: !!selectedReportId,
    queryFn: async () => {
      return await api.get<ReportDetail>(`/api/v1/reports/${selectedReportId}`);
    },
  });

  // Generate mutation
  const generateMutation = useMutation({
    mutationFn: async () => {
      return await api.post<ReportItem>("/api/v1/reports/generate", {
        title: title.trim(),
        report_type: reportType,
        ticker: ticker ? ticker.toUpperCase().trim() : undefined,
        format,
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["reports-list"] });
      setModalOpen(false);
      setSelectedReportId(data.id);
    },
  });

  const handleDownload = (id: string, repTitle: string) => {
    const link = document.createElement("a");
    link.href = `/api/v1/reports/${id}/download`;
    link.setAttribute("download", `${repTitle.toLowerCase().replace(/\s+/g, "_")}.md`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <FileText className="h-6 w-6 text-brand-400" />
            <h1 className="text-2xl font-semibold tracking-tight text-white">Institutional Reports & Tearsheets</h1>
          </div>
          <p className="mt-1 text-sm text-neutral-400">
            Generate formal equity research tearsheets, risk memos, and DCF valuation summaries for distribution.
          </p>
        </div>
        <Button
          size="sm"
          onClick={() => setModalOpen(true)}
          data-testid="generate-report-button"
        >
          <Plus className="mr-1.5 h-4 w-4" />
          Generate Report
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Reports Archive */}
        <Panel className="overflow-hidden lg:col-span-1">
          <div className="flex items-center justify-between border-b border-neutral-800 p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-300">
              Generated Reports ({reports.length})
            </h2>
          </div>

          {reports.length === 0 ? (
            <div className="p-8 text-center text-xs text-neutral-500">
              No reports archived. Generate your first research tearsheet above.
            </div>
          ) : (
            <div className="divide-y divide-neutral-800">
              {reports.map((r) => (
                <div
                  key={r.id}
                  onClick={() => setSelectedReportId(r.id)}
                  className={`cursor-pointer p-4 transition ${
                    selectedReportId === r.id
                      ? "bg-brand-500/10 border-l-2 border-brand-500"
                      : "hover:bg-neutral-800/40"
                  }`}
                  data-testid={`report-card-${r.id}`}
                >
                  <div className="flex items-start justify-between">
                    <span className="font-medium text-sm text-white">{r.title}</span>
                    <Badge tone="neutral" className="text-[10px]">
                      {r.format}
                    </Badge>
                  </div>
                  <div className="mt-2 flex items-center justify-between text-xs text-neutral-400">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-neutral-800 px-1.5 py-0.5 font-mono text-[10px] text-neutral-300">
                        {r.report_type}
                      </span>
                      {r.ticker && (
                        <span className="font-mono text-brand-400 font-semibold">
                          {r.ticker}
                        </span>
                      )}
                    </div>
                    <span>{r.created_at.slice(0, 10)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        {/* Report Preview */}
        <Panel className="p-6 lg:col-span-2 min-h-[500px]">
          {activeDetail ? (
            <div>
              <div className="mb-4 flex items-center justify-between border-b border-neutral-800 pb-4">
                <div>
                  <h3 className="text-lg font-semibold text-white">{activeDetail.title}</h3>
                  <div className="mt-1 flex items-center gap-2 text-xs text-neutral-400">
                    <span>Type: {activeDetail.report_type}</span>
                    {activeDetail.ticker && <span>• Asset: {activeDetail.ticker}</span>}
                    <span>• Generated: {activeDetail.created_at}</span>
                  </div>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleDownload(activeDetail.id, activeDetail.title)}
                  data-testid="download-report-button"
                >
                  <Download className="mr-1.5 h-4 w-4" />
                  Download
                </Button>
              </div>

              <div className="prose prose-invert max-w-none rounded-lg border border-neutral-800 bg-neutral-900/60 p-6 font-mono text-xs leading-relaxed text-neutral-200 whitespace-pre-wrap">
                {activeDetail.content}
              </div>
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center p-12 text-center text-neutral-500">
              <FileText className="mb-3 h-10 w-10 text-neutral-700" />
              <p className="text-sm font-medium text-neutral-400">No Report Selected</p>
              <p className="mt-1 text-xs text-neutral-500">
                Select a report from the archive or generate a new tearsheet to preview its contents.
              </p>
            </div>
          )}
        </Panel>
      </div>

      {/* Generate Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-lg border border-neutral-700 bg-neutral-900 p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Generate Research Report</h3>
              <button
                onClick={() => setModalOpen(false)}
                className="text-neutral-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">
                  Report Title
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
                  data-testid="report-title-input"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">
                  Report Type
                </label>
                <select
                  value={reportType}
                  onChange={(e) => setReportType(e.target.value)}
                  className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
                  data-testid="report-type-select"
                >
                  <option value="TEARSHEET">Equity Tearsheet</option>
                  <option value="DCF_SUMMARY">DCF Valuation Model Summary</option>
                  <option value="PORTFOLIO_RISK">Portfolio Risk & Scenario Memo</option>
                  <option value="BACKTEST_PERFORMANCE">Strategy Backtest Performance</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1">
                    Ticker (Optional)
                  </label>
                  <input
                    type="text"
                    value={ticker}
                    onChange={(e) => setTicker(e.target.value.toUpperCase())}
                    className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 uppercase focus:border-brand-500 focus:outline-none"
                    data-testid="report-ticker-input"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1">
                    Output Format
                  </label>
                  <select
                    value={format}
                    onChange={(e) => setFormat(e.target.value)}
                    className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
                  >
                    <option value="MARKDOWN">Markdown Document</option>
                    <option value="PDF">PDF Tearsheet</option>
                    <option value="CSV">CSV Data Export</option>
                    <option value="JSON">JSON Structure</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setModalOpen(false)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => generateMutation.mutate()}
                disabled={!title.trim() || generateMutation.isPending}
                data-testid="confirm-generate-report-button"
              >
                Generate
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
