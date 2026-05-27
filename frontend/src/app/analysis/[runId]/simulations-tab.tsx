"use client"

import { useState } from "react"
import {
  CheckCircle,
  Info,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronUp,
} from "lucide-react"

import type { Report, CitationType } from "@/lib/types"
import { getCitationStyle } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

const citationIcons: Record<CitationType, React.ElementType> = {
  mentioned_by_name: CheckCircle,
  mentioned_as_specialty: Info,
  competitor_in_place: AlertTriangle,
  not_mentioned: XCircle,
}

interface SimulationsTabProps {
  report: Report
  doctorName: string
}

export function SimulationsTab({ report, doctorName }: SimulationsTabProps) {
  const { prompts, responses, verdicts } = report

  return (
    <div className="mt-4 space-y-4">
      {prompts.map((prompt, idx) => {
        const response = responses.find((r) => r.prompt_id === prompt.id)
        const verdict = verdicts.find((v) => v.prompt_id === prompt.id)

        return (
          <SimulationCard
            key={prompt.id}
            index={idx}
            promptText={prompt.text}
            persona={prompt.persona}
            responseText={response?.raw_text}
            doctorName={doctorName}
            verdict={verdict}
            competitors={verdict?.competitors_named ?? []}
          />
        )
      })}
    </div>
  )
}

interface SimulationCardProps {
  index: number
  promptText: string
  persona: string
  responseText?: string
  doctorName: string
  verdict?: {
    citation_type: CitationType
    confidence: number
    position?: number | null
    evidence_quote: string
    competitors_named: string[]
  }
  competitors: string[]
}

function SimulationCard({
  index,
  promptText,
  persona,
  responseText,
  doctorName,
  verdict,
  competitors,
}: SimulationCardProps) {
  const [expanded, setExpanded] = useState(false)
  const style = verdict ? getCitationStyle(verdict.citation_type) : null
  const Icon = verdict ? citationIcons[verdict.citation_type] : null

  function highlightNames(text: string): React.ReactNode {
    if (!text) return text
    const parts: React.ReactNode[] = []
    let remaining = text

    const nameParts = doctorName.split(" ").filter(
      (p) => !/^(dr\.?|dra\.?|prof\.?)$/i.test(p),
    )
    const doctorMatchName = nameParts.length >= 2
      ? `${nameParts[0]} ${nameParts[nameParts.length - 1]}`
      : nameParts[0] ?? doctorName
    const allNames = [doctorMatchName, ...competitors]
    const regex = new RegExp(
      `(${allNames.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
      "gi",
    )
    const segments = remaining.split(regex)

    segments.forEach((seg, i) => {
      if (!seg) return
      const isDoctor = seg.toLowerCase() === doctorMatchName.toLowerCase()
      const isCompetitor = competitors.some(
        (c) => c.toLowerCase() === seg.toLowerCase(),
      )
      if (isDoctor) {
        parts.push(
          <mark key={i} className="rounded bg-green-200 px-0.5 font-semibold text-green-900">
            {seg}
          </mark>,
        )
      } else if (isCompetitor) {
        parts.push(
          <mark key={i} className="rounded bg-red-200 px-0.5 font-semibold text-red-900">
            {seg}
          </mark>,
        )
      } else {
        parts.push(seg)
      }
    })
    return parts
  }

  return (
    <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
      {/* macOS-style header */}
      <div className="flex items-center gap-2 bg-slate-800 px-3 py-2">
        <div className="flex gap-1.5">
          <span className="size-2.5 rounded-full bg-red-500" />
          <span className="size-2.5 rounded-full bg-yellow-500" />
          <span className="size-2.5 rounded-full bg-green-500" />
        </div>
        <span className="ml-2 text-xs text-slate-300">
          ChatGPT — Prompt p{index + 1}
        </span>
        <Button
          variant="ghost"
          size="icon-xs"
          className="ml-auto text-slate-400 hover:text-white"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
          aria-label={expanded ? "Recolher" : "Expandir"}
        >
          {expanded ? (
            <ChevronUp className="size-3" />
          ) : (
            <ChevronDown className="size-3" />
          )}
        </Button>
      </div>

      {/* Chat bubbles */}
      <div className="space-y-3 p-4">
        {/* Patient (user) bubble */}
        <div className="flex gap-3">
          <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-blue-50 px-4 py-3">
            <p className="mb-1 text-[10px] font-medium text-blue-600">
              {persona}
            </p>
            <p className="text-sm">{promptText}</p>
          </div>
        </div>

        {/* AI response bubble */}
        {responseText && (
          <div className="flex justify-end gap-3">
            <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-gray-100 px-4 py-3">
              <p className={`text-sm leading-relaxed ${expanded ? "" : "line-clamp-4"}`}>
                {highlightNames(responseText)}
              </p>
              {!expanded && responseText.length > 300 && (
                <button
                  onClick={() => setExpanded(true)}
                  className="mt-1 text-xs text-blue-600 hover:underline"
                  type="button"
                >
                  Mostrar mais
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Verdict bar */}
      {verdict && style && Icon && (
        <div className={`flex flex-wrap items-center gap-2 border-t px-4 py-2 ${style.bg}`}>
          <Icon className={`size-4 ${style.text}`} />
          <span className={`text-sm font-medium ${style.text}`}>
            {style.label}
          </span>
          <Badge variant="secondary" className="text-[10px]">
            Confiança: {Math.round(verdict.confidence * 100)}%
          </Badge>
          {verdict.position != null && (
            <Badge variant="outline" className="text-[10px]">
              Posição #{verdict.position}
            </Badge>
          )}
          {competitors.length > 0 && (
            <span className="text-xs text-muted-foreground">
              Concorrentes: {competitors.join(", ")}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
