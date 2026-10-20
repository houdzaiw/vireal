import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import { Coins } from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import {
  AdminAppService,
  AdminEffectCatalogService,
  UsersService,
} from "@/client"
import { CopyId, DateTime, PageHeader } from "@/components/AppAdmin/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { createIdempotencyKey } from "@/utils"

export const Route = createFileRoute("/_layout/coin-wallet")({
  component: CoinWallet,
  beforeLoad: async () => {
    const { data: user } = await UsersService.readUserMe()
    if (!user.is_superuser) throw redirect({ to: "/" })
  },
  head: () => ({ meta: [{ title: "Coin Wallet - Vireal Admin" }] }),
})

function CoinWallet() {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState("")
  const [appUserId, setAppUserId] = useState("")
  const [delta, setDelta] = useState(0)
  const [reason, setReason] = useState("")
  const [ledgerSkip, setLedgerSkip] = useState(0)
  const ledgerLimit = 25
  const validUserId = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(
    appUserId,
  )
  const wallet = useQuery({
    queryKey: ["admin-app-wallet", appUserId, ledgerSkip],
    queryFn: async () =>
      (
        await AdminAppService.readAppUserWallet({
          path: { app_user_id: appUserId },
          query: { skip: ledgerSkip, limit: ledgerLimit },
        })
      ).data,
    enabled: validUserId,
    retry: false,
  })
  function selectUser(id: string) {
    setAppUserId(id)
    setLedgerSkip(0)
  }
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
          idempotency_key: createIdempotencyKey(),
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
      queryClient.invalidateQueries({
        queryKey: ["admin-app-wallet", appUserId],
      })
    },
    onError: () => toast.error("调整失败：请确认用户、金额和余额"),
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Coin Wallet"
        description="先只读核对当前余额和关联流水；调账是独立操作，需要原因并写入管理员审计。"
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
                  onClick={() => selectUser(user.id)}
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
              <Label htmlFor="coin-adjust-user">App User ID</Label>
              <Input
                id="coin-adjust-user"
                value={appUserId}
                onChange={(event) => selectUser(event.target.value.trim())}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="coin-adjust-amount">调整数量（可为负数）</Label>
              <Input
                id="coin-adjust-amount"
                type="number"
                value={delta}
                onChange={(event) => setDelta(Number(event.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="coin-adjust-reason">原因</Label>
              <Input
                id="coin-adjust-reason"
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
      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">余额与流水（只读）</h2>
            <Button
              variant="outline"
              disabled={!validUserId || wallet.isFetching}
              onClick={() => wallet.refetch()}
            >
              刷新余额与流水
            </Button>
          </div>
          {!validUserId ? (
            <p>
              选择用户或输入有效的 App User ID 后查看，不会创建账户或调整余额。
            </p>
          ) : wallet.isError ? (
            <p role="alert">读取失败，请确认权限或稍后重试；未进行任何调整。</p>
          ) : wallet.isPending ? (
            <p>正在读取余额与流水…</p>
          ) : (
            <>
              <p className="text-lg" data-testid="wallet-current-balance">
                当前余额：{wallet.data.balance} 金币
              </p>
              {!wallet.data.account_initialized && (
                <p>该用户尚未初始化金币账户；本次查看不会创建账户。</p>
              )}
              <p className="text-sm text-muted-foreground">
                共 {wallet.data.count}{" "}
                笔流水；每笔“余额”是发生时的历史快照，不代表当前余额。
              </p>
              {wallet.data.ledger.length === 0 ? (
                <p>暂无流水。</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b">
                        {[
                          "时间",
                          "类型",
                          "变动",
                          "历史余额",
                          "关联订单",
                          "关联任务",
                          "原因",
                        ].map((title) => (
                          <th className="px-3 py-2" key={title}>
                            {title}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {wallet.data.ledger.map((entry) => (
                        <tr className="border-b" key={entry.id}>
                          <td className="px-3 py-2">
                            <DateTime value={entry.created_at} />
                          </td>
                          <td className="px-3 py-2">{entry.entry_type}</td>
                          <td className="px-3 py-2">
                            {entry.delta > 0 ? "+" : ""}
                            {entry.delta}
                          </td>
                          <td className="px-3 py-2">{entry.balance_after}</td>
                          <td className="px-3 py-2">
                            {entry.order_id ? (
                              <CopyId id={entry.order_id} />
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="px-3 py-2">
                            {entry.task_id ? (
                              <CopyId id={entry.task_id} />
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="px-3 py-2">{entry.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  disabled={ledgerSkip === 0 || wallet.isFetching}
                  onClick={() =>
                    setLedgerSkip(Math.max(0, ledgerSkip - ledgerLimit))
                  }
                >
                  上一页
                </Button>
                <span>第 {Math.floor(ledgerSkip / ledgerLimit) + 1} 页</span>
                <Button
                  variant="outline"
                  disabled={
                    ledgerSkip + ledgerLimit >= wallet.data.count ||
                    wallet.isFetching
                  }
                  onClick={() => setLedgerSkip(ledgerSkip + ledgerLimit)}
                >
                  下一页
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
