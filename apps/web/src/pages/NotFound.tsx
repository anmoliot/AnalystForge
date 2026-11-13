import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-6 text-center">
      <Compass className="size-8 text-muted" aria-hidden="true" />
      <p className="panel-title">404</p>
      <h1 className="text-lg font-semibold">This page does not exist</h1>
      <p className="max-w-sm text-xs text-muted">
        The link may be out of date, or the resource may have been moved within the workspace.
      </p>
      <Link to="/">
        <Button size="sm">Return to overview</Button>
      </Link>
    </div>
  );
}
