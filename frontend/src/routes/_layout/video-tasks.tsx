import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import { useRef, useState } from "react"
import { toast } from "sonner"

import {
  type AdminVideoTaskResolve,
  AdminVideoTasksService,
  UsersService,
} from "@/client"
import {
  CopyId,
  DateTime,
  PageHeader,
  StatusBadge,
} from "@/components/AppAdmin/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { createIdempotencyKey } from "@/utils"

export const Route = createFileRoute("/_layout/video-tasks")({
  component: VideoTasks,
  beforeLoad: async () => {
    const { data: user } = await UsersService.readUserMe()
    if (!user.is_superuser) throw redirect({ to: "/" })
  },
  head: () => ({ meta: [{ title: "Video Tasks - Vireal Admin" }] }),
})

function VideoTasks() {
  const queryClient = useQueryClient()
  const [reviewOnly, setReviewOnly] = useState(true)
  const [selectedId, setSelectedId] = useState("")
  const [reason, setReason] = useState("")
  const [evidence, setEvidence] = useState("")
  const [confirmed, setConfirmed] = useState(false)
  const [resolution, setResolution] =
    useState<AdminVideoTaskResolve["resolution"]>("not_submitted")
  const requestKeys = useRef(
    new Map<string, { signature: string; key: string }>(),
  )
  const tasks = useQuery({
    queryKey: ["admin-video-tasks", reviewOnly],
    queryFn: async () =>
      (
        await AdminVideoTasksService.readVideoTasks({
          query: { limit: 100, needs_review: reviewOnly },
        })
      ).data,
    refetchInterval: 60000,
  })
  const details = useQuery({
    queryKey: ["admin-video-task", selectedId],
    queryFn: async () =>
      (
        await AdminVideoTasksService.readVideoTask({
          path: { task_id: selectedId },
        })
      ).data,
    enabled: Boolean(selectedId),
  })
  const task = details.data
  const keyFor = (operation: string) => {
    const signature = JSON.stringify({
      selectedId,
      reason,
      evidence,
      resolution,
    })
    const previous = requestKeys.current.get(operation)
    if (previous?.signature === signature) return previous.key
    const key = createIdempotencyKey()
    requestKeys.current.set(operation, { signature, key })
    return key
  }
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin-video-tasks"] }),
      queryClient.invalidateQueries({
        queryKey: ["admin-video-task", selectedId],
      }),
      queryClient.invalidateQueries({ queryKey: ["admin-app-operation-logs"] }),
    ])
  }
  const reconcile = useMutation({
    mutationFn: () =>
      AdminVideoTasksService.reconcileVideoTask({
        path: { task_id: selectedId },
        body: { reason: reason.trim(), idempotency_key: keyFor("reconcile") },
      }),
    onSuccess: async () => {
      requestKeys.current.delete("reconcile")
      toast.success("核查完成，请查看最新状态；查询异常不代表生成失败")
      await refresh()
    },
    onError: () =>
      toast.error(
        "核查未完成。没有任务 ID 时请先获取供应商证据，不能重新生成。",
      ),
  })
  const resolve = useMutation({
    mutationFn: () =>
      AdminVideoTasksService.resolveVideoTask({
        path: { task_id: selectedId },
        body: {
          reason: reason.trim(),
          idempotency_key: keyFor("resolve"),
          resolution,
          evidence: evidence.trim(),
          provider_confirmed: true,
        },
      }),
    onSuccess: async () => {
      requestKeys.current.delete("resolve")
      toast.success("已审计结案，金币补偿仅按原扣币快照执行一次")
      setConfirmed(false)
      await refresh()
    },
    onError: () =>
      toast.error(
        "结案未完成：请核对证据、任务状态和原始扣币流水，不要直接修改余额。",
      ),
  })
  const busy = reconcile.isPending || resolve.isPending
  const canResolve =
    task &&
    !task.coin_refunded_at &&
    ([
      "submitting",
      "submission_unknown",
      "pending",
      "running",
      "saving",
    ].includes(task.status) ||
      (task.status === "expired" && !task.completed_at))

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Video Tasks"
        description="新版付费视频任务与异常核查。这里只查询已有预测，不创建生成任务或现金退款。"
      />
      <div className="flex gap-3">
        <Button
          variant={reviewOnly ? "default" : "outline"}
          onClick={() => setReviewOnly(true)}
        >
          待核查任务
        </Button>
        <Button
          variant={!reviewOnly ? "default" : "outline"}
          onClick={() => setReviewOnly(false)}
        >
          全部任务
        </Button>
        <Button variant="outline" onClick={() => void refresh()}>
          刷新
        </Button>
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              共 {tasks.data?.count ?? 0} 条；显示最近 100 条，每分钟更新。
            </p>
            {tasks.isLoading && <p>正在读取任务…</p>}
            {tasks.isError && (
              <p role="alert">任务读取失败，请刷新或检查权限。</p>
            )}
            {!tasks.isLoading && tasks.data?.data.length === 0 && (
              <p>当前没有匹配任务。</p>
            )}
            <div className="max-h-[640px] divide-y overflow-auto rounded-lg border">
              {tasks.data?.data.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  disabled={busy}
                  onClick={() => {
                    setSelectedId(item.id)
                    setReason("")
                    setEvidence("")
                    setConfirmed(false)
                    setResolution(
                      item.provider_task_id ? "failed" : "not_submitted",
                    )
                  }}
                  className={`flex w-full flex-col gap-2 p-4 text-left hover:bg-muted ${selectedId === item.id ? "bg-muted" : ""}`}
                >
                  <span className="flex justify-between gap-2">
                    <strong>
                      {item.template_id} · {item.duration}s
                    </strong>
                    <StatusBadge status={item.status} />
                  </span>
                  <span className="break-all font-mono text-xs">{item.id}</span>
                  <span className="text-sm text-muted-foreground">
                    用户 {item.app_user_id} · {item.model}
                  </span>
                  <span className="text-sm">
                    扣币{" "}
                    {(item.ledger ?? [])
                      .filter((row) => row.entry_type === "generation_debit")
                      .reduce((sum, row) => sum - row.delta, 0)}{" "}
                    / 退币{" "}
                    {(item.ledger ?? [])
                      .filter((row) => row.entry_type === "generation_refund")
                      .reduce((sum, row) => sum + row.delta, 0)}
                  </span>
                  <span className="text-xs">
                    最后核查：
                    <DateTime value={item.provider_last_checked_at} />
                  </span>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-4">
            {!task && <p>选择任务查看流水与处置选项。</p>}
            {details.isError && <p role="alert">任务详情读取失败。</p>}
            {task && (
              <>
                <h2 className="font-semibold">任务详情</h2>
                <CopyId id={task.id} />
                <div className="text-sm">
                  用户：
                  <CopyId id={task.app_user_id} />
                </div>
                <p className="break-all text-sm">
                  供应商 ID：
                  {task.provider_task_id || "未知；必须人工核实，禁止重试生成"}
                </p>
                <p className="text-sm">
                  提交：
                  <DateTime value={task.submission_attempted_at} /> · 完成：
                  <DateTime value={task.completed_at} />
                </p>
                <p className="text-sm">
                  最后核查：
                  <DateTime value={task.provider_last_checked_at} /> · 下次：
                  <DateTime value={task.provider_next_check_at} />
                </p>
                <p className="text-sm">
                  金币退回：
                  <DateTime value={task.coin_refunded_at} />
                </p>
                {task.error && (
                  <p className="text-sm text-destructive">{task.error}</p>
                )}
                <div className="rounded-lg border p-3 text-sm">
                  {(task.ledger ?? []).map((row) => (
                    <p key={row.id}>
                      {row.entry_type}: {row.delta} · 余额 {row.balance_after}
                    </p>
                  ))}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="task-reason">操作原因（至少 5 字）</Label>
                  <Input
                    id="task-reason"
                    value={reason}
                    disabled={busy}
                    onChange={(event) => setReason(event.target.value)}
                  />
                </div>
                <Button
                  disabled={
                    busy || !task.provider_task_id || reason.trim().length < 5
                  }
                  onClick={() => reconcile.mutate()}
                >
                  核对供应商状态
                </Button>
                {canResolve && (
                  <div className="space-y-3 rounded-lg border border-destructive/30 p-4">
                    <h3 className="font-semibold">有证据的人工结案</h3>
                    <p className="text-sm text-muted-foreground">
                      超时、404、暂时查不到记录均不是失败证据。供应商已接受的任务仍占当天名额；补偿不允许手工填写金额。
                    </p>
                    <Label htmlFor="task-resolution">核实结果</Label>
                    <select
                      id="task-resolution"
                      className="w-full rounded-md border bg-background p-2"
                      value={resolution}
                      disabled={busy}
                      onChange={(event) =>
                        setResolution(
                          event.target
                            .value as AdminVideoTaskResolve["resolution"],
                        )
                      }
                    >
                      <option
                        value="not_submitted"
                        disabled={Boolean(
                          task.provider_task_id ||
                            task.real_submission_counted_at,
                        )}
                      >
                        确认未提交
                      </option>
                      <option value="failed">供应商确认失败</option>
                      <option value="canceled">供应商确认取消</option>
                      <option value="unavailable">确认结果已无法交付</option>
                    </select>
                    <Label htmlFor="task-evidence">
                      证据说明/供应商工单号（至少 10
                      字，勿填密钥或私人图片地址）
                    </Label>
                    <textarea
                      id="task-evidence"
                      className="min-h-24 w-full rounded-md border bg-background p-2"
                      value={evidence}
                      disabled={busy}
                      onChange={(event) => setEvidence(event.target.value)}
                    />
                    <label className="flex items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={confirmed}
                        disabled={busy}
                        onChange={(event) => setConfirmed(event.target.checked)}
                      />
                      我已核实供应商证据，不是根据等待时间或查询错误推断失败。
                    </label>
                    <Button
                      variant="destructive"
                      disabled={
                        busy ||
                        !confirmed ||
                        reason.trim().length < 5 ||
                        evidence.trim().length < 10
                      }
                      onClick={() => resolve.mutate()}
                    >
                      按原扣币记录结案
                    </Button>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
