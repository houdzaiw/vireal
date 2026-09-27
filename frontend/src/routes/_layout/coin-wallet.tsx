import { useMutation, useQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import { Coins } from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import {
  AdminAppService,
  AdminEffectCatalogService,
  UsersService,
} from "@/client"
import { PageHeader } from "@/components/AppAdmin/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export const Route = createFileRoute("/_layout/coin-wallet")({
  component: CoinWallet,
  beforeLoad: async () => {
    const { data: user } = await UsersService.readUserMe()
    if (!user.is_superuser) throw redirect({ to: "/" })
  },
  head: () => ({ meta: [{ title: "Coin Wallet - Vireal Admin" }] }),
})

function CoinWallet() {
  const [query, setQuery] = useState("")
  const [appUserId, setAppUserId] = useState("")
  const [delta, setDelta] = useState(0)
  const [reason, setReason] = useState("")
  const users = useQuery({
    queryKey: ["admin-app-users"],
    queryFn: async () =>
      (await AdminAppService.readAppUsers({ query: { skip: 0, limit: 100 } }))
        .data,
  })
  const visibleUsers = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return (users.data?.data ?? []).filter(
      (user) =>
        !needle ||
        [user.id, user.email, user.nickname].some((value) =>
          value?.toLowerCase().includes(needle),
        ),
    )
  }, [query, users.data])
  const adjust = useMutation({
    mutationFn: async () =>
      AdminEffectCatalogService.adjustUserCoins({
        body: {
          app_user_id: appUserId,
          delta,
          reason,
          idempotency_key: crypto.randomUUID(),
        },
      }),
    onSuccess: ({ data }) => {
      toast.success(
        data.applied
          ? `调整成功，余额 ${data.balance}`
          : `请求已处理，余额 ${data.balance}`,
      )
      setDelta(0)
      setReason("")
    },
    onError: () => toast.error("调整失败：请确认用户、金额和余额"),
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Coin Wallet"
        description="为 App 用户发放或扣减金币。每次操作都要求原因并写入不可变流水与管理员审计。"
      />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,.85fr)]">
        <Card>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>查找用户</Label>
              <Input
                placeholder="邮箱、昵称或用户 ID"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <div className="max-h-[520px] divide-y overflow-auto rounded-lg border">
              {visibleUsers.map((user) => (
                <button
                  type="button"
                  key={user.id}
                  onClick={() => setAppUserId(user.id)}
                  className={`flex w-full items-center justify-between gap-4 px-4 py-3 text-left transition-colors hover:bg-muted ${appUserId === user.id ? "bg-muted" : ""}`}
                >
                  <span>
                    <span className="block font-medium">
                      {user.nickname || user.email || "未命名用户"}
                    </span>
                    <span className="block text-sm text-muted-foreground">
                      {user.email || user.id}
                    </span>
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {user.status}
                  </span>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-5">
            <div className="flex size-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Coins />
            </div>
            <div className="space-y-2">
              <Label>App User ID</Label>
              <Input
                value={appUserId}
                onChange={(event) => setAppUserId(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>调整数量（可为负数）</Label>
              <Input
                type="number"
                value={delta}
                onChange={(event) => setDelta(Number(event.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label>原因</Label>
              <Input
                placeholder="例如：活动赠送 / 客诉补偿"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </div>
            <Button
              className="w-full"
              disabled={
                adjust.isPending || !appUserId || !delta || !reason.trim()
              }
              onClick={() => adjust.mutate()}
            >
              {adjust.isPending ? "提交中…" : "确认调整"}
            </Button>
            <p className="text-sm text-muted-foreground">
              扣减不会让用户余额低于 0；重复请求由服务端幂等键保护。
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
