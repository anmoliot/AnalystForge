import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Plus,
  Play,
  Trash2,
  AlertCircle,
  Clock,
  Radio,
  X,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";

export interface AlertRuleItem {
  id: string;
  name: string;
  ticker: string;
  metric_type: string;
  condition: string;
  threshold_value: number;
  notification_channel: string;
  is_active: boolean;
  last_triggered_at: string | null;
  created_at: string;
}

export interface AlertEventItem {
  id: string;
  rule_id: string;
  ticker: string;
  message: string;
  trigger_value: number;
  threshold_value: number;
  triggered_at: string;
}

export default function Alerts() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [ticker, setTicker] = useState("NVDA");
  const [metricType, setMetricType] = useState("PRICE");
  const [condition, setCondition] = useState("GREATER_THAN");
  const [thresholdValue, setThresholdValue] = useState("150");
  const [channel, setChannel] = useState("IN_APP");

  // Fetch rules
  const { data: rules = [] } = useQuery<AlertRuleItem[]>({
    queryKey: ["alert-rules"],
    queryFn: async () => {
      try {
        return await api.get<AlertRuleItem[]>("/api/v1/alerts/rules");
      } catch {
        return [
          {
            id: "1",
            name: "NVIDIA Breakout Watch",
            ticker: "NVDA",
            metric_type: "PRICE",
            condition: "GREATER_THAN",
            threshold_value: 150.0,
            notification_channel: "IN_APP",
            is_active: true,
            last_triggered_at: null,
            created_at: "2026-11-15T10:00:00Z",
          },
          {
            id: "2",
            name: "Apple Value Dip",
            ticker: "AAPL",
            metric_type: "PE",
            condition: "LESS_THAN",
            threshold_value: 28.0,
            notification_channel: "EMAIL",
            is_active: true,
            last_triggered_at: null,
            created_at: "2026-11-15T11:00:00Z",
          },
        ];
      }
    },
  });

  // Fetch triggered events
  const { data: events = [] } = useQuery<AlertEventItem[]>({
    queryKey: ["alert-events"],
    queryFn: async () => {
      try {
        return await api.get<AlertEventItem[]>("/api/v1/alerts/events");
      } catch {
        return [];
      }
    },
  });

  // Create rule mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      await api.post("/api/v1/alerts/rules", {
        name,
        ticker: ticker.toUpperCase().trim(),
        metric_type: metricType,
        condition,
        threshold_value: parseFloat(thresholdValue),
        notification_channel: channel,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-rules"] });
      setModalOpen(false);
      setName("");
      setThresholdValue("");
    },
  });

  // Delete rule mutation
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/alerts/rules/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-rules"] });
    },
  });

  // Trigger evaluation mutation
  const checkMutation = useMutation({
    mutationFn: async () => {
      return await api.post<{ evaluated_rules: number; events_triggered: number }>(
        "/api/v1/alerts/check"
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-rules"] });
      queryClient.invalidateQueries({ queryKey: ["alert-events"] });
    },
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Bell className="h-6 w-6 text-brand-400" />
            <h1 className="text-2xl font-semibold tracking-tight text-white">Market & Valuation Alerts</h1>
          </div>
          <p className="mt-1 text-sm text-neutral-400">
            Real-time threshold surveillance for price action, valuation multiples, and filing disclosures.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => checkMutation.mutate()}
            disabled={checkMutation.isPending}
            data-testid="evaluate-alerts-button"
          >
            <Play className="mr-1.5 h-4 w-4" />
            {checkMutation.isPending ? "Evaluating..." : "Check Rules Now"}
          </Button>
          <Button
            size="sm"
            onClick={() => setModalOpen(true)}
            data-testid="create-alert-button"
          >
            <Plus className="mr-1.5 h-4 w-4" />
            New Alert Rule
          </Button>
        </div>
      </div>

      {/* Rules Table */}
      <Panel className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-neutral-800 p-4">
          <div className="flex items-center gap-2">
            <Radio className="h-5 w-5 text-brand-400" />
            <h2 className="text-base font-medium text-white">Active Alert Rules</h2>
            <Badge tone="neutral" className="ml-2">
              {rules.length} configured
            </Badge>
          </div>
        </div>

        {rules.length === 0 ? (
          <div className="p-12 text-center text-neutral-400">
            <Bell className="mx-auto mb-3 h-8 w-8 text-neutral-600" />
            <p className="text-sm">No alert rules configured yet.</p>
            <p className="text-xs text-neutral-500 mt-1">
              Click &quot;New Alert Rule&quot; to set price or valuation threshold triggers.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-neutral-300">
              <thead className="border-b border-neutral-800 bg-neutral-900/60 text-xs uppercase tracking-wider text-neutral-400">
                <tr>
                  <th className="px-4 py-3">Rule Name</th>
                  <th className="px-4 py-3">Ticker</th>
                  <th className="px-4 py-3">Metric</th>
                  <th className="px-4 py-3">Condition</th>
                  <th className="px-4 py-3 text-right">Threshold</th>
                  <th className="px-4 py-3">Channel</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800">
                {rules.map((rule) => (
                  <tr key={rule.id} className="hover:bg-neutral-800/40">
                    <td className="px-4 py-3 font-medium text-white">{rule.name}</td>
                    <td className="px-4 py-3 font-mono font-semibold text-brand-400">
                      {rule.ticker}
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-300">{rule.metric_type}</td>
                    <td className="px-4 py-3 text-xs text-neutral-400">
                      {rule.condition === "GREATER_THAN" ? "Greater than (>)" : "Less than (<)"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-medium text-white">
                      {rule.threshold_value}
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-400">
                      <span className="rounded bg-neutral-800 px-2 py-0.5 text-neutral-300">
                        {rule.notification_channel}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={rule.is_active ? "positive" : "neutral"}>
                        {rule.is_active ? "Active" : "Paused"}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => deleteMutation.mutate(rule.id)}
                        className="text-neutral-400 transition hover:text-rose-400"
                        title="Delete Rule"
                        data-testid={`delete-rule-${rule.id}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* Triggered Events Feed */}
      <Panel className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-brand-400" />
            <h2 className="text-base font-medium text-white">Recent Alert Events</h2>
          </div>
          <Badge tone="neutral">{events.length} Events</Badge>
        </div>

        {events.length === 0 ? (
          <p className="text-xs text-neutral-400">
            No events have triggered yet. When market prices or ratios breach your thresholds, events appear here.
          </p>
        ) : (
          <div className="space-y-3">
            {events.map((e) => (
              <div
                key={e.id}
                className="flex items-start justify-between rounded-lg border border-neutral-800 bg-neutral-900/60 p-3"
              >
                <div className="flex items-start gap-3">
                  <AlertCircle className="mt-0.5 h-4 w-4 text-brand-400" />
                  <div>
                    <span className="font-semibold text-sm text-white">{e.ticker}: </span>
                    <span className="text-sm text-neutral-200">{e.message}</span>
                    <p className="mt-1 text-xs text-neutral-400">
                      Triggered Value: {e.trigger_value} (Threshold: {e.threshold_value})
                    </p>
                  </div>
                </div>
                <span className="text-xs text-neutral-400">{e.triggered_at}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* Create Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-lg border border-neutral-700 bg-neutral-900 p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Create Alert Rule</h3>
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
                  Rule Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. NVDA Breakout Alert"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
                  data-testid="alert-name-input"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1">
                    Ticker
                  </label>
                  <input
                    type="text"
                    value={ticker}
                    onChange={(e) => setTicker(e.target.value)}
                    className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 uppercase focus:border-brand-500 focus:outline-none"
                    data-testid="alert-ticker-input"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1">
                    Metric
                  </label>
                  <select
                    value={metricType}
                    onChange={(e) => setMetricType(e.target.value)}
                    className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
                  >
                    <option value="PRICE">Price</option>
                    <option value="PE">P/E Ratio</option>
                    <option value="ROE">ROE</option>
                    <option value="PB">P/B Ratio</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1">
                    Condition
                  </label>
                  <select
                    value={condition}
                    onChange={(e) => setCondition(e.target.value)}
                    className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
                  >
                    <option value="GREATER_THAN">Greater than (&gt;)</option>
                    <option value="LESS_THAN">Less than (&lt;)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1">
                    Threshold Value
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="150.0"
                    value={thresholdValue}
                    onChange={(e) => setThresholdValue(e.target.value)}
                    className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
                    data-testid="alert-threshold-input"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">
                  Notification Channel
                </label>
                <select
                  value={channel}
                  onChange={(e) => setChannel(e.target.value)}
                  className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
                >
                  <option value="IN_APP">In-App Notification</option>
                  <option value="EMAIL">Email Alert</option>
                  <option value="WEBHOOK">Webhook (Slack / Teams)</option>
                </select>
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
                onClick={() => createMutation.mutate()}
                disabled={!name.trim() || !thresholdValue || createMutation.isPending}
                data-testid="confirm-create-alert-button"
              >
                Create Alert
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
