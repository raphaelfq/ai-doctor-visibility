"use client"

import Link from "next/link"
import { ArrowLeft, Loader2 } from "lucide-react"

import { useRunStatus } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Skeleton } from "@/components/ui/skeleton"
import { StatusBadge } from "@/components/status-badge"

import { OverviewTab } from "./overview-tab"
import { SimulationsTab } from "./simulations-tab"
import { CompetitorsTab } from "./competitors-tab"
import { ActionPlanTab } from "./action-plan-tab"

const STEPS = [
  { key: "prompts", label: "Gerando prompts" },
  { key: "queries", label: "Consultando IAs" },
  { key: "analysis", label: "Analisando respostas" },
  { key: "scoring", label: "Calculando score" },
]

function getStepIndex(progress: string | null | undefined): number {
  if (!progress) return 0
  const lower = progress.toLowerCase()
  if (lower.includes("scor") || lower.includes("finaliz")) return 3
  if (lower.includes("analis") || lower.includes("verdict") || lower.includes("judg")) return 2
  if (lower.includes("consult") || lower.includes("query") || lower.includes("search") || lower.includes("simul")) return 1
  if (lower.includes("prompt") || lower.includes("gera")) return 0
  return 0
}

interface AnalysisClientProps {
  runId: string
}

export function AnalysisClient({ runId }: AnalysisClientProps) {
  const { data: run, isLoading, error } = useRunStatus(runId)

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 rounded-xl" />
      </div>
    )
  }

  if (error || !run) {
    return (
      <div className="py-12 text-center">
        <p className="text-muted-foreground">
          {error ? "Erro ao carregar analise." : "Analise nao encontrada."}
        </p>
        <Button variant="outline" className="mt-4" render={<Link href="/" />}>
          Voltar ao Dashboard
        </Button>
      </div>
    )
  }

  const isPending = run.status === "pending" || run.status === "running"

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          render={<Link href={`/doctors/${run.doctor_id}`} />}
          aria-label="Voltar"
        >
          <ArrowLeft className="size-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Analise — {run.doctor_name}
          </h1>
          <p className="text-sm text-muted-foreground">
            {run.specialty} &middot; {run.city}
            {run.state ? `, ${run.state}` : ""}
          </p>
        </div>
        <div className="ml-auto">
          <StatusBadge status={run.status} />
        </div>
      </div>

      {/* In-progress mode */}
      {isPending && (
        <Card>
          <CardContent className="py-12">
            <div className="mx-auto max-w-md space-y-8 text-center">
              <Loader2 className="mx-auto size-12 animate-spin text-blue-500" />
              <div>
                <h2 className="text-lg font-semibold">Analise em andamento</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {run.progress || "Iniciando pipeline..."}
                </p>
              </div>

              {/* Step indicators */}
              <div className="space-y-3">
                {STEPS.map((step, i) => {
                  const currentStep = getStepIndex(run.progress)
                  const isDone = i < currentStep
                  const isCurrent = i === currentStep
                  return (
                    <div
                      key={step.key}
                      className="flex items-center gap-3 text-left"
                    >
                      <div
                        className={`flex size-7 items-center justify-center rounded-full text-xs font-bold ${
                          isDone
                            ? "bg-green-100 text-green-700"
                            : isCurrent
                              ? "bg-blue-100 text-blue-700"
                              : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {isDone ? "✓" : i + 1}
                      </div>
                      <span
                        className={
                          isCurrent
                            ? "font-medium"
                            : isDone
                              ? "text-muted-foreground"
                              : "text-muted-foreground"
                        }
                      >
                        {step.label}
                      </span>
                      {isCurrent && (
                        <Loader2 className="size-4 animate-spin text-blue-500" />
                      )}
                    </div>
                  )
                })}
              </div>

              <Progress value={((getStepIndex(run.progress) + 1) / STEPS.length) * 100}>
                <ProgressLabel className="sr-only">Progresso</ProgressLabel>
                <ProgressValue />
              </Progress>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Failed mode */}
      {run.status === "failed" && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-lg font-semibold text-destructive">
              Analise falhou
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              {run.error || "Um erro inesperado ocorreu."}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Completed mode — Tabs */}
      {run.status === "completed" && run.report && (
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Visao Geral</TabsTrigger>
            <TabsTrigger value="simulations">Simulacoes</TabsTrigger>
            <TabsTrigger value="competitors">Concorrentes</TabsTrigger>
            <TabsTrigger value="action-plan">Plano de Acao</TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            <OverviewTab report={run.report} benchmark={run.benchmark} />
          </TabsContent>
          <TabsContent value="simulations">
            <SimulationsTab report={run.report} doctorName={run.doctor_name} />
          </TabsContent>
          <TabsContent value="competitors">
            <CompetitorsTab report={run.report} />
          </TabsContent>
          <TabsContent value="action-plan">
            <ActionPlanTab recommendations={run.recommendations} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}
