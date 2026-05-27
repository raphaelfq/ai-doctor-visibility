"use client"

import { useMemo } from "react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Users, Trophy } from "lucide-react"

import type { Report } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"

interface CompetitorsTabProps {
  report: Report
}

interface CompetitorEntry {
  name: string
  count: number
}

export function CompetitorsTab({ report }: CompetitorsTabProps) {
  const { verdicts } = report
  const totalPrompts = verdicts.length

  const competitors = useMemo(() => {
    const map = new Map<string, number>()
    for (const v of verdicts) {
      for (const name of v.competitors_named) {
        map.set(name, (map.get(name) ?? 0) + 1)
      }
    }
    const entries: CompetitorEntry[] = []
    map.forEach((count, name) => entries.push({ name, count }))
    entries.sort((a, b) => b.count - a.count)
    return entries
  }, [verdicts])

  const uniqueCount = competitors.length
  const topCompetitor = competitors[0]

  const chartData = competitors.slice(0, 10)

  return (
    <div className="mt-4 space-y-6">
      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Concorrentes únicos
            </CardTitle>
            <Users className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{uniqueCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Mais citado
            </CardTitle>
            <Trophy className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-xl font-bold">
              {topCompetitor ? topCompetitor.name : "—"}
            </p>
            {topCompetitor && (
              <p className="text-sm text-muted-foreground">
                {topCompetitor.count}/{totalPrompts} prompts
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Bar chart */}
      {chartData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Top 10 Concorrentes</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  layout="vertical"
                  margin={{ left: 20, right: 20 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-muted" />
                  <XAxis
                    type="number"
                    domain={[0, totalPrompts]}
                    tick={{ fontSize: 12 }}
                    className="fill-muted-foreground"
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={140}
                    tick={{ fontSize: 12 }}
                    className="fill-muted-foreground"
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: "8px",
                      border: "1px solid var(--border)",
                      fontSize: "14px",
                    }}
                    formatter={(value) => [`${value}/${totalPrompts}`, "Aparições"]}
                  />
                  <Bar
                    dataKey="count"
                    fill="#ef4444"
                    radius={[0, 4, 4, 0]}
                    barSize={20}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Table */}
      {competitors.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Todos os Concorrentes</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Aparições</TableHead>
                  <TableHead className="text-right">Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {competitors.map((c) => (
                  <TableRow key={c.name}>
                    <TableCell className="font-medium">{c.name}</TableCell>
                    <TableCell>
                      {c.count}/{totalPrompts}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm">
                        Cadastrar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {competitors.length === 0 && (
        <p className="py-12 text-center text-muted-foreground">
          Nenhum concorrente identificado nesta análise.
        </p>
      )}
    </div>
  )
}
