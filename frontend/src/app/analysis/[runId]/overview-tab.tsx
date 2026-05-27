"use client"

import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts"

import type { Report } from "@/lib/types"
import { getCitationStyle } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScoreGauge } from "@/components/score-gauge"

interface OverviewTabProps {
  report: Report
  benchmark?: number | null
}

export function OverviewTab({ report, benchmark }: OverviewTabProps) {
  const { score, verdicts } = report

  const radarData = [
    { dimension: "Visibilidade", value: score.visibility, fullMark: 100 },
    { dimension: "Dominância", value: score.dominance, fullMark: 100 },
  ]

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

      {/* Radar chart */}
      <Card>
        <CardHeader>
          <CardTitle>Dimensões de Visibilidade</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mx-auto max-w-md" style={{ height: 288 }}>
            <ResponsiveContainer width="100%" height="100%" minHeight={200}>
              <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="75%">
                <PolarGrid stroke="var(--border)" />
                <PolarAngleAxis
                  dataKey="dimension"
                  tick={{ fontSize: 13, fill: "var(--foreground)" }}
                />
                <Radar
                  name="Score"
                  dataKey="value"
                  stroke="#3b82f6"
                  fill="#3b82f6"
                  fillOpacity={0.2}
                  strokeWidth={2}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          {/* Dimension breakdown */}
          <div className="mt-4 grid grid-cols-2 gap-3">
            {radarData.map((d) => (
              <div key={d.dimension} className="text-center">
                <p className="text-2xl font-bold">{Math.round(d.value)}</p>
                <p className="text-xs text-muted-foreground">{d.dimension}</p>
              </div>
            ))}
          </div>
          {/* Indirect presence — informational metric */}
          <div className="mt-3 flex justify-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-dashed px-3 py-1 text-sm text-muted-foreground">
              <span>Presença Indireta</span>
              <span className="font-semibold">{Math.round(score.indirect_presence)}</span>
              <span className="text-xs">(informativo)</span>
            </div>
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
