"use client"

import type { Report } from "@/lib/types"
import { getCitationStyle } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScoreGauge } from "@/components/score-gauge"

interface OverviewTabProps {
  report: Report
  benchmark?: number | null
}

function DimensionBar({ label, value, weight, color }: { label: string; value: number; weight: string; color: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-xs text-muted-foreground">{weight}</span>
      </div>
      <div className="h-3 w-full rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
        />
      </div>
      <p className="text-right text-sm font-bold mt-0.5">{Math.round(value)}</p>
    </div>
  )
}

export function OverviewTab({ report, benchmark }: OverviewTabProps) {
  const { score, verdicts } = report

  return (
    <div className="mt-4 space-y-6">
      {/* Score gauge + benchmark */}
      <div className="flex flex-col items-center gap-4">
        <ScoreGauge score={score.overall} size={200} />
        {benchmark != null && (
          <p className="text-sm text-muted-foreground">
            Benchmark da especialidade:{" "}
            <span className="font-semibold">{Math.round(benchmark)}</span>
            {" — "}
            {score.overall >= benchmark ? (
              <span className="text-green-600">acima da média</span>
            ) : (
              <span className="text-amber-600">abaixo da média</span>
            )}
          </p>
        )}
      </div>

      {/* Dimensions */}
      <Card>
        <CardHeader>
          <CardTitle>Dimensões de Visibilidade</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <DimensionBar label="Visibilidade" value={score.visibility} weight="65%" color="bg-blue-500" />
          <DimensionBar label="Dominância Competitiva" value={score.dominance} weight="35%" color="bg-emerald-500" />
          {/* Indirect presence — informational */}
          <div className="border-t pt-4">
            <div className="flex items-baseline justify-between mb-1">
              <span className="text-sm font-medium text-muted-foreground">Presença Indireta</span>
              <span className="text-xs text-muted-foreground">informativo</span>
            </div>
            <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-amber-400"
                style={{ width: `${Math.min(100, Math.max(0, score.indirect_presence))}%` }}
              />
            </div>
            <p className="text-right text-sm font-medium text-muted-foreground mt-0.5">{Math.round(score.indirect_presence)}</p>
          </div>
        </CardContent>
      </Card>

      {/* Prompt Performance Grid */}
      <Card>
        <CardHeader>
          <CardTitle>Performance por Prompt</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {verdicts.map((v, i) => {
              const style = getCitationStyle(v.citation_type)
              return (
                <div
                  key={v.prompt_id}
                  className={`rounded-lg border p-3 text-center ${style.bg} ${style.border}`}
                >
                  <p className={`text-xs font-semibold ${style.text}`}>
                    P{i + 1}
                  </p>
                  <p className={`mt-1 text-[10px] ${style.text}`}>
                    {style.label}
                  </p>
                  {v.position != null && (
                    <p className={`mt-0.5 text-[10px] ${style.text}`}>
                      #{v.position}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
