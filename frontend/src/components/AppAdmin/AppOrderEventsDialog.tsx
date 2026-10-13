import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Eye } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

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
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const queryClient = useQueryClient()
  const { data: cases } = useQuery({
    queryKey: ["admin-payment-cases", order.id],
    enabled: isOpen && order.provider === "paypal",
    queryFn: async () =>
      (await AdminAppService.readPaymentCases({ path: { order_id: order.id } }))
        .data,
  })
  const resolve = useMutation({
    mutationFn: async ({
      id,
      resolution,
    }: {
      id: string
      resolution: "recover" | "dismiss"
    }) => {
      const reason = (reasons[id] || "").trim()
      if (reason.length < 3)
        throw new Error("Enter a review reason (at least 3 characters)")
      return AdminAppService.resolvePaymentCase({
        path: { case_id: id },
        body: { resolution, reason },
      })
    },
    onSuccess: async () => {
      toast.success("Case resolved and audited")
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["admin-payment-cases", order.id],
        }),
        queryClient.invalidateQueries({ queryKey: ["admin-app-orders"] }),
      ])
    },
    onError: (error) =>
      toast.error(
        error.message ||
          "Case could not be resolved; account remains under review",
      ),
  })
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
        {order.provider === "paypal" && (
          <div className="space-y-3">
            <h3 className="font-semibold">Refunds & disputes</h3>
            <p className="text-sm text-muted-foreground">
              Cash refunds are processed manually in PayPal. Insufficient credit
              balance keeps the account frozen. Dispute recovery requires a
              verified buyer win and refund amount; dismissal requires a seller
              win or buyer cancellation. Partial-refund reviews require the
              verified refund webhook.
            </p>
            {cases?.length ? (
              cases.map((item) => (
                <div key={item.id} className="rounded-md border p-4 space-y-2">
                  <p>
                    {item.kind} · {item.status} · recovery {item.required_coins}{" "}
                    credits / recovered {item.recovered_coins}
                  </p>
                  <p className="font-mono text-xs break-all">
                    {item.external_id}
                  </p>
                  {item.status === "open" ? (
                    <>
                      <input
                        className="border rounded px-3 py-2 w-full"
                        aria-label={`Review reason ${item.id}`}
                        maxLength={500}
                        value={reasons[item.id] || ""}
                        onChange={(event) =>
                          setReasons({
                            ...reasons,
                            [item.id]: event.target.value,
                          })
                        }
                        placeholder="Verified review reason"
                      />
                      <Button
                        disabled={
                          item.kind === "refund_review" ||
                          resolve.isPending ||
                          (reasons[item.id] || "").trim().length < 3
                        }
                        onClick={() => {
                          if (
                            window.confirm(
                              "Recover the required credits and resolve this verified payment case?",
                            )
                          )
                            resolve.mutate({
                              id: item.id,
                              resolution: "recover",
                            })
                        }}
                      >
                        Recover credits & resolve
                      </Button>
                      {item.kind === "dispute" && (
                        <Button
                          variant="outline"
                          disabled={
                            resolve.isPending ||
                            (reasons[item.id] || "").trim().length < 3
                          }
                          onClick={() => {
                            if (
                              window.confirm(
                                "Verify PayPal resolved this dispute in the seller’s favour and dismiss it?",
                              )
                            )
                              resolve.mutate({
                                id: item.id,
                                resolution: "dismiss",
                              })
                          }}
                        >
                          Verify seller win & dismiss
                        </Button>
                      )}
                    </>
                  ) : (
                    <p className="text-sm">
                      {item.resolution}: {item.reason}
                    </p>
                  )}
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No payment cases.</p>
            )}
          </div>
        )}
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
