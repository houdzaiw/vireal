import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { Suspense } from "react"

import { AdminAppService, type AppOrderPublic, UsersService } from "@/client"
import { AppOrderEventsDialog } from "@/components/AppAdmin/AppOrderEventsDialog"
import {
  CopyId,
  DateTime,
  EmptyState,
  PageHeader,
  ProviderBadge,
  StatusBadge,
} from "@/components/AppAdmin/common"
import { DataTable } from "@/components/Common/DataTable"

function getAppOrdersQueryOptions() {
  return {
    queryFn: async () =>
      (
        await AdminAppService.readAppOrders({
          query: { skip: 0, limit: 100 },
        })
      ).data,
    queryKey: ["admin-app-orders"],
  }
}

export const Route = createFileRoute("/_layout/app-orders")({
  component: AppOrders,
  beforeLoad: async () => {
    const { data: user } = await UsersService.readUserMe()
    if (!user.is_superuser) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({
    meta: [{ title: "App Orders - App Server Platform" }],
  }),
})

function formatAmount(order: AppOrderPublic) {
  if (order.amount == null) {
    return "N/A"
  }
  return `${order.amount} ${order.currency ?? ""}`.trim()
}

const columns: ColumnDef<AppOrderPublic>[] = [
  {
    accessorKey: "id",
    header: "ID",
    cell: ({ row }) => <CopyId id={row.original.id} />,
  },
  {
    accessorKey: "product_id",
    header: "Product",
    cell: ({ row }) => (
      <span className="font-medium">{row.original.product_id}</span>
    ),
  },
  {
    accessorKey: "provider",
    header: "Provider",
    cell: ({ row }) => <ProviderBadge provider={row.original.provider} />,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  },
  {
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {formatAmount(row.original)}
      </span>
    ),
  },
  {
    accessorKey: "transaction_id",
    header: "Transaction",
    cell: ({ row }) => (
      <span className="block max-w-48 truncate font-mono text-xs text-muted-foreground">
        {row.original.transaction_id ?? "N/A"}
      </span>
    ),
  },
  {
    accessorKey: "paid_at",
    header: "Paid",
    cell: ({ row }) => <DateTime value={row.original.paid_at} />,
  },
  {
    id: "events",
    header: () => <span className="sr-only">Events</span>,
    cell: ({ row }) => (
      <div className="flex justify-end">
        <AppOrderEventsDialog order={row.original} />
      </div>
    ),
  },
]

function AppOrdersTableContent() {
  const { data: orders } = useSuspenseQuery(getAppOrdersQueryOptions())

  if (orders.data.length === 0) {
    return (
      <EmptyState
        title="No App orders yet"
        description="Orders will appear here after App users start payment flows."
      />
    )
  }

  return <DataTable columns={columns} data={orders.data} />
}

function AppOrdersTable() {
  return (
    <Suspense
      fallback={
        <div className="py-12 text-center text-muted-foreground">
          Loading App orders...
        </div>
      }
    >
      <AppOrdersTableContent />
    </Suspense>
  )
}

function AppOrders() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="App Orders"
        description="Inspect payment order status and callback events."
      />
      <AppOrdersTable />
    </div>
  )
}
