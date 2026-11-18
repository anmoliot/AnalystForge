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
  metadata?: Record<string, unknown>;
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
  const { data: reports = [], error: listError } = useQuery<ReportItem[]>({
    queryKey: ["reports-list"],
    queryFn: async () => {
      return api.get<ReportItem[]>("/api/v1/reports");
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

  const download = useMutation({
    mutationFn: async (id: string) => {
      const token = localStorage.getItem("af-token");
      const response = await fetch("/api/v1/reports/" + id + "/download", {
        headers: token ? { Authorization: "Bearer " + token } : {},
      });
      if (!response.ok) throw new Error("Report download failed (HTTP " + response.status + ").");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = response.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] ?? "report";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });

  return (
    <div className="space-y-6">
      {listError && <p role="alert">Unavailable. {listError.message}</p>}
      {download.error && <p role="alert">{download.error.message}</p>}
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <FileText className="h-6 w-6 text-accent" />
            <h1 className="text-2xl font-semibold tracking-tight text-ink">Institutional Reports & Tearsheets</h1>
          </div>
          <p className="mt-1 text-sm text-muted">
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
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink">
              Generated Reports ({reports.length})
            </h2>
          </div>

          {reports.length === 0 ? (
            <div className="p-8 text-center text-xs text-muted">
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
                      : "hover:bg-elevated/40"
                  }`}
                  data-testid={`report-card-${r.id}`}
                >
                  <div className="flex items-start justify-between">
                    <span className="font-medium text-sm text-ink">{r.title}</span>
                    <Badge tone="neutral" className="text-[10px]">
                      {r.format}
                    </Badge>
                  </div>
                  <div className="mt-2 flex items-center justify-between text-xs text-muted">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-elevated px-1.5 py-0.5 font-mono text-[10px] text-ink">
                        {r.report_type}
                      </span>
                      {r.ticker && (
                        <span className="font-mono text-accent font-semibold">
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
                  <h3 className="text-lg font-semibold text-ink">{activeDetail.title}</h3>
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted">
                    <span>Type: {activeDetail.report_type}</span>
                    {activeDetail.ticker && <span>• Asset: {activeDetail.ticker}</span>}
                    <span>• Generated: {activeDetail.created_at}</span>
                  </div>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => download.mutate(activeDetail.id)}
                  data-testid="download-report-button"
                >
                  <Download className="mr-1.5 h-4 w-4" />
                  Download
                </Button>
              </div>

              <div className="prose prose-invert max-w-none rounded-lg border border-neutral-800 bg-elevated/60 p-6 font-mono text-xs leading-relaxed text-ink whitespace-pre-wrap">
                {activeDetail.content}
              </div>
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center p-12 text-center text-muted">
              <FileText className="mb-3 h-10 w-10 text-neutral-700" />
              <p className="text-sm font-medium text-muted">No Report Selected</p>
              <p className="mt-1 text-xs text-muted">
                Select a report from the archive or generate a new tearsheet to preview its contents.
              </p>
            </div>
          )}
        </Panel>
      </div>

      {/* Generate Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-lg border border-neutral-700 bg-elevated p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-ink">Generate Research Report</h3>
              <button
                onClick={() => setModalOpen(false)}
                className="text-muted hover:text-ink"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-muted mb-1">
                  Report Title
                </label>
                <input aria-label="Report Title"
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink focus:border-brand-500 focus:outline-none"
                  data-testid="report-title-input"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-muted mb-1">
                  Report Type
                </label>
                <select aria-label="Report Type"
                  value={reportType}
                  onChange={(e) => setReportType(e.target.value)}
                  className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink focus:border-brand-500 focus:outline-none"
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
                  <label className="block text-xs font-medium text-muted mb-1">
                    Ticker (Optional)
                  </label>
                  <input aria-label="Ticker (Optional)"
                    type="text"
                    value={ticker}
                    onChange={(e) => setTicker(e.target.value.toUpperCase())}
                    className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink uppercase focus:border-brand-500 focus:outline-none"
                    data-testid="report-ticker-input"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted mb-1">
                    Output Format
                  </label>
                  <select aria-label="Output Format"
                    value={format}
                    onChange={(e) => setFormat(e.target.value)}
                    className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink focus:border-brand-500 focus:outline-none"
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
