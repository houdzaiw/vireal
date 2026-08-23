import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { ImageIcon } from "lucide-react"
import { Suspense } from "react"

import {
  AdminAppService,
  type AppContentAdminPublic,
  UsersService,
} from "@/client"
import { AppContentActionsMenu } from "@/components/AppAdmin/AppContentActionsMenu"
import {
  CopyId,
  DateTime,
  EmptyState,
  getMediaUrl,
  PageHeader,
  StatusBadge,
} from "@/components/AppAdmin/common"
import { DataTable } from "@/components/Common/DataTable"

function getAppContentsQueryOptions() {
  return {
    queryFn: async () =>
      (
        await AdminAppService.readAppContents({
          query: { skip: 0, limit: 100 },
        })
      ).data,
    queryKey: ["admin-app-contents"],
  }
}

export const Route = createFileRoute("/_layout/app-contents")({
  component: AppContents,
  beforeLoad: async () => {
    const { data: user } = await UsersService.readUserMe()
    if (!user.is_superuser) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({
    meta: [{ title: "App Contents - App Server Platform" }],
  }),
})

const columns: ColumnDef<AppContentAdminPublic>[] = [
  {
    accessorKey: "id",
    header: "ID",
    cell: ({ row }) => <CopyId id={row.original.id} />,
  },
  {
    accessorKey: "text",
    header: "Content",
    cell: ({ row }) => (
      <span className="block max-w-sm truncate font-medium">
        {row.original.text || "Images only"}
      </span>
    ),
  },
  {
    accessorKey: "author",
    header: "Author",
    cell: ({ row }) => (
      <div className="flex flex-col">
        <span>{row.original.author.nickname || "Unnamed user"}</span>
        <span className="font-mono text-xs text-muted-foreground">
          {row.original.app_user_id}
        </span>
      </div>
    ),
  },
  {
    accessorKey: "images",
    header: "Images",
    cell: ({ row }) => {
      const firstImage = row.original.images[0]
      return (
        <div className="flex items-center gap-2">
          {firstImage ? (
            <img
              src={getMediaUrl(firstImage.url)}
              alt=""
              className="size-10 rounded-md border object-cover"
            />
          ) : (
            <div className="grid size-10 place-items-center rounded-md border bg-muted">
              <ImageIcon className="size-4 text-muted-foreground" />
            </div>
          )}
          <span className="text-muted-foreground">
            {row.original.images.length}
          </span>
        </div>
      )
    },
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
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
        <AppContentActionsMenu content={row.original} />
      </div>
    ),
  },
]

function AppContentsTableContent() {
  const { data: contents } = useSuspenseQuery(getAppContentsQueryOptions())

  if (contents.data.length === 0) {
    return (
      <EmptyState
        title="No App contents yet"
        description="Published posts will appear here after App users create content."
      />
    )
  }

  return <DataTable columns={columns} data={contents.data} />
}

function AppContentsTable() {
  return (
    <Suspense
      fallback={
        <div className="py-12 text-center text-muted-foreground">
          Loading App contents...
        </div>
      }
    >
      <AppContentsTableContent />
    </Suspense>
  )
}

function AppContents() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="App Contents"
        description="Review posts and remove content from the App feed."
      />
      <AppContentsTable />
    </div>
  )
}
