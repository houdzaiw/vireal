import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { ExternalLink, Film, ImageIcon } from "lucide-react"
import { Suspense } from "react"

import {
  AdminAppService,
  type AppGenerationAdminPublic,
  UsersService,
} from "@/client"
import { AppGenerationActionsMenu } from "@/components/AppAdmin/AppGenerationActionsMenu"
import {
  CopyId,
  DateTime,
  EmptyState,
  getMediaUrl,
  PageHeader,
  ProviderBadge,
  StatusBadge,
} from "@/components/AppAdmin/common"
import { DataTable } from "@/components/Common/DataTable"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

function getAppGenerationsQueryOptions() {
  return {
    queryFn: async () =>
      (
        await AdminAppService.readAppGenerations({
          query: { skip: 0, limit: 100 },
        })
      ).data,
    queryKey: ["admin-app-generations"],
  }
}

export const Route = createFileRoute("/_layout/app-generations")({
  component: AppGenerations,
  beforeLoad: async () => {
    const { data: user } = await UsersService.readUserMe()
    if (!user.is_superuser) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({
    meta: [{ title: "App Generations - App Server Platform" }],
  }),
})

function KindBadge({ kind }: { kind: string }) {
  const Icon = kind === "image" ? ImageIcon : Film
  return (
    <Badge variant="secondary" className="gap-1 capitalize">
      <Icon className="size-3" />
      {kind}
    </Badge>
  )
}

function GenerationMedia({
  generation,
}: {
  generation: AppGenerationAdminPublic
}) {
  const mediaUrl =
    generation.output_url ||
    generation.reference_image_url ||
    generation.character_image_url
  if (!mediaUrl) {
    return <span className="text-muted-foreground">N/A</span>
  }

  const visibleUrl = getMediaUrl(mediaUrl)
  return (
    <Button variant="outline" size="sm" asChild>
      <a href={visibleUrl} target="_blank" rel="noreferrer">
        <ExternalLink className="size-4" />
        Open
      </a>
    </Button>
  )
}

const columns: ColumnDef<AppGenerationAdminPublic>[] = [
  {
    accessorKey: "id",
    header: "ID",
    cell: ({ row }) => <CopyId id={row.original.id} />,
  },
  {
    accessorKey: "kind",
    header: "Type",
    cell: ({ row }) => <KindBadge kind={row.original.kind} />,
  },
  {
    accessorKey: "prompt",
    header: "Prompt",
    cell: ({ row }) => (
      <div className="max-w-xs">
        <span className="block truncate font-medium">
          {row.original.prompt}
        </span>
        <span className="text-xs text-muted-foreground">
          {row.original.style} · {row.original.aspect_ratio}
        </span>
      </div>
    ),
  },
  {
    accessorKey: "app_user_id",
    header: "App User",
    cell: ({ row }) => <CopyId id={row.original.app_user_id} />,
  },
  {
    accessorKey: "provider",
    header: "Provider",
    cell: ({ row }) => (
      <div className="flex flex-col gap-1">
        <ProviderBadge provider={row.original.provider} />
        <span className="max-w-40 truncate text-xs text-muted-foreground">
          {row.original.model}
        </span>
      </div>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  },
  {
    accessorKey: "output_url",
    header: "Output",
    cell: ({ row }) => <GenerationMedia generation={row.original} />,
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => <DateTime value={row.original.created_at} />,
  },
  {
    id: "actions",
    header: () => <span className="sr-only">Actions</span>,
    cell: ({ row }) => (
      <div className="flex justify-end">
        <AppGenerationActionsMenu generation={row.original} />
      </div>
    ),
  },
]

function AppGenerationsTableContent() {
  const { data: generations } = useSuspenseQuery(
    getAppGenerationsQueryOptions(),
  )

  if (generations.data.length === 0) {
    return (
      <EmptyState
        title="No App generations yet"
        description="AI video and image works will appear here after App users generate them."
      />
    )
  }

  return <DataTable columns={columns} data={generations.data} />
}

function AppGenerationsTable() {
  return (
    <Suspense
      fallback={
        <div className="py-12 text-center text-muted-foreground">
          Loading App generations...
        </div>
      }
    >
      <AppGenerationsTableContent />
    </Suspense>
  )
}

function AppGenerations() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="App Generations"
        description="Review AI video and image works, provider status, and remove works from user history."
      />
      <AppGenerationsTable />
    </div>
  )
}
