"use client"

import { Badge } from "@/components/ui/badge"
import { getScoreColor, getScoreLabel } from "@/lib/utils"

interface ScoreBadgeProps {
  score: number | null | undefined
  showLabel?: boolean
}

export function ScoreBadge({ score, showLabel = false }: ScoreBadgeProps) {
  const color = getScoreColor(score)
  const label = getScoreLabel(score)

  if (score == null) {
    return (
      <Badge variant="secondary" className="tabular-nums">
        —
      </Badge>
    )
  }

  return (
    <Badge
      className="tabular-nums gap-1"
      style={{
        backgroundColor: `${color}15`,
        color: color,
        borderColor: `${color}30`,
      }}
    >
      {Math.round(score)}
      {showLabel && <span className="font-normal">({label})</span>}
    </Badge>
  )
}
