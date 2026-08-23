import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { Suspense } from "react"

import {
  AdminAppService,
  type AppUserAdminPublic,
  UsersService,
} from "@/client"
import { AppUserActionsMenu } from "@/components/AppAdmin/AppUserActionsMenu"
import {
  CopyId,
  DateTime,
  EmptyState,
  PageHeader,
  StatusBadge,
} from "@/components/AppAdmin/common"
import { DataTable } from "@/components/Common/DataTable"

function getAppUsersQueryOptions() {
  return {
    queryFn: async () =>
      (
        await AdminAppService.readAppUsers({
          query: { skip: 0, limit: 100 },
        })
      ).data,
    queryKey: ["admin-app-users"],
  }
}

export const Route = createFileRoute("/_layout/app-users")({
  component: AppUsers,
  beforeLoad: async () => {
    const { data: user } = await UsersService.readUserMe()
    if (!user.is_superuser) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({
    meta: [{ title: "App Users - App Server Platform" }],
  }),
})

const columns: ColumnDef<AppUserAdminPublic>[] = [
  {
    accessorKey: "id",
    header: "ID",
    cell: ({ row }) => <CopyId id={row.original.id} />,
  },
  {
    accessorKey: "nickname",
    header: "Nickname",
    cell: ({ row }) => (
      <span className="font-medium">
        {row.original.nickname || "Unnamed user"}
      </span>
    ),
  },
  {
    accessorKey: "avatar_url",
    header: "Avatar",
    cell: ({ row }) => (
      <span className="block max-w-48 truncate text-muted-foreground">
        {row.original.avatar_url || "N/A"}
      </span>
    ),
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
        <AppUserActionsMenu user={row.original} />
      </div>
    ),
  },
]

function AppUsersTableContent() {
  const { data: users } = useSuspenseQuery(getAppUsersQueryOptions())

  if (users.data.length === 0) {
    return (
      <EmptyState
        title="No App users yet"
        description="Users will appear here after the App device login API is used."
      />
    )
  }

  return <DataTable columns={columns} data={users.data} />
}

function AppUsersTable() {
  return (
    <Suspense
      fallback={
        <div className="py-12 text-center text-muted-foreground">
          Loading App users...
        </div>
      }
    >
      <AppUsersTableContent />
    </Suspense>
  )
}

function AppUsers() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="App Users"
        description="Manage mobile App users and account availability."
      />
      <AppUsersTable />
    </div>
  )
}
