import { Panel } from "@/components/ui/Panel";
import { useAuth } from "@/stores/auth";

export default function Settings() {
  const { user } = useAuth();
  return <div className="space-y-4">
    <h1 className="text-xl font-semibold">Account & System Settings</h1>
    <Panel className="space-y-2 p-5">
      {user ? <>
        <p>{user.full_name}</p><p>{user.email}</p><p>Role {user.role}</p>
        <p>Tenant {user.tenant_id}</p><p>Two-factor authentication {user.totp_enabled ? "enabled" : "disabled"}</p>
      </> : <p>Account details unavailable. Sign in to view your account.</p>}
      <p>API key and TOTP management are available through the authenticated API.</p>
      <a href="/docs">Open API reference</a>
    </Panel>
  </div>;
}
