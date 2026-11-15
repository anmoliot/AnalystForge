import {
  Settings as SettingsIcon,
  Shield,
  Key,
  User,
  CheckCircle2,
  Copy,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { useAuth } from "@/stores/auth";

export default function Settings() {
  const { user } = useAuth();
  const [copiedKey, setCopiedKey] = useState(false);
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(false);

  const mockApiKey = "af_live_948f29c4819d4b0ea772839bce";

  const handleCopy = () => {
    navigator.clipboard?.writeText(mockApiKey);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <SettingsIcon className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-semibold tracking-tight text-white">Account & System Settings</h1>
        </div>
        <p className="mt-1 text-sm text-neutral-400">
          Manage your analyst profile, API access keys, multi-factor authentication, and terminal preferences.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Profile Card */}
        <Panel className="p-6">
          <div className="mb-4 flex items-center justify-between border-b border-neutral-800 pb-3">
            <div className="flex items-center gap-2">
              <User className="h-5 w-5 text-brand-400" />
              <h2 className="text-base font-medium text-white">Analyst Profile</h2>
            </div>
            <Badge tone="accent">{user?.role || "ANALYST"}</Badge>
          </div>

          <div className="space-y-3 text-sm">
            <div>
              <span className="text-xs text-neutral-400">Full Name</span>
              <p className="font-medium text-white">{user?.full_name || "Institutional Analyst"}</p>
            </div>
            <div>
              <span className="text-xs text-neutral-400">Email Address</span>
              <p className="font-mono text-neutral-200">{user?.email || "analyst@hedgefund.com"}</p>
            </div>
            <div>
              <span className="text-xs text-neutral-400">Firm / Tenant</span>
              <p className="text-neutral-200">{user?.tenant_name || "Alpha Investment Management"}</p>
            </div>
          </div>
        </Panel>

        {/* Security & 2FA */}
        <Panel className="p-6">
          <div className="mb-4 flex items-center justify-between border-b border-neutral-800 pb-3">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-brand-400" />
              <h2 className="text-base font-medium text-white">Security & 2FA</h2>
            </div>
            <Badge tone={twoFactorEnabled ? "positive" : "neutral"}>
              {twoFactorEnabled ? "Enabled" : "Standard"}
            </Badge>
          </div>

          <p className="text-xs text-neutral-400 leading-relaxed">
            Protect your research models and proprietary trading strategies with Time-based One-Time Password (TOTP) two-factor authentication.
          </p>

          <div className="mt-4 flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900/60 p-3">
            <div>
              <p className="text-sm font-medium text-white">TOTP Authenticator</p>
              <p className="text-xs text-neutral-400">Google Authenticator, 1Password, or YubiKey</p>
            </div>
            <Button
              variant={twoFactorEnabled ? "secondary" : "primary"}
              size="sm"
              onClick={() => setTwoFactorEnabled(!twoFactorEnabled)}
            >
              {twoFactorEnabled ? "Disable" : "Enable 2FA"}
            </Button>
          </div>
        </Panel>

        {/* API Access Keys */}
        <Panel className="p-6 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between border-b border-neutral-800 pb-3">
            <div className="flex items-center gap-2">
              <Key className="h-5 w-5 text-brand-400" />
              <h2 className="text-base font-medium text-white">Developer API Keys</h2>
            </div>
            <Badge tone="neutral">Python SDK & CLI</Badge>
          </div>

          <p className="text-xs text-neutral-400 leading-relaxed mb-4">
            Use your personal API key to query the quantitative library, execute backtests, and pull market fundamentals via the <code className="text-brand-300">analystforge-sdk</code> Python package.
          </p>

          <div className="flex items-center gap-3 rounded-lg border border-neutral-800 bg-neutral-950 p-3 font-mono text-sm text-neutral-300">
            <span className="flex-1 truncate">{mockApiKey}</span>
            <Button variant="secondary" size="sm" onClick={handleCopy}>
              {copiedKey ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
              <span className="ml-1.5">{copiedKey ? "Copied" : "Copy Key"}</span>
            </Button>
          </div>
        </Panel>
      </div>
    </div>
  );
}
