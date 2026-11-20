import { Check, CircleAlert, Clock3, LoaderCircle, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
const labels: Record<string, string> = {
  ready: "Ready",
  queued: "Queued",
  running: "Processing",
  failed: "Failed",
  cancelled: "Cancelled",
  succeeded: "Complete",
};
export function DocumentStatus({ status }: { status: string }) {
  const Icon = ["ready", "succeeded"].includes(status)
    ? Check
    : status === "failed"
      ? CircleAlert
      : status === "running"
        ? LoaderCircle
        : status === "cancelled"
          ? X
          : Clock3;
  return (
    <Badge
      className={`gap-1.5 whitespace-nowrap ${status === "failed" ? "border-destructive/30 bg-destructive/10 text-destructive" : "border-border/60 bg-secondary/60 text-foreground"}`}
    >
      <Icon
        className={`size-3 ${status === "running" ? "animate-spin motion-reduce:animate-none" : ""}`}
        aria-hidden
      />
      {labels[status] ?? status}
    </Badge>
  );
}
