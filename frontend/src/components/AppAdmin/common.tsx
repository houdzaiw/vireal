import { Check, Copy, Search } from "lucide-react"
import type { ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import { cn } from "@/lib/utils"

export function CopyId({ id }: { id: string }) {
  const [copiedText, copy] = useCopyToClipboard()
  const isCopied = copiedText === id

  return (
    <div className="flex items-center gap-1.5 group">
      <span className="font-mono text-xs text-muted-foreground">{id}</span>
      <Button
        variant="ghost"
        size="icon"
        className="size-6 opacity-0 transition-opacity group-hover:opacity-100"
        onClick={() => copy(id)}
      >
        {isCopied ? (
          <Check className="size-3 text-green-500" />
        ) : (
          <Copy className="size-3" />
        )}
        <span className="sr-only">Copy ID</span>
      </Button>
    </div>
  )
}

export function StatusBadge({ status }: { status?: string | null }) {
  const normalizedStatus = status ?? "unknown"
  const variant =
    normalizedStatus === "active" ||
    normalizedStatus === "paid" ||
    normalizedStatus === "created"
      ? "default"
      : normalizedStatus === "disabled" || normalizedStatus === "refunded"
        ? "secondary"
        : "outline"

  return (
    <Badge
      variant={variant}
      className={cn(
        "capitalize",
        (normalizedStatus === "deleted" ||
          normalizedStatus === "failed" ||
          normalizedStatus === "canceled") &&
          "border-destructive/40 text-destructive",
      )}
    >
      {normalizedStatus}
    </Badge>
  )
}

export function ProviderBadge({ provider }: { provider?: string | null }) {
  return (
    <Badge variant="secondary" className="capitalize">
      {provider ?? "unknown"}
    </Badge>
  )
}

export function BooleanBadge({ value }: { value?: boolean | null }) {
  return (
    <Badge variant={value ? "default" : "secondary"}>
      {value ? "Enabled" : "Disabled"}
    </Badge>
  )
}

export function DateTime({ value }: { value?: string | null }) {
  if (!value) {
    return <span className="text-muted-foreground">N/A</span>
  }

  return (
    <span className="whitespace-nowrap text-muted-foreground">
      {new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))}
    </span>
  )
}

export function EmptyState({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="mb-4 rounded-full bg-muted p-4">
        <Search className="h-8 w-8 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="text-muted-foreground">{description}</p>
    </div>
  )
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        <p className="text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  )
}

export function getMediaUrl(url?: string | null) {
  if (!url) {
    return ""
  }
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url
  }
  const baseUrl = import.meta.env.VITE_API_URL ?? ""
  return `${baseUrl}${url}`
}
