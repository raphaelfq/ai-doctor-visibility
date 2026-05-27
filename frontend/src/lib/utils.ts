import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import type { CitationType } from "./types"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// ---------------------------------------------------------------------------
// Score helpers
// ---------------------------------------------------------------------------

export function getScoreColor(score: number | null | undefined): string {
  if (score == null) return "#94a3b8" // slate-400
  if (score <= 30) return "#ef4444" // red-500
  if (score <= 60) return "#f59e0b" // amber-500
  return "#22c55e" // green-500
}

export function getScoreLabel(score: number | null | undefined): string {
  if (score == null) return "Sem dados"
  if (score <= 30) return "Baixo"
  if (score <= 60) return "Medio"
  return "Alto"
}

// ---------------------------------------------------------------------------
// Citation style map
// ---------------------------------------------------------------------------

export function getCitationStyle(type: CitationType) {
  const styles: Record<CitationType, { icon: string; bg: string; border: string; text: string; label: string }> = {
    mentioned_by_name: {
      icon: "check-circle",
      bg: "bg-green-50",
      border: "border-green-200",
      text: "text-green-700",
      label: "Citado por nome",
    },
    mentioned_as_specialty: {
      icon: "info",
      bg: "bg-yellow-50",
      border: "border-yellow-200",
      text: "text-yellow-700",
      label: "Citado como especialidade",
    },
    competitor_in_place: {
      icon: "alert-triangle",
      bg: "bg-red-50",
      border: "border-red-200",
      text: "text-red-700",
      label: "Concorrente citado",
    },
    not_mentioned: {
      icon: "x-circle",
      bg: "bg-gray-50",
      border: "border-gray-200",
      text: "text-gray-500",
      label: "Nao mencionado",
    },
  }
  return styles[type]
}

// ---------------------------------------------------------------------------
// Date formatting
// ---------------------------------------------------------------------------

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
