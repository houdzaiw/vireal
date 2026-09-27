import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import { Plus, Save, Trash2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import {
  type AdminCategoryInput,
  type AdminCategoryPublic,
  AdminEffectCatalogService,
  UsersService,
} from "@/client"
import { PageHeader } from "@/components/AppAdmin/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export const Route = createFileRoute("/_layout/effect-categories")({
  component: EffectCategories,
  beforeLoad: async () => {
    const { data: user } = await UsersService.readUserMe()
    if (!user.is_superuser) throw redirect({ to: "/" })
  },
  head: () => ({ meta: [{ title: "Effect Categories - Vireal Admin" }] }),
})

const emptyCategory: AdminCategoryInput = {
  slug: "",
  name_zh: "",
  name_en: "",
  tones: ["#F3E8FF", "#FCE7F3", "#FFF7ED"],
  sort_order: 0,
  is_enabled: true,
}

function CategoryForm({
  initial,
  onSave,
  onDelete,
  busy,
}: {
  initial: AdminCategoryInput
  onSave: (value: AdminCategoryInput) => void
  onDelete?: () => void
  busy: boolean
}) {
  const [value, setValue] = useState(initial)
  const set = <K extends keyof AdminCategoryInput>(
    key: K,
    next: AdminCategoryInput[K],
  ) => setValue((current) => ({ ...current, [key]: next }))

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr_auto] lg:items-end">
      <div className="space-y-2">
        <Label>中文名称</Label>
        <Input
          value={value.name_zh}
          onChange={(e) => set("name_zh", e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label>English name</Label>
        <Input
          value={value.name_en}
          onChange={(e) => set("name_en", e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label>Slug</Label>
        <Input
          value={value.slug}
          onChange={(e) => set("slug", e.target.value)}
        />
      </div>
      <div className="flex items-center gap-2 pb-2">
        <Checkbox
          checked={value.is_enabled}
          onCheckedChange={(checked) => set("is_enabled", checked === true)}
        />
        <Label>启用</Label>
      </div>
      <div className="space-y-2 lg:col-span-2">
        <Label>渐变缺省色</Label>
        <div className="flex gap-2">
          {value.tones.map((tone, index) => (
            <Input
              key={`${index}-${tone}`}
              type="color"
              aria-label={`渐变色 ${index + 1}`}
              value={tone}
              onChange={(event) => {
                const tones = [...value.tones] as [string, string, string]
                tones[index] = event.target.value
                set("tones", tones)
              }}
              className="h-10 w-16 p-1"
            />
          ))}
        </div>
      </div>
      <div className="space-y-2">
        <Label>排序</Label>
        <Input
          type="number"
          value={value.sort_order}
          onChange={(event) => set("sort_order", Number(event.target.value))}
        />
      </div>
      <div className="flex gap-2">
        {onDelete && (
          <Button variant="outline" onClick={onDelete} disabled={busy}>
            <Trash2 /> 删除/归档
          </Button>
        )}
        <Button
          onClick={() => onSave(value)}
          disabled={busy || !value.slug || !value.name_zh || !value.name_en}
        >
          <Save /> 保存
        </Button>
      </div>
    </div>
  )
}

function EffectCategories() {
  const client = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const categories = useQuery({
    queryKey: ["effect-categories"],
    queryFn: async () =>
      (await AdminEffectCatalogService.listCategories()).data,
  })
  const save = useMutation({
    mutationFn: async ({
      id,
      body,
    }: {
      id?: string
      body: AdminCategoryInput
    }) =>
      id
        ? AdminEffectCatalogService.updateCategory({
            path: { category_id: id },
            body,
          })
        : AdminEffectCatalogService.createCategory({ body }),
    onSuccess: async () => {
      toast.success("分类已保存")
      setShowCreate(false)
      await client.invalidateQueries({ queryKey: ["effect-categories"] })
    },
    onError: () => toast.error("保存失败，请检查 slug 是否重复"),
  })
  const remove = useMutation({
    mutationFn: (categoryId: string) =>
      AdminEffectCatalogService.deleteCategory({
        path: { category_id: categoryId },
      }),
    onSuccess: async ({ data }) => {
      toast.success(
        data.message === "Category archived" ? "分类已归档" : "分类已删除",
      )
      await Promise.all([
        client.invalidateQueries({ queryKey: ["effect-categories"] }),
        client.invalidateQueries({ queryKey: ["effects"] }),
      ])
    },
    onError: () => toast.error("删除或归档失败"),
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Effect Categories"
        description="维护 H5 一级分类、排序和无媒体时的编号渐变视觉。新分类会自动建立 3 条草稿效果。"
        action={
          <Button onClick={() => setShowCreate((value) => !value)}>
            <Plus /> 新建分类
          </Button>
        }
      />
      {showCreate && (
        <Card>
          <CardContent>
            <CategoryForm
              initial={emptyCategory}
              busy={save.isPending}
              onSave={(body) => save.mutate({ body })}
            />
          </CardContent>
        </Card>
      )}
      {categories.isLoading && (
        <p className="text-muted-foreground">加载分类中…</p>
      )}
      <div className="space-y-4">
        {categories.data?.data.map((category: AdminCategoryPublic) => (
          <Card key={category.id}>
            <CardContent>
              <div className="mb-4 flex items-center justify-between text-sm text-muted-foreground">
                <span>{category.effect_count ?? 0} 个效果</span>
                <span className="font-mono">{category.id}</span>
              </div>
              <CategoryForm
                key={category.updated_at ?? category.id}
                initial={category}
                busy={save.isPending || remove.isPending}
                onSave={(body) => save.mutate({ id: category.id, body })}
                onDelete={() => {
                  if (
                    window.confirm(
                      "未发布且未被任务引用的分类会被删除；其他分类会归档。是否继续？",
                    )
                  ) {
                    remove.mutate(category.id)
                  }
                }}
              />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
