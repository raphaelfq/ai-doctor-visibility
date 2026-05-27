"use client"

import Link from "next/link"
import { Activity, Stethoscope, TrendingUp } from "lucide-react"

import { useDoctors, useRuns } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Skeleton } from "@/components/ui/skeleton"
import { ScoreBadge } from "@/components/score-badge"
import { StatusBadge } from "@/components/status-badge"
import { formatDate } from "@/lib/utils"

export default function DashboardPage() {
  const { data: doctors, isLoading: loadingDoctors } = useDoctors()
  const { data: runs, isLoading: loadingRuns } = useRuns()

  const totalDoctors = doctors?.length ?? 0
  const totalRuns = runs?.length ?? 0
  const scoredDoctors = doctors?.filter((d) => d.latest_score != null) ?? []
  const avgScore =
    scoredDoctors.length > 0
      ? scoredDoctors.reduce((sum, d) => sum + (d.latest_score ?? 0), 0) /
        scoredDoctors.length
      : null

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>

      {/* Stat cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Médicos cadastrados
            </CardTitle>
            <Stethoscope className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {loadingDoctors ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <p className="text-3xl font-bold">{totalDoctors}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Análises realizadas
            </CardTitle>
            <Activity className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {loadingRuns ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <p className="text-3xl font-bold">{totalRuns}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Score médio
            </CardTitle>
            <TrendingUp className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {loadingDoctors ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <p className="text-3xl font-bold">
                {avgScore != null && !isNaN(avgScore)
                  ? Math.round(avgScore)
                  : "—"}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Doctor grid */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Médicos</h2>
          <Link
            href="/doctors"
            className="text-sm text-blue-600 hover:underline"
          >
            Ver todos
          </Link>
        </div>

        {loadingDoctors ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {doctors?.slice(0, 6).map((doc) => (
              <Link key={doc.id} href={`/doctors/${doc.id}`}>
                <Card className="transition-shadow hover:shadow-md">
                  <CardHeader>
                    <CardTitle>{doc.name}</CardTitle>
                  </CardHeader>
                  <CardContent className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">
                      {doc.specialty} &middot; {doc.city}
                    </span>
                    <ScoreBadge score={doc.latest_score} />
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* Recent runs */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Análises recentes</h2>

        <Card>
          <CardContent className="p-0">
            {loadingRuns ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : runs && runs.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Médico</TableHead>
                    <TableHead>Especialidade</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Score</TableHead>
                    <TableHead className="hidden md:table-cell">Data</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.map((run) => (
                    <TableRow key={run.id} className="cursor-pointer">
                      <TableCell>
                        <Link
                          href={`/analysis/${run.id}`}
                          className="font-medium hover:underline"
                        >
                          {run.doctor_name || "—"}
                        </Link>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {run.specialty || "—"}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={run.status} />
                      </TableCell>
                      <TableCell>
                        <ScoreBadge score={run.score} />
                      </TableCell>
                      <TableCell className="hidden text-muted-foreground md:table-cell">
                        {formatDate(run.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="p-6 text-center text-muted-foreground">
                Nenhuma análise realizada ainda.
              </p>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  )
}
