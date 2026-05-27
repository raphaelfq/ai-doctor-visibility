"use client"

import { use } from "react"
import { AnalysisClient } from "./client"

export default function AnalysisPage({
  params,
}: {
  params: Promise<{ runId: string }>
}) {
  const { runId } = use(params)
  return <AnalysisClient runId={runId} />
}
