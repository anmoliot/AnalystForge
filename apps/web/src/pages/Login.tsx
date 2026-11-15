import { Lock, Mail, Building, User, ArrowRight, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";
import { useAuth } from "@/stores/auth";

export default function Login() {
  const navigate = useNavigate();
  const setAuth = useAuth((s) => s.setAuth);

  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleDemoFill = () => {
    setEmail("analyst@apexcap.com");
    setPassword("Password123!");
    setFullName("Jane Doe");
    setTenantName("Apex Capital");
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (mode === "register") {
        await api.post<{ id: string; email: string }>("/api/v1/auth/register", {
          email,
          password,
          full_name: fullName,
          tenant_name: tenantName,
        });
      }

      // Login
      const loginPayload: Record<string, string> = { email, password };
      if (totpCode.trim()) {
        loginPayload.totp_code = totpCode.trim();
      }

      const res = await api.post<{ access_token: string; refresh_token: string; token_type: string }>(
        "/api/v1/auth/login",
        loginPayload,
      );

      // Fetch user profile
      const me = await api.get<{
        id: string;
        email: string;
        full_name: string;
        role: "ADMIN" | "PORTFOLIO_MANAGER" | "ANALYST" | "READ_ONLY";
        tenant_id: string;
        tenant_name?: string;
      }>("/api/v1/auth/me", {
        headers: { Authorization: `Bearer ${res.access_token}` },
      });

      setAuth(res.access_token, me);
      navigate("/portfolios");
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Authentication failed. Please verify credentials.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[80vh] items-center justify-center p-4">
      <Panel className="w-full max-w-md border-line bg-panel p-6 shadow-xl">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-lg bg-accent/15">
            <ShieldCheck className="size-6 text-accent" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">AnalystForge Access</h1>
          <p className="mt-1 text-xs text-muted">
            Institutional investment analysis, risk modeling & portfolio execution
          </p>
        </div>

        {/* Tab switch */}
        <div className="mb-6 flex rounded border border-line bg-elevated p-0.5">
          <button
            type="button"
            onClick={() => {
              setMode("login");
              setError(null);
            }}
            className={`flex-1 rounded py-1.5 text-xs font-medium transition-colors ${
              mode === "login" ? "bg-panel text-ink shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("register");
              setError(null);
            }}
            className={`flex-1 rounded py-1.5 text-xs font-medium transition-colors ${
              mode === "register" ? "bg-panel text-ink shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            Register Firm
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-400">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === "register" && (
            <>
              <div>
                <label className="mb-1 block text-2xs font-medium uppercase tracking-wider text-muted">
                  Organization / Firm Name
                </label>
                <div className="relative">
                  <Building className="absolute left-3 top-2.5 size-4 text-muted" />
                  <input
                    type="text"
                    required
                    value={tenantName}
                    onChange={(e) => setTenantName(e.target.value)}
                    placeholder="e.g. Apex Capital Management"
                    className="w-full rounded border border-line bg-elevated py-2 pl-9 pr-3 text-xs text-ink placeholder:text-muted/60 focus:border-accent focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-2xs font-medium uppercase tracking-wider text-muted">
                  Full Name
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-2.5 size-4 text-muted" />
                  <input
                    type="text"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="e.g. Jane Doe"
                    className="w-full rounded border border-line bg-elevated py-2 pl-9 pr-3 text-xs text-ink placeholder:text-muted/60 focus:border-accent focus:outline-none"
                  />
                </div>
              </div>
            </>
          )}

          <div>
            <label className="mb-1 block text-2xs font-medium uppercase tracking-wider text-muted">
              Corporate Email
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-2.5 size-4 text-muted" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="analyst@hedgefund.com"
                className="w-full rounded border border-line bg-elevated py-2 pl-9 pr-3 text-xs text-ink placeholder:text-muted/60 focus:border-accent focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-2xs font-medium uppercase tracking-wider text-muted">
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 size-4 text-muted" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full rounded border border-line bg-elevated py-2 pl-9 pr-3 text-xs text-ink placeholder:text-muted/60 focus:border-accent focus:outline-none"
              />
            </div>
          </div>

          {mode === "login" && (
            <div>
              <div className="flex items-center justify-between">
                <label className="mb-1 block text-2xs font-medium uppercase tracking-wider text-muted">
                  2FA Authenticator Code <span className="text-muted/50">(optional)</span>
                </label>
                <Badge tone="neutral">6 digits</Badge>
              </div>
              <input
                type="text"
                maxLength={6}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                placeholder="123456"
                className="w-full rounded border border-line bg-elevated py-2 px-3 font-mono text-xs text-ink placeholder:text-muted/60 focus:border-accent focus:outline-none"
              />
            </div>
          )}

          <Button type="submit" disabled={loading} className="w-full justify-center">
            {loading ? "Authenticating..." : mode === "login" ? "Sign In" : "Create Firm Account"}
            <ArrowRight className="ml-1.5 size-3.5" />
          </Button>
        </form>

        <div className="mt-5 border-t border-line/60 pt-4 text-center">
          <button
            type="button"
            onClick={handleDemoFill}
            className="text-2xs font-medium text-accent hover:underline"
          >
            Quick-fill demo analyst credentials
          </button>
        </div>
      </Panel>
    </div>
  );
}
