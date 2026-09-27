import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import { Archive, ImageUp, Plus, Save, Send, Trash2, Video } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import {
  AdminEffectCatalogService,
  type AdminEffectInput,
  type AdminEffectPublic,
  type AdminVariantInput,
  type AdminVariantPublic,
  UsersService,
} from "@/client"
import { PageHeader } from "@/components/AppAdmin/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export const Route = createFileRoute("/_layout/effects")({
  component: Effects,
  beforeLoad: async () => {
    const { data: user } = await UsersService.readUserMe()
    if (!user.is_superuser) throw redirect({ to: "/" })
  },
  head: () => ({ meta: [{ title: "Effects - Vireal Admin" }] }),
})

const models = [
  "minimax/video-01",
  "wan-video/wan-2.7-r2v",
  "bytedance/seedance-2.0",
] as const

const defaultVariant: AdminVariantInput = {
  duration_seconds: 5,
  coin_cost: 10,
  provider: "replicate",
  model: models[0],
  model_type: "image-to-video",
  prompt: "Create a natural, cinematic moment from the uploaded portrait.",
  negative_prompt: "distorted face, extra limbs, text, watermark",
  prompt_version: "v1",
  is_default: true,
  is_enabled: true,
}

function asEffectInput(effect: AdminEffectPublic): AdminEffectInput {
  return {
    category_id: effect.category_id,
    slug: effect.slug,
    title_zh: effect.title_zh,
    title_en: effect.title_en,
    description: effect.description,
    input_image_count: effect.input_image_count,
    poster_asset_id: effect.poster_asset_id,
    preview_asset_id: effect.preview_asset_id,
    sort_order: effect.sort_order,
    is_enabled: effect.is_enabled,
    recommendation_label: effect.recommendation_label,
    recommendation_ids: effect.recommendation_ids,
  }
}

function VariantEditor({
  effectId,
  variant,
  refresh,
}: {
  effectId: string
  variant: AdminVariantPublic
  refresh: () => Promise<unknown>
}) {
  const [value, setValue] = useState<AdminVariantInput>(variant)
  const set = <K extends keyof AdminVariantInput>(
    key: K,
    next: AdminVariantInput[K],
  ) => setValue((current) => ({ ...current, [key]: next }))
  const update = useMutation({
    mutationFn: () =>
      AdminEffectCatalogService.updateVariant({
        path: { effect_id: effectId, variant_id: variant.id },
        body: value,
      }),
    onSuccess: async () => {
      toast.success("变体已保存")
      await refresh()
    },
    onError: () => toast.error("变体不符合模型规则，请检查时长和提示词"),
  })
  const remove = useMutation({
    mutationFn: () =>
      AdminEffectCatalogService.deleteVariant({
        path: { effect_id: effectId, variant_id: variant.id },
      }),
    onSuccess: async () => {
      toast.success("变体已删除")
      await refresh()
    },
    onError: () => toast.error("变体删除失败"),
  })

  return (
    <div className="space-y-4 rounded-lg border p-4">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="space-y-2">
          <Label>模型</Label>
          <select
            className="h-9 w-full rounded-md border bg-background px-3 text-sm"
            value={value.model}
            onChange={(e) => set("model", e.target.value)}
          >
            {models.map((model) => (
              <option key={model}>{model}</option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label>模型类型</Label>
          <Input
            value={value.model_type}
            onChange={(e) => set("model_type", e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label>时长（秒）</Label>
          <Input
            type="number"
            min={1}
            max={60}
            value={value.duration_seconds}
            onChange={(e) => set("duration_seconds", Number(e.target.value))}
          />
        </div>
        <div className="space-y-2">
          <Label>金币价格</Label>
          <Input
            type="number"
            min={0}
            value={value.coin_cost}
            onChange={(e) => set("coin_cost", Number(e.target.value))}
          />
        </div>
      </div>
      <div className="space-y-2">
        <Label>生成提示词</Label>
        <textarea
          className="min-h-24 w-full rounded-md border bg-background px-3 py-2 text-sm"
          value={value.prompt}
          onChange={(e) => set("prompt", e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label>负向提示词</Label>
        <textarea
          className="min-h-20 w-full rounded-md border bg-background px-3 py-2 text-sm"
          value={value.negative_prompt ?? ""}
          onChange={(e) => set("negative_prompt", e.target.value || null)}
        />
      </div>
      <div className="flex flex-wrap items-center gap-5">
        <div className="flex items-center gap-2 text-sm">
          <Checkbox
            aria-label="默认变体"
            checked={value.is_default}
            onCheckedChange={(checked) => set("is_default", checked === true)}
          />
          默认变体
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Checkbox
            aria-label="启用变体"
            checked={value.is_enabled}
            onCheckedChange={(checked) => set("is_enabled", checked === true)}
          />
          启用
        </div>
        <div className="ml-auto flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
          >
            <Trash2 /> 删除
          </Button>
          <Button
            size="sm"
            onClick={() => update.mutate()}
            disabled={update.isPending || !value.prompt}
          >
            <Save /> 保存变体
          </Button>
        </div>
      </div>
    </div>
  )
}

function Effects() {
  const client = useQueryClient()
  const [selectedId, setSelectedId] = useState<string>()
  const [categoryFilter, setCategoryFilter] = useState("")
  const [draft, setDraft] = useState<AdminEffectInput>()
  const categories = useQuery({
    queryKey: ["effect-categories"],
    queryFn: async () =>
      (await AdminEffectCatalogService.listCategories()).data,
  })
  const effects = useQuery({
    queryKey: ["effects", categoryFilter],
    queryFn: async () =>
      (
        await AdminEffectCatalogService.listEffects({
          query: { category_id: categoryFilter || undefined },
        })
      ).data,
  })
  const selected = useMemo(
    () => effects.data?.data.find((effect) => effect.id === selectedId),
    [effects.data, selectedId],
  )
  useEffect(() => {
    if (!selectedId && effects.data?.data[0])
      setSelectedId(effects.data.data[0].id)
  }, [effects.data, selectedId])
  useEffect(() => {
    if (selected) setDraft(asEffectInput(selected))
  }, [selected])
  const refresh = async () =>
    client.invalidateQueries({ queryKey: ["effects"] })
  const save = useMutation({
    mutationFn: () =>
      AdminEffectCatalogService.updateEffect({
        path: { effect_id: selectedId! },
        body: draft!,
      }),
    onSuccess: async () => {
      toast.success("效果已保存")
      await refresh()
    },
    onError: () => toast.error("效果保存失败，请检查 slug、媒体和推荐关系"),
  })
  const create = useMutation({
    mutationFn: async () => {
      const categoryId = categoryFilter || categories.data?.data[0]?.id
      if (!categoryId) throw new Error("category required")
      const suffix = Date.now().toString().slice(-6)
      return AdminEffectCatalogService.createEffect({
        body: {
          category_id: categoryId,
          slug: `new-effect-${suffix}`,
          title_zh: "新效果",
          title_en: `NEW EFFECT ${suffix}`,
          input_image_count: 1,
          sort_order: (effects.data?.count ?? 0) * 10 + 10,
          is_enabled: true,
          recommendation_ids: [],
        },
      })
    },
    onSuccess: async ({ data }) => {
      await refresh()
      setSelectedId(data.id)
      toast.success("已创建草稿效果")
    },
    onError: () => toast.error("请先创建分类"),
  })
  const publish = useMutation({
    mutationFn: () =>
      AdminEffectCatalogService.publishEffect({
        path: { effect_id: selectedId! },
      }),
    onSuccess: async () => {
      toast.success("效果已发布")
      await refresh()
    },
    onError: () =>
      toast.error("发布失败：请确认至少有一个有效变体且模型配置合规"),
  })
  const archive = useMutation({
    mutationFn: () =>
      AdminEffectCatalogService.deleteEffect({
        path: { effect_id: selectedId! },
      }),
    onSuccess: async () => {
      toast.success("效果已归档")
      setSelectedId(undefined)
      await refresh()
    },
    onError: () => toast.error("归档失败"),
  })
  const addVariant = useMutation({
    mutationFn: () =>
      AdminEffectCatalogService.createVariant({
        path: { effect_id: selectedId! },
        body: defaultVariant,
      }),
    onSuccess: async () => {
      toast.success("已添加变体")
      await refresh()
    },
    onError: () => toast.error("变体创建失败"),
  })
  const upload = async (kind: "poster" | "preview_video", file?: File) => {
    if (!file) return
    try {
      const { data } = await AdminEffectCatalogService.uploadMediaAsset({
        body: { kind, file },
      })
      setDraft((current) =>
        current
          ? {
              ...current,
              [kind === "poster" ? "poster_asset_id" : "preview_asset_id"]:
                data.id,
            }
          : current,
      )
      toast.success("媒体已上传，请保存效果以生效")
    } catch {
      toast.error("媒体上传失败，请检查格式和大小")
    }
  }
  const set = <K extends keyof AdminEffectInput>(
    key: K,
    value: AdminEffectInput[K],
  ) => setDraft((current) => (current ? { ...current, [key]: value } : current))

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Effects"
        description="目录内容以这里为最终真值；只有通过发布校验的效果才会出现在 H5。"
        action={
          <Button onClick={() => create.mutate()}>
            <Plus /> 新建效果
          </Button>
        }
      />
      <div className="grid min-h-[680px] gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
        <Card className="self-start">
          <CardContent className="space-y-4">
            <select
              className="h-9 w-full rounded-md border bg-background px-3 text-sm"
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value)
                setSelectedId(undefined)
              }}
            >
              <option value="">全部分类</option>
              {categories.data?.data.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name_zh}
                </option>
              ))}
            </select>
            <div className="max-h-[600px] space-y-1 overflow-auto">
              {effects.data?.data.map((effect) => (
                <button
                  type="button"
                  key={effect.id}
                  onClick={() => setSelectedId(effect.id)}
                  className={`w-full rounded-lg px-3 py-3 text-left transition-colors hover:bg-muted ${effect.id === selectedId ? "bg-muted" : ""}`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-medium">{effect.title_zh}</span>
                    <Badge
                      variant={
                        effect.publish_status === "published"
                          ? "default"
                          : "secondary"
                      }
                    >
                      {effect.publish_status}
                    </Badge>
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {effect.title_en} · {effect.variants?.length ?? 0} variants
                  </span>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
        {!draft || !selected ? (
          <div className="grid place-items-center rounded-xl border border-dashed text-muted-foreground">
            请选择一个效果
          </div>
        ) : (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  基础信息{" "}
                  <Badge variant="outline">{selected.publish_status}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <div className="space-y-2">
                    <Label>所属分类</Label>
                    <select
                      className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                      value={draft.category_id}
                      onChange={(e) => set("category_id", e.target.value)}
                    >
                      {categories.data?.data.map((category) => (
                        <option key={category.id} value={category.id}>
                          {category.name_zh}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label>中文名称</Label>
                    <Input
                      value={draft.title_zh}
                      onChange={(e) => set("title_zh", e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>英文名称</Label>
                    <Input
                      value={draft.title_en}
                      onChange={(e) => set("title_en", e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Slug</Label>
                    <Input
                      value={draft.slug}
                      onChange={(e) => set("slug", e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>上传图片数</Label>
                    <select
                      className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                      value={draft.input_image_count}
                      onChange={(e) =>
                        set("input_image_count", Number(e.target.value))
                      }
                    >
                      <option value={1}>1 张</option>
                      <option value={2}>2 张</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label>排序</Label>
                    <Input
                      type="number"
                      value={draft.sort_order}
                      onChange={(e) =>
                        set("sort_order", Number(e.target.value))
                      }
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>描述</Label>
                  <textarea
                    className="min-h-20 w-full rounded-md border bg-background px-3 py-2 text-sm"
                    value={draft.description ?? ""}
                    onChange={(e) => set("description", e.target.value || null)}
                  />
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>推荐标题</Label>
                    <Input
                      value={draft.recommendation_label ?? ""}
                      onChange={(e) =>
                        set("recommendation_label", e.target.value || null)
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>推荐效果 ID（逗号分隔）</Label>
                    <Input
                      value={(draft.recommendation_ids ?? []).join(", ")}
                      onChange={(e) =>
                        set(
                          "recommendation_ids",
                          e.target.value
                            .split(",")
                            .map((id) => id.trim())
                            .filter(Boolean),
                        )
                      }
                    />
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <label className="flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted">
                    <ImageUp className="size-4" />
                    上传封面
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      hidden
                      onChange={(e) =>
                        void upload("poster", e.target.files?.[0])
                      }
                    />
                  </label>
                  <label className="flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted">
                    <Video className="size-4" />
                    上传预览视频
                    <input
                      type="file"
                      accept="video/mp4,video/webm"
                      hidden
                      onChange={(e) =>
                        void upload("preview_video", e.target.files?.[0])
                      }
                    />
                  </label>
                  <span className="text-xs text-muted-foreground">
                    封面 {draft.poster_asset_id ? "已绑定" : "使用缺省视觉"} ·
                    视频 {draft.preview_asset_id ? "已绑定" : "未绑定"}
                  </span>
                  <div className="ml-auto flex items-center gap-2 text-sm">
                    <Checkbox
                      aria-label="启用效果"
                      checked={draft.is_enabled}
                      onCheckedChange={(checked) =>
                        set("is_enabled", checked === true)
                      }
                    />
                    启用
                  </div>
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  <Button variant="outline" onClick={() => archive.mutate()}>
                    <Archive />
                    归档
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => save.mutate()}
                    disabled={save.isPending}
                  >
                    <Save />
                    保存
                  </Button>
                  <Button
                    onClick={() => publish.mutate()}
                    disabled={publish.isPending}
                  >
                    <Send />
                    发布
                  </Button>
                </div>
              </CardContent>
            </Card>
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">生成变体</h2>
                <p className="text-sm text-muted-foreground">
                  客户端只提交变体 ID；模型、价格、时长和提示词均由服务端解析。
                </p>
              </div>
              <Button variant="outline" onClick={() => addVariant.mutate()}>
                <Plus />
                添加变体
              </Button>
            </div>
            <div className="space-y-4">
              {selected.variants?.map((variant) => (
                <VariantEditor
                  key={variant.id}
                  effectId={selected.id}
                  variant={variant}
                  refresh={refresh}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
