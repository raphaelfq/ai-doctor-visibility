"use client"

import { Lightbulb } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

interface ActionPlanTabProps {
  recommendations?: string[] | null
}

export function ActionPlanTab({ recommendations }: ActionPlanTabProps) {
  if (!recommendations || recommendations.length === 0) {
    return (
      <div className="mt-4 py-12 text-center text-muted-foreground">
        Nenhuma recomendacao disponivel para esta analise.
      </div>
    )
  }

  return (
    <div className="mt-4 space-y-4">
      <h2 className="text-lg font-semibold">
        Recomendacoes ({recommendations.length})
      </h2>

      {recommendations.map((rec, i) => (
        <Alert key={i}>
          <Lightbulb className="size-4" />
          <AlertTitle>Recomendacao {i + 1}</AlertTitle>
          <AlertDescription>{rec}</AlertDescription>
        </Alert>
      ))}
    </div>
  )
}
