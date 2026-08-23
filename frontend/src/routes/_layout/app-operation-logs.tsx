import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { Suspense } from "react"

import {
  AdminAppService,
  type AppAdminOperationLogPublic,
  UsersService,
} from "@/client"
import { AppOperationLogDetailsDialog } from "@/components/AppAdmin/AppOperationLogDetailsDialog"
import {
  CopyId,
  DateTime,
  EmptyState,
  PageHeader,
} from "@/components/AppAdmin/common"
import { DataTable } from "@/components/Common/DataTable"
import { Badge } from "@/components/ui/badge"

function getAppOperationLogsQueryOptions() {
  return {
    queryFn: async () =>
      (
        await AdminAppService.readAppAdminOperationLogs({
          query: { skip: 0, limit: 100 },
        })
      ).data,
    queryKey: ["admin-app-operation-logs"],
  }
}

export const Route = createFileRoute("/_layout/app-operation-logs")({
  component: AppOperationLogs,
  beforeLoad: async () => {
    const { data: user } = await UsersService.readUserMe()
    if (!user.is_superuser) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({
    meta: [{ title: "App Logs - App Server Platform" }],
  }),
})

const columns: ColumnDef<AppAdminOperationLogPublic>[] = [
  {
    accessorKey: "id",
    header: "ID",
    cell: ({ row }) => <CopyId id={row.original.id} />,
  },
  {
    accessorKey: "action",
    header: "Action",
    cell: ({ row }) => (
      <span className="font-mono text-xs font-medium">
        {row.original.action}
      </span>
    ),
  },
  {
    accessorKey: "target_type",
    header: "Target",
    cell: ({ row }) => (
      <div className="flex flex-col gap-1">
        <Badge variant="secondary" className="w-fit">
          {row.original.target_type}
        </Badge>
        <span className="max-w-56 truncate font-mono text-xs text-muted-foreground">
          {row.original.target_id || "N/A"}
        </span>
      </div>
    ),
  },
  {
    accessorKey: "admin_email",
    header: "Admin",
    cell: ({ row }) => (
      <span className="text-sm text-muted-foreground">
        {row.original.admin_email}
      </span>
    ),
  },
  {
    accessorKey: "summary",
    header: "Summary",
    cell: ({ row }) => (
      <span className="block max-w-sm truncate">
        {row.original.summary || "N/A"}
      </span>
    ),
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => <DateTime value={row.original.created_at} />,
  },
  {
    id: "details",
    header: () => <span className="sr-only">Details</span>,
    cell: ({ row }) => (
      <div className="flex justify-end">
        <AppOperationLogDetailsDialog log={row.original} />
      </div>
    ),
  },
]

function AppOperationLogsTableContent() {
  const { data: logs } = useSuspenseQuery(getAppOperationLogsQueryOptions())

  if (logs.data.length === 0) {
    return (
      <EmptyState
        title="No operation logs yet"
        description="Admin write actions will appear here after App management changes."
      />
    )
  }

  return <DataTable columns={columns} data={logs.data} />
}

function AppOperationLogsTable() {
  return (
    <Suspense
      fallback={
        <div className="py-12 text-center text-muted-foreground">
          Loading App operation logs...
        </div>
      }
    >
      <AppOperationLogsTableContent />
    </Suspense>
  )
}

function AppOperationLogs() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="App Logs"
        description="Review admin write actions on App users, content, and configs."
      />
      <AppOperationLogsTable />
    </div>
  )
}
