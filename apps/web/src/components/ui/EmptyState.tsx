import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-6 py-10 text-center",
        className,
      )}
    >
      <div className="flex size-9 items-center justify-center rounded-full border border-line bg-elevated">
        <Icon className="size-4 text-muted" aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-ink">{title}</p>
        <div className="max-w-sm text-xs leading-relaxed text-muted">{description}</div>
      </div>
      {action}
    </div>
  );
}
