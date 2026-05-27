"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import {
  ArrowLeft,
  Play,
  Trash2,
  BadgeCheck,
} from "lucide-react"
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { useDoctor, createRun, deleteDoctor } from "@/lib/api"
import { formatDate, getScoreColor } from "@/lib/utils"
import { Button, buttonVariants } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { ScoreBadge } from "@/components/score-badge"
import { StatusBadge } from "@/components/status-badge"

interface DoctorDetailClientProps {
  id: string
}

export function DoctorDetailClient({ id }: DoctorDetailClientProps) {
  const router = useRouter()
  const { data: doctor, isLoading, mutate } = useDoctor(id)
  const [runLoading, setRunLoading] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)

  async function handleNewRun() {
    if (!doctor) return
    setRunLoading(true)
    try {
      const result = await createRun(doctor.id)
      router.push(`/analysis/${result.run_id}`)
    } catch {
      setRunLoading(false)
    }
  }

  async function handleDelete() {
    if (!doctor) return
    setDeleteLoading(true)
    try {
      await deleteDoctor(doctor.id)
      router.push("/doctors")
    } catch {
      setDeleteLoading(false)
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    )
  }

  if (!doctor) {
    return (
      <div className="py-12 text-center">
        <p className="text-muted-foreground">Medico nao encontrado.</p>
        <Link href="/doctors" className={buttonVariants({ variant: "outline", className: "mt-4" })}>
          Voltar
        </Link>
      </div>
    )
  }

  const completedRuns = doctor.runs
    .filter((r) => r.status === "completed" && r.score != null)
    .sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    )

  const chartData = completedRuns.map((r) => ({
    date: formatDate(r.created_at),
    score: r.score ?? 0,
  }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Link href="/doctors" className={buttonVariants({ variant: "ghost", size: "icon" })} aria-label="Voltar">
            <ArrowLeft className="size-4" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{doctor.name}</h1>
            <p className="text-sm text-muted-foreground">
              {doctor.specialty} &middot; {doctor.city}
              {doctor.state ? `, ${doctor.state}` : ""}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button onClick={handleNewRun} disabled={runLoading}>
            <Play className="size-4" />
            {runLoading ? "Iniciando..." : "Nova Analise"}
          </Button>
          <Dialog>
            <DialogTrigger
              render={
                <Button variant="destructive" aria-label="Remover medico" />
              }
            >
              <Trash2 className="size-4" />
              Remover
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Remover medico</DialogTitle>
                <DialogDescription>
                  Tem certeza que deseja remover {doctor.name}? Todas as analises
                  serao perdidas. Esta acao nao pode ser desfeita.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose render={<Button variant="outline" />}>
                  Cancelar
                </DialogClose>
                <Button
                  variant="destructive"
                  onClick={handleDelete}
                  disabled={deleteLoading}
                >
                  {deleteLoading ? "Removendo..." : "Confirmar"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Profile card */}
      <Card>
        <CardHeader>
          <CardTitle>Perfil</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-xs text-muted-foreground">Especialidade</p>
              <p className="font-medium">{doctor.specialty}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Cidade</p>
              <p className="font-medium">
                {doctor.city}
                {doctor.state ? `, ${doctor.state}` : ""}
              </p>
            </div>
            {doctor.neighborhood && (
              <div>
                <p className="text-xs text-muted-foreground">Bairro</p>
                <p className="font-medium">{doctor.neighborhood}</p>
              </div>
            )}
            {doctor.crm && (
              <div>
                <p className="text-xs text-muted-foreground">CRM</p>
                <p className="flex items-center gap-1 font-medium">
                  <BadgeCheck className="size-4 text-green-600" />
                  {doctor.crm}
                  {doctor.crm_state ? `/${doctor.crm_state}` : ""}
                </p>
              </div>
            )}
            <div>
              <p className="text-xs text-muted-foreground">Analises</p>
              <p className="font-medium">{doctor.runs?.length ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Ultimo score</p>
              <ScoreBadge score={doctor.runs?.find((r) => r.status === "completed")?.score} showLabel />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Score trend chart */}
      {chartData.length >= 2 && (
        <Card>
          <CardHeader>
            <CardTitle>Evolucao do Score</CardTitle>
            <CardDescription>
              Historico de scores nas ultimas analises
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 12 }}
                    className="fill-muted-foreground"
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 12 }}
                    className="fill-muted-foreground"
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: "8px",
                      border: "1px solid var(--border)",
                      fontSize: "14px",
                    }}
                  />
                  <ReferenceLine
                    y={50}
                    stroke="#94a3b8"
                    strokeDasharray="5 5"
                    label={{ value: "Benchmark", position: "right", fontSize: 11 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="score"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    fill="url(#scoreGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Run history */}
      <Card>
        <CardHeader>
          <CardTitle>Historico de Analises</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {doctor.runs.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12 text-center">#</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead className="text-right">Acao</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {doctor.runs.map((run, idx) => (
                  <TableRow
                    key={run.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => router.push(`/analysis/${run.id}`)}
                  >
                    <TableCell className="text-center text-muted-foreground">
                      {doctor.runs.length - idx}
                    </TableCell>
                    <TableCell>{formatDate(run.created_at)}</TableCell>
                    <TableCell>
                      <StatusBadge status={run.status} />
                    </TableCell>
                    <TableCell>
                      <ScoreBadge score={run.score} />
                    </TableCell>
                    <TableCell className="text-right">
                      <Link
                        href={`/analysis/${run.id}`}
                        className={buttonVariants({ variant: "ghost", size: "sm" })}
                        onClick={(e) => e.stopPropagation()}
                      >
                        Ver detalhes
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="p-6 text-center text-muted-foreground">
              Nenhuma analise realizada para este medico.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
