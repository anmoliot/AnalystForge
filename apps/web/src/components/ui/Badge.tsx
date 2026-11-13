import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type Tone = "neutral" | "accent" | "positive" | "negative" | "warning";

const tones: Record<Tone, string> = {
  neutral: "border-line bg-elevated text-muted",
  accent: "border-accent/30 bg-accent/10 text-accent",
  positive: "border-positive/30 bg-positive/10 text-positive",
  negative: "border-negative/30 bg-negative/10 text-negative",
  warning: "border-warning/30 bg-warning/10 text-warning",
};

export function Badge({
  className,
  tone = "neutral",
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded border px-1.5 font-mono text-2xs font-medium uppercase tracking-wide",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}
