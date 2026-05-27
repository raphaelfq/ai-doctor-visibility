"use client"

import Link from "next/link"
import { useState } from "react"
import { Plus, Search } from "lucide-react"

import { useDoctors } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ScoreBadge } from "@/components/score-badge"

export default function DoctorsPage() {
  const { data: doctors, isLoading } = useDoctors()
  const [search, setSearch] = useState("")

  const filtered = doctors?.filter((d) => {
    const q = search.toLowerCase()
    return (
      d.name.toLowerCase().includes(q) ||
      d.specialty.toLowerCase().includes(q) ||
      d.city.toLowerCase().includes(q)
    )
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Medicos</h1>
        <Button render={<Link href="/doctors/new" />}>
          <Plus className="size-4" />
          Novo Medico
        </Button>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Buscar por nome, especialidade ou cidade..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
          aria-label="Buscar medicos"
        />
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-xl" />
          ))}
        </div>
      ) : filtered && filtered.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((doc) => (
            <Link key={doc.id} href={`/doctors/${doc.id}`}>
              <Card className="transition-shadow hover:shadow-md">
                <CardHeader>
                  <CardTitle>{doc.name}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">
                        {doc.specialty}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {doc.city}
                        {doc.state ? `, ${doc.state}` : ""}
                      </p>
                    </div>
                    <div className="text-right">
                      <ScoreBadge score={doc.latest_score} />
                      <p className="mt-1 text-xs text-muted-foreground">
                        {doc.run_count} {doc.run_count === 1 ? "analise" : "analises"}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <p className="py-12 text-center text-muted-foreground">
          {search
            ? "Nenhum medico encontrado para esta busca."
            : "Nenhum medico cadastrado ainda."}
        </p>
      )}
    </div>
  )
}
