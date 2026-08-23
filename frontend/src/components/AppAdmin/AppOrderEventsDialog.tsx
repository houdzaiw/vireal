import { useQuery } from "@tanstack/react-query"
import { Eye } from "lucide-react"
import { useState } from "react"

import { AdminAppService, type AppOrderPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { DateTime, ProviderBadge, StatusBadge } from "./common"

interface AppOrderEventsDialogProps {
  order: AppOrderPublic
}

export function AppOrderEventsDialog({ order }: AppOrderEventsDialogProps) {
  const [isOpen, setIsOpen] = useState(false)
  const { data: events, isLoading } = useQuery({
    queryFn: async () =>
      (
        await AdminAppService.readAppOrderEvents({
          path: { order_id: order.id },
        })
      ).data,
    queryKey: ["admin-app-order-events", order.id],
    enabled: isOpen,
  })

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <Button variant="ghost" size="icon" onClick={() => setIsOpen(true)}>
        <Eye />
        <span className="sr-only">View events</span>
      </Button>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Order Events</DialogTitle>
          <DialogDescription>
            Callback events recorded for order {order.id}.
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <div className="py-8 text-center text-muted-foreground">
            Loading events...
          </div>
        ) : events?.data.length ? (
          <div className="space-y-4">
            {events.data.map((event) => (
              <div key={event.id} className="rounded-md border p-4">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <ProviderBadge provider={event.provider} />
                  <StatusBadge status={event.status} />
                  <span className="text-sm font-medium">
                    {event.event_type}
                  </span>
                  <DateTime value={event.created_at} />
                </div>
                <dl className="grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-muted-foreground">Event ID</dt>
                    <dd className="break-all font-mono text-xs">
                      {event.event_id}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Transaction ID</dt>
                    <dd className="break-all font-mono text-xs">
                      {event.transaction_id ?? "N/A"}
                    </dd>
                  </div>
                </dl>
                <pre className="mt-3 max-h-56 overflow-auto rounded-md bg-muted p-3 text-xs">
                  {event.raw_payload}
                </pre>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-8 text-center text-muted-foreground">
            No events recorded.
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
