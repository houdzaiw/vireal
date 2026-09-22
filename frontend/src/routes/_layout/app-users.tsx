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
    accessorKey: "email",
    header: "Email",
    cell: ({ row }) => (
      <span className="font-medium">
        {row.original.email || "Legacy test user"}
      </span>
    ),
  },
  {
    accessorKey: "auth_providers",
    header: "Login methods",
    cell: ({ row }) => {
      const providers = row.original.auth_providers ?? []
      return (
        <span className="text-muted-foreground">
          {providers.length > 0 ? providers.join(", ") : "device"}
        </span>
      )
    },
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
    accessorKey: "last_login_at",
    header: "Last login",
    cell: ({ row }) => <DateTime value={row.original.last_login_at} />,
  },
  {
    accessorKey: "login_count",
    header: "Logins",
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
        description="Invited users will appear here after their first Clerk sign-in."
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
        description="Review invited users, login methods, recent access, and account availability."
      />
      <AppUsersTable />
    </div>
  )
}
