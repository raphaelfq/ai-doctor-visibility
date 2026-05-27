"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { ArrowLeft } from "lucide-react"
import Link from "next/link"

import { createDoctor } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function NewDoctorPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setError(null)

    const formData = new FormData(e.currentTarget)
    const name = formData.get("name") as string
    const specialty = formData.get("specialty") as string
    const city = formData.get("city") as string
    const state = formData.get("state") as string
    const neighborhood = formData.get("neighborhood") as string
    const crm = formData.get("crm") as string
    const crmState = formData.get("crm_state") as string

    if (!name || !specialty || !city) {
      setError("Nome, especialidade e cidade sao obrigatorios.")
      setLoading(false)
      return
    }

    try {
      const doc = await createDoctor({
        name,
        specialty,
        city,
        state: state || undefined,
        neighborhood: neighborhood || undefined,
        crm: crm || undefined,
        crm_state: crmState || undefined,
      })
      router.push(`/doctors/${doc.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro desconhecido")
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" render={<Link href="/doctors" />} aria-label="Voltar">
          <ArrowLeft className="size-4" />
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">Novo Medico</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Informacoes do medico</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="name">Nome *</Label>
                <Input id="name" name="name" placeholder="Dr. Joao Silva" required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="specialty">Especialidade *</Label>
                <Input id="specialty" name="specialty" placeholder="Cardiologista" required />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="city">Cidade *</Label>
                <Input id="city" name="city" placeholder="Sao Paulo" required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="state">Estado</Label>
                <Input id="state" name="state" placeholder="SP" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="neighborhood">Bairro</Label>
                <Input id="neighborhood" name="neighborhood" placeholder="Jardins" />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="crm">CRM</Label>
                <Input id="crm" name="crm" placeholder="123456" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="crm_state">Estado do CRM</Label>
                <Input id="crm_state" name="crm_state" placeholder="SP" />
              </div>
            </div>

            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" type="button" render={<Link href="/doctors" />}>
                Cancelar
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? "Salvando..." : "Cadastrar"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
