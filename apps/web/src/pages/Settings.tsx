import { Settings as SettingsIcon } from "lucide-react";

import { ModuleScaffold } from "@/pages/ModuleScaffold";

export default function Settings() {
  return (
    <ModuleScaffold
      icon={SettingsIcon}
      title="Settings"
      description="Profile, security (2FA and sessions), API keys, notification preferences and workspace appearance."
      status="Authentication is not enabled in this build, so account settings are unavailable."
      capabilities={[
        "TOTP two-factor authentication and session revocation",
        "Scoped, rotating API keys",
        "Notification channel preferences",
        "Theme and density preferences",
      ]}
    />
  );
}
