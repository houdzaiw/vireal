import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { Suspense } from "react"

import { AdminAppService, type AppConfigPublic, UsersService } from "@/client"
import { AppConfigActionsMenu } from "@/components/AppAdmin/AppConfigActionsMenu"
import { AppConfigDialog } from "@/components/AppAdmin/AppConfigDialog"
import {
  BooleanBadge,
  CopyId,
  DateTime,
  EmptyState,
  PageHeader,
} from "@/components/AppAdmin/common"
import { DataTable } from "@/components/Common/DataTable"

function getAppConfigsQueryOptions() {
  return {
    queryFn: async () =>
      (
        await AdminAppService.readAppConfigs({
          query: { skip: 0, limit: 100 },
        })
      ).data,
    queryKey: ["admin-app-configs"],
  }
}

export const Route = createFileRoute("/_layout/app-configs")({
  component: AppConfigs,
  beforeLoad: async () => {
    const { data: user } = await UsersService.readUserMe()
    if (!user.is_superuser) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({
    meta: [{ title: "App Configs - App Server Platform" }],
  }),
})

const columns: ColumnDef<AppConfigPublic>[] = [
  {
    accessorKey: "id",
    header: "ID",
    cell: ({ row }) => <CopyId id={row.original.id} />,
  },
  {
    accessorKey: "key",
    header: "Key",
    cell: ({ row }) => (
      <span className="font-mono text-sm font-medium">{row.original.key}</span>
    ),
  },
  {
    accessorKey: "value",
    header: "Value",
    cell: ({ row }) => (
      <span className="block max-w-sm truncate text-muted-foreground">
        {row.original.value}
      </span>
    ),
  },
  {
    accessorKey: "description",
    header: "Description",
    cell: ({ row }) => (
      <span className="block max-w-xs truncate text-muted-foreground">
        {row.original.description || "N/A"}
      </span>
    ),
  },
  {
    accessorKey: "is_enabled",
    header: "Status",
    cell: ({ row }) => <BooleanBadge value={row.original.is_enabled} />,
  },
  {
    accessorKey: "updated_at",
    header: "Updated",
    cell: ({ row }) => <DateTime value={row.original.updated_at} />,
  },
  {
    id: "actions",
    header: () => <span className="sr-only">Actions</span>,
    cell: ({ row }) => (
      <div className="flex justify-end">
        <AppConfigActionsMenu config={row.original} />
      </div>
    ),
  },
]

function AppConfigsTableContent() {
  const { data: configs } = useSuspenseQuery(getAppConfigsQueryOptions())

  if (configs.data.length === 0) {
    return (
      <EmptyState
        title="No configs yet"
        description="Add the first key-value setting for App startup."
      />
    )
  }

  return <DataTable columns={columns} data={configs.data} />
}

function AppConfigsTable() {
  return (
    <Suspense
      fallback={
        <div className="py-12 text-center text-muted-foreground">
          Loading App configs...
        </div>
      }
    >
      <AppConfigsTableContent />
    </Suspense>
  )
}

function AppConfigs() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="App Configs"
        description="Manage key-value settings fetched by the App at startup."
        action={<AppConfigDialog />}
      />
      <AppConfigsTable />
    </div>
  )
}
