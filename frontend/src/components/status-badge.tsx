import { Badge } from "@/components/ui/badge"
import type { RunStatus } from "@/lib/types"

const statusConfig: Record<RunStatus, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  pending: { label: "Pendente", variant: "secondary" },
  running: { label: "Executando", variant: "outline" },
  completed: { label: "Concluído", variant: "default" },
  failed: { label: "Falhou", variant: "destructive" },
}

interface StatusBadgeProps {
  status: RunStatus
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status]
  return <Badge variant={config.variant}>{config.label}</Badge>
}
