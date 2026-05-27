"use client"

import { use } from "react"
import { DoctorDetailClient } from "./client"

export default function DoctorDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  return <DoctorDetailClient id={id} />
}
