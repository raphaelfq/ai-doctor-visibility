"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Eye, LayoutDashboard, Menu, Users, Plus } from "lucide-react"
import { useState } from "react"

import { cn } from "@/lib/utils"
import { buttonVariants } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/doctors", label: "Médicos", icon: Users },
]

function NavContent() {
  const pathname = usePathname()

  return (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-5">
        <Eye className="size-6 text-blue-400" />
        <span className="text-lg font-semibold text-white">AI Visibility</span>
      </div>

      {/* Navigation */}
      <nav className="space-y-1 px-2" aria-label="Menu principal">
        {navItems.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href)

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-slate-800 text-white"
                  : "text-slate-400 hover:bg-slate-800 hover:text-white",
              )}
              aria-current={isActive ? "page" : undefined}
            >
              <item.icon className="size-4" />
              {item.label}
            </Link>
          )
        })}
      </nav>

      {/* Action button — right below nav */}
      <div className="px-3 pt-4">
        <Link
          href="/doctors/new"
          className={cn(
            buttonVariants({ variant: "default", size: "lg" }),
            "w-full gap-2 bg-blue-600 text-white hover:bg-blue-700",
          )}
        >
          <Plus className="size-4" />
          Novo Médico
        </Link>
      </div>

      {/* Spacer */}
      <div className="flex-1" />
    </div>
  )
}

export function Sidebar() {
  return (
    <aside className="hidden w-64 shrink-0 bg-slate-900 lg:block" aria-label="Barra lateral">
      <div className="sticky top-0 h-screen">
        <NavContent />
      </div>
    </aside>
  )
}

export function MobileHeader() {
  const [open, setOpen] = useState(false)

  return (
    <header className="flex h-14 items-center gap-3 border-b bg-white px-4 lg:hidden">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger
          className={cn(
            buttonVariants({ variant: "ghost", size: "icon" }),
          )}
          aria-label="Abrir menu"
        >
          <Menu className="size-5" />
        </SheetTrigger>
        <SheetContent side="left" className="w-64 bg-slate-900 p-0">
          <SheetTitle className="sr-only">Menu de navegação</SheetTitle>
          <NavContent />
        </SheetContent>
      </Sheet>
      <div className="flex items-center gap-2">
        <Eye className="size-5 text-blue-600" />
        <span className="font-semibold">AI Visibility</span>
      </div>
    </header>
  )
}
