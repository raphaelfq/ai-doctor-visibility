import useSWR, { type SWRConfiguration } from "swr"
import type {
  CreateDoctorPayload,
  CreateRunResponse,
  Doctor,
  DoctorDetail,
  RunDetail,
  RunListItem,
} from "./types"

// ---------------------------------------------------------------------------
// Base URL & fetcher
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

async function fetcher<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`API ${res.status}: ${body}`)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// SWR hooks
// ---------------------------------------------------------------------------

export function useDoctors(config?: SWRConfiguration<Doctor[]>) {
  return useSWR<Doctor[]>("/api/doctors", fetcher<Doctor[]>, config)
}

export function useDoctor(id: string | undefined, config?: SWRConfiguration<DoctorDetail>) {
  return useSWR<DoctorDetail>(
    id ? `/api/doctors/${id}` : null,
    fetcher<DoctorDetail>,
    config,
  )
}

export function useRuns(config?: SWRConfiguration<RunListItem[]>) {
  return useSWR<RunListItem[]>("/api/runs", fetcher<RunListItem[]>, config)
}

export function useRunDetail(id: string | undefined, config?: SWRConfiguration<RunDetail>) {
  return useSWR<RunDetail>(
    id ? `/api/runs/${id}` : null,
    fetcher<RunDetail>,
    config,
  )
}

export function useRunStatus(id: string | undefined) {
  const { data, error, isLoading, mutate } = useSWR<RunDetail>(
    id ? `/api/runs/${id}` : null,
    fetcher<RunDetail>,
    {
      refreshInterval: (latestData) => {
        if (!latestData) return 3000
        if (latestData.status === "pending" || latestData.status === "running") {
          return 3000
        }
        return 0
      },
    },
  )
  return { data, error, isLoading, mutate }
}

// ---------------------------------------------------------------------------
// Mutation functions
// ---------------------------------------------------------------------------

export async function createDoctor(payload: CreateDoctorPayload): Promise<Doctor> {
  const res = await fetch(`${API_BASE}/api/doctors`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`Erro ao criar medico: ${body}`)
  }
  return res.json() as Promise<Doctor>
}

export async function deleteDoctor(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/doctors/${id}`, {
    method: "DELETE",
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`Erro ao remover medico: ${body}`)
  }
}

export async function createRun(doctorId: string): Promise<CreateRunResponse> {
  const res = await fetch(`${API_BASE}/api/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`Erro ao criar analise: ${body}`)
  }
  return res.json() as Promise<CreateRunResponse>
}
