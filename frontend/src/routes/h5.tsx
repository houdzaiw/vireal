import { createFileRoute } from "@tanstack/react-router"
import {
  AlertCircle,
  BadgeCheck,
  Camera,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Download,
  Film,
  ImageIcon,
  Loader2,
  LockKeyhole,
  Palette,
  RefreshCw,
  Send,
  Settings2,
  Share2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  UserRound,
  WandSparkles,
  Zap,
} from "lucide-react"
import {
  type ChangeEvent,
  type ComponentType,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
  type SVGProps,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react"
import { toast } from "sonner"

import {
  AppAuthService,
  AppConfigsService,
  AppContentsService,
  type AppGenerationPublic,
  AppGenerationsService,
  AppUploadsService,
  type AppUserPublic,
} from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/h5")({
  component: H5AiGenerator,
  head: () => ({
    meta: [
      {
        title: "Vireal AI 创作",
      },
    ],
  }),
})

type CreativeTab = "video" | "image" | "works"
type GenerationKind = "video" | "image"
type LoginProvider = "apple" | "google"
type WorkStatus = "processing" | "done" | "failed"

interface GenerationDraft {
  prompt: string
  style: string
  aspectRatio: string
  durationSeconds: number
  consistency: boolean
  referenceFile: File | null
  referencePreviewUrl: string
  characterFile: File | null
  characterPreviewUrl: string
}

interface WorkItem {
  id: string
  kind: GenerationKind
  model: string
  status: WorkStatus
  prompt: string
  style: string
  aspectRatio: string
  durationSeconds?: number
  consistency: boolean
  createdAt: string
  outputUrl?: string
  previewUrl?: string
  uploadedImageUrls: string[]
}

interface FreeQuota {
  video: number
  image: number
}

interface StoredSession {
  token: string
  user: AppUserPublic
  provider: LoginProvider
}

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>

const APP_TOKEN_KEY = "vireal_h5_app_token"
const APP_USER_KEY = "vireal_h5_app_user"
const APP_PROVIDER_KEY = "vireal_h5_login_provider"
const DEVICE_UUID_KEY = "vireal_h5_device_uuid"

const defaultQuota: FreeQuota = {
  video: 2,
  image: 2,
}

const defaultVideoDraft: GenerationDraft = {
  prompt: "",
  style: "写实",
  aspectRatio: "9:16",
  durationSeconds: 5,
  consistency: true,
  referenceFile: null,
  referencePreviewUrl: "",
  characterFile: null,
  characterPreviewUrl: "",
}

const defaultImageDraft: GenerationDraft = {
  prompt: "",
  style: "写实",
  aspectRatio: "1:1",
  durationSeconds: 0,
  consistency: true,
  referenceFile: null,
  referencePreviewUrl: "",
  characterFile: null,
  characterPreviewUrl: "",
}

const videoTemplates = [
  "把参考图里的角色变成写实电影感短片，镜头轻微推进，情绪自然，有社交头像氛围。",
  "人物站在城市夜景前微笑转身，光线柔和，画面干净，适合朋友圈分享。",
  "生成一段浪漫约会感视频，人物保持一致，动作自然，背景有温暖灯光。",
]

const imageTemplates = [
  "写实社交头像，干净背景，五官自然，光线柔和，适合头像使用。",
  "电影感半身照，人物一致，浅景深，高级但自然。",
  "明亮日常自拍风，真实皮肤质感，表情轻松。",
]

function readJson<T>(key: string, fallback: T): T {
  try {
    const rawValue = localStorage.getItem(key)
    return rawValue ? (JSON.parse(rawValue) as T) : fallback
  } catch {
    return fallback
  }
}

function writeJson<T>(key: string, value: T) {
  localStorage.setItem(key, JSON.stringify(value))
}

function createId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
}

function getOrCreateDeviceUuid(provider: LoginProvider) {
  const storageKey = `${DEVICE_UUID_KEY}_${provider}`
  const existing = localStorage.getItem(storageKey)
  if (existing) return existing
  const nextValue = createId()
  localStorage.setItem(storageKey, nextValue)
  return nextValue
}

function getMediaUrl(url?: string | null) {
  if (!url) return ""
  if (url.startsWith("http://") || url.startsWith("https://")) return url
  const baseUrl = import.meta.env.VITE_API_URL ?? ""
  return `${baseUrl}${url}`
}

function readStoredSession(): StoredSession | null {
  const token = localStorage.getItem(APP_TOKEN_KEY)
  const user = readJson<AppUserPublic | null>(APP_USER_KEY, null)
  const provider =
    (localStorage.getItem(APP_PROVIDER_KEY) as LoginProvider | null) ?? "apple"
  if (!token || !user) return null
  return { token, user, provider }
}

function saveSession(session: StoredSession) {
  localStorage.setItem(APP_TOKEN_KEY, session.token)
  localStorage.setItem(APP_PROVIDER_KEY, session.provider)
  writeJson(APP_USER_KEY, session.user)
}

function clearSession() {
  localStorage.removeItem(APP_TOKEN_KEY)
  localStorage.removeItem(APP_PROVIDER_KEY)
  localStorage.removeItem(APP_USER_KEY)
}

function fileToPreviewUrl(file: File) {
  return URL.createObjectURL(file)
}

function tabLabel(tab: CreativeTab) {
  if (tab === "video") return "AI 视频"
  if (tab === "image") return "AI 图片"
  return "作品"
}

function kindLabel(kind: GenerationKind) {
  return kind === "video" ? "视频" : "图片"
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}

function isQuotaEnough(quota: FreeQuota, kind: GenerationKind) {
  return quota[kind] > 0
}

function generationStatus(status: string): WorkStatus {
  if (status === "succeeded") return "done"
  if (status === "failed") return "failed"
  return "processing"
}

function generationKind(kind: string): GenerationKind {
  return kind === "image" ? "image" : "video"
}

function generationToWork(generation: AppGenerationPublic): WorkItem {
  const imageUrl =
    generation.output_url ||
    generation.reference_image_url ||
    generation.character_image_url ||
    undefined

  return {
    id: generation.id,
    kind: generationKind(generation.kind),
    model: generation.model,
    status: generationStatus(generation.status),
    prompt: generation.prompt,
    style: generation.style,
    aspectRatio: generation.aspect_ratio,
    durationSeconds: generation.duration_seconds ?? undefined,
    consistency: generation.consistency,
    createdAt: generation.created_at ?? new Date().toISOString(),
    outputUrl: imageUrl ? getMediaUrl(imageUrl) : undefined,
    previewUrl: imageUrl ? getMediaUrl(imageUrl) : undefined,
    uploadedImageUrls: [
      generation.reference_image_url,
      generation.character_image_url,
    ].filter(Boolean) as string[],
  }
}

function getErrorDetail(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    .response?.data?.detail
  return typeof detail === "string" ? detail : null
}

function H5AiGenerator() {
  const [activeTab, setActiveTab] = useState<CreativeTab>("video")
  const [videoDraft, setVideoDraft] =
    useState<GenerationDraft>(defaultVideoDraft)
  const [imageDraft, setImageDraft] =
    useState<GenerationDraft>(defaultImageDraft)
  const [works, setWorks] = useState<WorkItem[]>([])
  const [quota, setQuota] = useState<FreeQuota>(defaultQuota)
  const [session, setSession] = useState<StoredSession | null>(
    readStoredSession,
  )
  const [loginOpen, setLoginOpen] = useState(false)
  const [loginLoading, setLoginLoading] = useState<LoginProvider | null>(null)
  const [pendingGenerateKind, setPendingGenerateKind] =
    useState<GenerationKind | null>(null)
  const [isGenerating, setIsGenerating] = useState<GenerationKind | null>(null)
  const [configStatus, setConfigStatus] = useState("默认配置")
  const sessionToken = session?.token

  const refreshAppState = useCallback(async (token: string) => {
    try {
      const [
        profileResponse,
        configResponse,
        quotaResponse,
        generationsResponse,
      ] = await Promise.all([
        AppAuthService.testAppToken({ auth: () => token }),
        AppConfigsService.readAppConfigs({ auth: () => token }),
        AppGenerationsService.readGenerationQuota({ auth: () => token }),
        AppGenerationsService.readGenerations({
          auth: () => token,
          query: { skip: 0, limit: 100 },
        }),
      ])
      setSession((current) => {
        if (!current) return current
        const nextSession = {
          ...current,
          user: profileResponse.data,
        }
        saveSession(nextSession)
        return nextSession
      })
      setConfigStatus(`配置 ${configResponse.data.count}`)
      setQuota({
        video: quotaResponse.data.video_remaining,
        image: quotaResponse.data.image_remaining,
      })
      setWorks(generationsResponse.data.data.map(generationToWork))
    } catch {
      clearSession()
      setSession(null)
      setConfigStatus("默认配置")
      setQuota(defaultQuota)
      setWorks([])
    }
  }, [])

  useEffect(() => {
    if (!sessionToken) {
      setQuota(defaultQuota)
      setWorks([])
      return
    }
    void refreshAppState(sessionToken)
  }, [sessionToken, refreshAppState])

  const currentDraft = activeTab === "image" ? imageDraft : videoDraft
  const setCurrentDraft = activeTab === "image" ? setImageDraft : setVideoDraft
  const doneWorks = works.filter((work) => work.status === "done").length
  const processingWorks = works.filter(
    (work) => work.status === "processing",
  ).length
  const hasProcessingWorks = processingWorks > 0

  useEffect(() => {
    if (!sessionToken || !hasProcessingWorks) return

    const timer = window.setInterval(() => {
      void refreshAppState(sessionToken)
    }, 2500)

    return () => window.clearInterval(timer)
  }, [hasProcessingWorks, refreshAppState, sessionToken])

  async function loginWithProvider(provider: LoginProvider) {
    if (loginLoading) return
    setLoginLoading(provider)
    try {
      const response = await AppAuthService.deviceLogin({
        body: {
          device_uuid: getOrCreateDeviceUuid(provider),
          platform: provider === "apple" ? "ios" : "android",
        },
      })
      const nextSession: StoredSession = {
        token: response.data.access_token,
        user: response.data.app_user,
        provider,
      }
      saveSession(nextSession)
      setSession(nextSession)
      setLoginOpen(false)
      toast.success("登录成功")

      if (pendingGenerateKind) {
        const targetKind = pendingGenerateKind
        setPendingGenerateKind(null)
        await generateWork(targetKind, response.data.access_token)
      }
    } catch {
      toast.error("登录失败，请稍后重试")
    } finally {
      setLoginLoading(null)
    }
  }

  function requireLoginForGenerate(kind: GenerationKind) {
    setPendingGenerateKind(kind)
    setLoginOpen(true)
  }

  async function uploadDraftImages(draft: GenerationDraft, token: string) {
    const files = [draft.referenceFile, draft.characterFile].filter(
      Boolean,
    ) as File[]
    if (!files.length) return []
    const uploadedUrls: string[] = []

    for (const file of files) {
      const response = await AppUploadsService.uploadAppImage({
        auth: () => token,
        body: { file },
      })
      uploadedUrls.push(response.data.url)
    }

    return uploadedUrls
  }

  async function publishWorkAsContent(
    work: WorkItem,
    token: string,
    uploadedImageUrls: string[],
  ) {
    try {
      await AppContentsService.createContent({
        auth: () => token,
        body: {
          text: `${kindLabel(work.kind)}生成：${work.prompt}`,
          image_urls: uploadedImageUrls,
        },
      })
    } catch {
      toast.warning("作品已生成，本次动态同步失败")
    }
  }

  async function generateWork(kind: GenerationKind, tokenOverride?: string) {
    const token = tokenOverride ?? sessionToken
    if (!token) {
      requireLoginForGenerate(kind)
      return
    }
    if (!isQuotaEnough(quota, kind)) {
      toast.error(`${kindLabel(kind)}免费次数已用完`)
      return
    }

    const draft = kind === "video" ? videoDraft : imageDraft
    const prompt = draft.prompt.trim()
    if (!prompt) {
      toast.error("请输入生成描述")
      setActiveTab(kind)
      return
    }

    setIsGenerating(kind)
    try {
      const uploadedImageUrls = await uploadDraftImages(draft, token)
      const generationResponse = await AppGenerationsService.createGeneration({
        auth: () => token,
        body: {
          kind,
          prompt,
          style: draft.style,
          aspect_ratio: draft.aspectRatio,
          duration_seconds: kind === "video" ? draft.durationSeconds : null,
          consistency: draft.consistency,
          reference_image_url: uploadedImageUrls[0] ?? null,
          character_image_url: uploadedImageUrls[1] ?? null,
        },
      })
      const nextWork = generationToWork(generationResponse.data)

      setWorks((currentWorks) => [
        nextWork,
        ...currentWorks.filter((work) => work.id !== nextWork.id),
      ])
      setActiveTab("works")
      void publishWorkAsContent(nextWork, token, uploadedImageUrls)
      void refreshAppState(token)
    } catch (error) {
      const detail = getErrorDetail(error)
      if (detail === "Free generation quota exhausted") {
        toast.error(`${kindLabel(kind)}免费次数已用完`)
        void refreshAppState(token)
      } else {
        toast.error("生成提交失败，本次不扣次数")
      }
    } finally {
      setIsGenerating(null)
    }
  }

  function handleGenerate(kind: GenerationKind) {
    if (!sessionToken) {
      requireLoginForGenerate(kind)
      return
    }
    void generateWork(kind)
  }

  async function handleDeleteWork(workId: string) {
    if (!sessionToken) {
      setWorks((currentWorks) =>
        currentWorks.filter((work) => work.id !== workId),
      )
      toast.success("作品已删除")
      return
    }

    try {
      await AppGenerationsService.deleteGeneration({
        auth: () => sessionToken,
        path: { generation_id: workId },
      })
      setWorks((currentWorks) =>
        currentWorks.filter((work) => work.id !== workId),
      )
      toast.success("作品已删除")
    } catch {
      toast.error("删除失败，请稍后重试")
    }
  }

  async function handleShareWork(work: WorkItem) {
    const shareText = `Vireal ${kindLabel(work.kind)}作品：${work.prompt}`
    if (navigator.share) {
      await navigator.share({
        title: "Vireal AI 创作",
        text: shareText,
        url: window.location.href,
      })
      return
    }
    await navigator.clipboard.writeText(shareText)
    toast.success("分享文案已复制")
  }

  function handleDownloadWork(work: WorkItem) {
    const anchor = document.createElement("a")
    if (work.outputUrl) {
      anchor.href = work.outputUrl
      anchor.download = `vireal-${work.kind}-${work.id}`
    } else {
      const blob = new Blob(
        [
          `Vireal ${work.model}\n类型：${kindLabel(work.kind)}\n描述：${
            work.prompt
          }\n风格：${work.style}\n比例：${work.aspectRatio}`,
        ],
        { type: "text/plain;charset=utf-8" },
      )
      anchor.href = URL.createObjectURL(blob)
      anchor.download = `vireal-${work.kind}-${work.id}.txt`
    }
    document.body.append(anchor)
    anchor.click()
    anchor.remove()
  }

  function handleRegenerate(work: WorkItem) {
    const targetDraft: GenerationDraft = {
      ...(work.kind === "video" ? defaultVideoDraft : defaultImageDraft),
      prompt: work.prompt,
      style: work.style,
      aspectRatio: work.aspectRatio,
      durationSeconds: work.durationSeconds ?? 5,
      consistency: work.consistency,
    }
    if (work.kind === "video") {
      setVideoDraft(targetDraft)
    } else {
      setImageDraft(targetDraft)
    }
    setActiveTab(work.kind)
    toast.success("已带入上次参数")
  }

  function handleLogout() {
    clearSession()
    setSession(null)
    setConfigStatus("默认配置")
    setQuota(defaultQuota)
    setWorks([])
    toast.success("已退出登录")
  }

  const visibleTemplates =
    activeTab === "image" ? imageTemplates : videoTemplates

  return (
    <div className="min-h-svh bg-[#090b0a] text-stone-50">
      <div className="mx-auto flex min-h-svh w-full max-w-[430px] flex-col border-x border-white/10 bg-[#0b100f]">
        <H5Header
          activeTab={activeTab}
          configStatus={configStatus}
          doneWorks={doneWorks}
          onLogout={handleLogout}
          processingWorks={processingWorks}
          quota={quota}
          session={session}
        />

        <main className="flex-1 overflow-y-auto pb-24">
          {activeTab === "video" || activeTab === "image" ? (
            <GeneratorPanel
              draft={currentDraft}
              isGenerating={isGenerating === activeTab}
              kind={activeTab}
              onGenerate={() => handleGenerate(activeTab)}
              onPickTemplate={(prompt) =>
                setCurrentDraft((current) => ({ ...current, prompt }))
              }
              quota={quota[activeTab]}
              setDraft={setCurrentDraft}
              templates={visibleTemplates}
            />
          ) : (
            <WorksPanel
              onDelete={handleDeleteWork}
              onDownload={handleDownloadWork}
              onRegenerate={handleRegenerate}
              onShare={(work) => void handleShareWork(work)}
              onStartCreate={(kind) => setActiveTab(kind)}
              works={works}
            />
          )}
        </main>

        <BottomTabs activeTab={activeTab} setActiveTab={setActiveTab} />
      </div>

      <LoginDialog
        loadingProvider={loginLoading}
        onLogin={loginWithProvider}
        onOpenChange={(open) => {
          setLoginOpen(open)
          if (!open) setPendingGenerateKind(null)
        }}
        open={loginOpen}
        pendingKind={pendingGenerateKind}
      />
    </div>
  )
}

function H5Header({
  activeTab,
  configStatus,
  doneWorks,
  onLogout,
  processingWorks,
  quota,
  session,
}: {
  activeTab: CreativeTab
  configStatus: string
  doneWorks: number
  onLogout: () => void
  processingWorks: number
  quota: FreeQuota
  session: StoredSession | null
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-[#0b100f]/95 px-5 py-4 backdrop-blur">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs font-semibold text-cyan-200">
            <Sparkles className="size-3.5" />
            <span>Vireal AI</span>
          </div>
          <h1 className="mt-1 truncate text-xl font-semibold leading-tight">
            {tabLabel(activeTab)}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex h-10 items-center gap-2 rounded-[8px] border border-cyan-200/40 px-3 text-cyan-100">
            <span className="font-semibold">{quota.video + quota.image}</span>
            <Zap className="size-4" />
          </div>
          <button
            aria-label="设置"
            className="grid size-10 place-items-center rounded-[8px] border border-white/15 text-stone-300"
            type="button"
          >
            <Settings2 className="size-4" />
          </button>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
        <HeaderMetric
          icon={ShieldCheck}
          label={session ? session.provider : "未登录"}
          value={session ? "已登录" : "待生成"}
        />
        <HeaderMetric icon={BadgeCheck} label={configStatus} value="启动配置" />
        <HeaderMetric
          icon={Clock3}
          label={`${processingWorks} 进行中`}
          value={`${doneWorks} 完成`}
        />
      </div>

      {session ? (
        <button
          className="mt-3 text-xs text-stone-400 underline-offset-4 hover:text-stone-100 hover:underline"
          onClick={onLogout}
          type="button"
        >
          {session.user.nickname || "匿名用户"}，退出登录
        </button>
      ) : null}
    </header>
  )
}

function HeaderMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: IconComponent
  label: string
  value: string
}) {
  return (
    <div className="rounded-[8px] border border-white/10 bg-white/[0.04] p-2">
      <div className="flex items-center gap-1.5 text-stone-400">
        <Icon className="size-3.5" />
        <span className="truncate">{label}</span>
      </div>
      <div className="mt-1 truncate font-semibold text-stone-50">{value}</div>
    </div>
  )
}

function GeneratorPanel({
  draft,
  isGenerating,
  kind,
  onGenerate,
  onPickTemplate,
  quota,
  setDraft,
  templates,
}: {
  draft: GenerationDraft
  isGenerating: boolean
  kind: GenerationKind
  onGenerate: () => void
  onPickTemplate: (prompt: string) => void
  quota: number
  setDraft: Dispatch<SetStateAction<GenerationDraft>>
  templates: string[]
}) {
  const isVideo = kind === "video"
  const modelName = isVideo ? "Seedance 2.0" : "Seedream"

  return (
    <section className="px-5 py-5">
      <div className="rounded-[8px] border border-white/10 bg-[#151a18] shadow-2xl shadow-black/30">
        <div className="border-b border-white/10 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold text-cyan-200">{modelName}</p>
              <h2 className="mt-1 text-lg font-semibold">
                {isVideo ? "暗色能量创作台" : "头像图片创作台"}
              </h2>
            </div>
            <div className="flex items-center gap-1.5 rounded-[8px] bg-cyan-300 px-3 py-1.5 text-sm font-semibold text-black">
              <span>{quota}</span>
              <Zap className="size-4" />
            </div>
          </div>
        </div>

        <div className="space-y-5 p-4">
          <div className="grid grid-cols-2 gap-3">
            <UploadSlot
              fileName={draft.referenceFile?.name}
              icon={Camera}
              label="参考图"
              onChange={(file) =>
                setDraft((current) => ({
                  ...current,
                  referenceFile: file,
                  referencePreviewUrl: file ? fileToPreviewUrl(file) : "",
                }))
              }
              previewUrl={draft.referencePreviewUrl}
            />
            <UploadSlot
              fileName={draft.characterFile?.name}
              icon={UserRound}
              label={isVideo ? "角色图" : "人物图"}
              onChange={(file) =>
                setDraft((current) => ({
                  ...current,
                  characterFile: file,
                  characterPreviewUrl: file ? fileToPreviewUrl(file) : "",
                }))
              }
              previewUrl={draft.characterPreviewUrl}
            />
          </div>

          <label className="block">
            <span className="mb-2 flex items-center gap-2 text-sm font-semibold text-stone-200">
              <WandSparkles className="size-4 text-cyan-200" />
              创意描述
            </span>
            <textarea
              className="min-h-36 w-full resize-none rounded-[8px] border border-white/10 bg-[#0e1312] p-4 text-base leading-7 text-stone-50 outline-none placeholder:text-stone-600 focus:border-cyan-200/60 focus:ring-2 focus:ring-cyan-200/15"
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  prompt: event.target.value,
                }))
              }
              placeholder="描述你的创意..."
              value={draft.prompt}
            />
          </label>

          <div className="space-y-4">
            <ControlGroup icon={SlidersHorizontal} label="比例">
              {["9:16", "1:1", "3:4", "16:9"].map((ratio) => (
                <ChoiceButton
                  active={draft.aspectRatio === ratio}
                  key={ratio}
                  onClick={() =>
                    setDraft((current) => ({
                      ...current,
                      aspectRatio: ratio,
                    }))
                  }
                >
                  {ratio}
                </ChoiceButton>
              ))}
            </ControlGroup>

            <ControlGroup icon={Palette} label="风格">
              {["写实", "电影", "自拍", "潮流"].map((style) => (
                <ChoiceButton
                  active={draft.style === style}
                  key={style}
                  onClick={() =>
                    setDraft((current) => ({
                      ...current,
                      style,
                    }))
                  }
                >
                  {style}
                </ChoiceButton>
              ))}
            </ControlGroup>

            <ControlGroup icon={LockKeyhole} label="一致性">
              <ChoiceButton
                active={draft.consistency}
                onClick={() =>
                  setDraft((current) => ({
                    ...current,
                    consistency: !current.consistency,
                  }))
                }
              >
                {draft.consistency ? "开启" : "关闭"}
              </ChoiceButton>
            </ControlGroup>

            {isVideo ? (
              <ControlGroup icon={Film} label="时长">
                {[5, 10, 15].map((duration) => (
                  <ChoiceButton
                    active={draft.durationSeconds === duration}
                    key={duration}
                    onClick={() =>
                      setDraft((current) => ({
                        ...current,
                        durationSeconds: duration,
                      }))
                    }
                  >
                    {duration} 秒
                  </ChoiceButton>
                ))}
              </ControlGroup>
            ) : null}
          </div>

          <Button
            className="h-13 w-full rounded-[8px] bg-cyan-300 text-base font-semibold text-black hover:bg-cyan-200 disabled:bg-white/15 disabled:text-stone-400"
            disabled={isGenerating}
            onClick={onGenerate}
            type="button"
          >
            {isGenerating ? (
              <Loader2 className="size-5 animate-spin" />
            ) : (
              <Sparkles className="size-5" />
            )}
            生成
            <span className="ml-1 inline-flex items-center gap-1 text-black/70">
              {quota > 0 ? "免费" : "已用完"}
              <ChevronRight className="size-4" />
            </span>
          </Button>
        </div>
      </div>

      <div className="mt-6 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold">
            {isVideo ? "浪漫时刻" : "头像灵感"}
          </h3>
          <span className="text-xs text-stone-500">{modelName}</span>
        </div>
        <div className="-mx-5 flex gap-3 overflow-x-auto px-5 pb-1">
          {templates.map((template, index) => (
            <button
              className="min-h-28 w-44 shrink-0 rounded-[8px] border border-white/10 bg-white/[0.05] p-3 text-left transition hover:border-cyan-200/50"
              key={template}
              onClick={() => onPickTemplate(template)}
              type="button"
            >
              <div
                className={cn(
                  "mb-3 grid h-11 w-11 place-items-center rounded-[8px]",
                  index === 0 && "bg-cyan-300 text-black",
                  index === 1 && "bg-amber-300 text-black",
                  index === 2 && "bg-rose-300 text-black",
                )}
              >
                {isVideo ? (
                  <Film className="size-5" />
                ) : (
                  <ImageIcon className="size-5" />
                )}
              </div>
              <p className="line-clamp-3 text-sm leading-5 text-stone-200">
                {template}
              </p>
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}

function UploadSlot({
  fileName,
  icon: Icon,
  label,
  onChange,
  previewUrl,
}: {
  fileName?: string
  icon: IconComponent
  label: string
  onChange: (file: File | null) => void
  previewUrl: string
}) {
  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    onChange(event.target.files?.[0] ?? null)
  }

  return (
    <label className="group relative flex aspect-square cursor-pointer flex-col items-center justify-center overflow-hidden rounded-[8px] border border-dashed border-white/20 bg-[#0e1312] text-center transition hover:border-cyan-200/60">
      <input
        accept="image/*"
        className="sr-only"
        onChange={handleFileChange}
        type="file"
      />
      {previewUrl ? (
        <img
          alt=""
          className="absolute inset-0 size-full object-cover"
          src={previewUrl}
        />
      ) : null}
      <div className="relative z-10 grid place-items-center gap-2 rounded-[8px] bg-black/35 px-3 py-2 backdrop-blur-sm">
        {previewUrl ? (
          <CheckCircle2 className="size-6 text-cyan-200" />
        ) : (
          <Icon className="size-7 text-stone-300" />
        )}
        <span className="text-sm font-semibold">{label}</span>
        <span className="max-w-28 truncate text-xs text-stone-400">
          {fileName || "普通上传"}
        </span>
      </div>
    </label>
  )
}

function ControlGroup({
  children,
  icon: Icon,
  label,
}: {
  children: ReactNode
  icon: IconComponent
  label: string
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-stone-200">
        <Icon className="size-4 text-stone-400" />
        <span>{label}</span>
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  )
}

function ChoiceButton({
  active,
  children,
  onClick,
}: {
  active: boolean
  children: ReactNode
  onClick: () => void
}) {
  return (
    <button
      className={cn(
        "min-h-10 rounded-[8px] border px-4 text-sm font-semibold transition",
        active
          ? "border-cyan-200 bg-cyan-300 text-black"
          : "border-white/15 bg-white/[0.04] text-stone-300",
      )}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  )
}

function WorksPanel({
  onDelete,
  onDownload,
  onRegenerate,
  onShare,
  onStartCreate,
  works,
}: {
  onDelete: (workId: string) => void
  onDownload: (work: WorkItem) => void
  onRegenerate: (work: WorkItem) => void
  onShare: (work: WorkItem) => void
  onStartCreate: (kind: GenerationKind) => void
  works: WorkItem[]
}) {
  const empty = works.length === 0

  return (
    <section className="px-5 py-5">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">作品</h2>
          <p className="text-sm text-stone-400">下载、分享、删除、再次生成</p>
        </div>
        <div className="flex gap-2">
          <Button
            className="rounded-[8px]"
            onClick={() => onStartCreate("video")}
            size="sm"
            type="button"
          >
            <Film className="size-4" />
            视频
          </Button>
          <Button
            className="rounded-[8px]"
            onClick={() => onStartCreate("image")}
            size="sm"
            type="button"
            variant="secondary"
          >
            <ImageIcon className="size-4" />
            图片
          </Button>
        </div>
      </div>

      {empty ? (
        <div className="grid min-h-80 place-items-center rounded-[8px] border border-white/10 bg-white/[0.04] p-8 text-center">
          <div>
            <div className="mx-auto grid size-16 place-items-center rounded-[8px] bg-amber-300 text-black">
              <Sparkles className="size-7" />
            </div>
            <h3 className="mt-4 text-lg font-semibold">暂无作品</h3>
            <p className="mt-2 text-sm leading-6 text-stone-400">
              从 AI 视频或 AI 图片开始生成，完成后会自动进入这里。
            </p>
            <Button
              className="mt-5 rounded-[8px] bg-cyan-300 text-black hover:bg-cyan-200"
              onClick={() => onStartCreate("video")}
              type="button"
            >
              <Film className="size-4" />
              去生成视频
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {works.map((work) => (
            <WorkCard
              key={work.id}
              onDelete={onDelete}
              onDownload={onDownload}
              onRegenerate={onRegenerate}
              onShare={onShare}
              work={work}
            />
          ))}
        </div>
      )}
    </section>
  )
}

function WorkCard({
  onDelete,
  onDownload,
  onRegenerate,
  onShare,
  work,
}: {
  onDelete: (workId: string) => void
  onDownload: (work: WorkItem) => void
  onRegenerate: (work: WorkItem) => void
  onShare: (work: WorkItem) => void
  work: WorkItem
}) {
  const Icon = work.kind === "video" ? Film : ImageIcon
  const statusText =
    work.status === "processing"
      ? "生成中"
      : work.status === "failed"
        ? "失败"
        : "已完成"

  return (
    <article className="overflow-hidden rounded-[8px] border border-white/10 bg-[#151a18]">
      <div className="relative aspect-[4/5] bg-[#0e1312]">
        {work.previewUrl ? (
          <img
            alt=""
            className="absolute inset-0 size-full object-cover opacity-85"
            src={work.previewUrl}
          />
        ) : (
          <div className="absolute inset-0 grid place-items-center bg-[linear-gradient(135deg,#17211f,#2b2a1b,#271a22)]">
            <Icon className="size-16 text-white/75" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-black/20" />
        <div className="absolute left-3 top-3 flex items-center gap-2 rounded-[8px] bg-black/55 px-3 py-1.5 text-xs font-semibold backdrop-blur-sm">
          {work.status === "processing" ? (
            <Loader2 className="size-3.5 animate-spin text-cyan-200" />
          ) : work.status === "failed" ? (
            <AlertCircle className="size-3.5 text-rose-200" />
          ) : (
            <CheckCircle2 className="size-3.5 text-cyan-200" />
          )}
          {statusText}
        </div>
        <div className="absolute bottom-3 left-3 right-3">
          <div className="flex items-center gap-2 text-xs text-stone-300">
            <Icon className="size-3.5" />
            <span>{work.model}</span>
            <span>{formatTime(work.createdAt)}</span>
          </div>
          <h3 className="mt-2 line-clamp-2 text-base font-semibold leading-6">
            {work.prompt}
          </h3>
        </div>
      </div>

      <div className="space-y-4 p-4">
        <div className="grid grid-cols-3 gap-2 text-xs">
          <WorkMeta label="比例" value={work.aspectRatio} />
          <WorkMeta label="风格" value={work.style} />
          <WorkMeta
            label={work.kind === "video" ? "时长" : "一致性"}
            value={
              work.kind === "video"
                ? `${work.durationSeconds ?? 5} 秒`
                : work.consistency
                  ? "开启"
                  : "关闭"
            }
          />
        </div>

        {work.status === "failed" ? (
          <div className="flex items-center gap-2 rounded-[8px] border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
            <AlertCircle className="size-4" />
            本次生成失败，额度已返还。
          </div>
        ) : null}

        <div className="grid grid-cols-4 gap-2">
          <IconButton
            disabled={work.status !== "done"}
            icon={Download}
            label="下载"
            onClick={() => onDownload(work)}
          />
          <IconButton
            disabled={work.status !== "done"}
            icon={Share2}
            label="分享"
            onClick={() => onShare(work)}
          />
          <IconButton
            icon={Trash2}
            label="删除"
            onClick={() => onDelete(work.id)}
          />
          <IconButton
            icon={RefreshCw}
            label="再生成"
            onClick={() => onRegenerate(work)}
          />
        </div>
      </div>
    </article>
  )
}

function WorkMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] border border-white/10 bg-white/[0.04] p-2">
      <div className="text-stone-500">{label}</div>
      <div className="mt-1 truncate font-semibold text-stone-100">{value}</div>
    </div>
  )
}

function IconButton({
  disabled,
  icon: Icon,
  label,
  onClick,
}: {
  disabled?: boolean
  icon: IconComponent
  label: string
  onClick: () => void
}) {
  return (
    <button
      className="flex min-h-14 flex-col items-center justify-center gap-1 rounded-[8px] border border-white/10 bg-white/[0.04] text-xs text-stone-200 transition hover:border-cyan-200/50 disabled:opacity-40"
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      <Icon className="size-4" />
      <span>{label}</span>
    </button>
  )
}

function BottomTabs({
  activeTab,
  setActiveTab,
}: {
  activeTab: CreativeTab
  setActiveTab: (tab: CreativeTab) => void
}) {
  const tabs = useMemo(
    () =>
      [
        { icon: Film, label: "AI 视频", value: "video" },
        { icon: ImageIcon, label: "AI 图片", value: "image" },
        { icon: Send, label: "作品", value: "works" },
      ] satisfies Array<{
        icon: IconComponent
        label: string
        value: CreativeTab
      }>,
    [],
  )

  return (
    <nav className="fixed bottom-0 left-1/2 z-30 w-full max-w-[430px] -translate-x-1/2 border-t border-white/10 bg-[#111614]/95 px-5 pb-[max(env(safe-area-inset-bottom),16px)] pt-3 backdrop-blur">
      <div className="grid grid-cols-3 gap-2">
        {tabs.map(({ icon: Icon, label, value }) => {
          const active = activeTab === value
          return (
            <button
              className={cn(
                "flex min-h-13 items-center justify-center gap-2 rounded-[8px] text-sm font-semibold transition",
                active
                  ? "bg-cyan-300 text-black"
                  : "bg-white/[0.04] text-stone-400",
              )}
              key={value}
              onClick={() => setActiveTab(value)}
              type="button"
            >
              <Icon className="size-4" />
              <span>{label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}

function LoginDialog({
  loadingProvider,
  onLogin,
  onOpenChange,
  open,
  pendingKind,
}: {
  loadingProvider: LoginProvider | null
  onLogin: (provider: LoginProvider) => Promise<void>
  onOpenChange: (open: boolean) => void
  open: boolean
  pendingKind: GenerationKind | null
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-auto bottom-24 z-[100] max-w-[360px] translate-y-0 rounded-[8px] border-cyan-200/30 bg-[#f8faf9] p-5 text-[#0b100f] shadow-2xl shadow-black/80">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <LockKeyhole className="size-5 text-cyan-200" />
            登录后生成
          </DialogTitle>
          <DialogDescription className="text-stone-600">
            {pendingKind
              ? `${kindLabel(pendingKind)}生成会使用对应免费次数。`
              : "登录账号后继续创作。"}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          <LoginButton
            icon={ShieldCheck}
            label="使用 Apple 登录"
            loading={loadingProvider === "apple"}
            onClick={() => void onLogin("apple")}
          />
          <LoginButton
            icon={Sparkles}
            label="使用 Google 登录"
            loading={loadingProvider === "google"}
            onClick={() => void onLogin("google")}
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}

function LoginButton({
  icon: Icon,
  label,
  loading,
  onClick,
}: {
  icon: IconComponent
  label: string
  loading: boolean
  onClick: () => void
}) {
  return (
    <button
      className="flex h-12 items-center justify-center gap-3 rounded-[8px] border border-white/10 bg-white text-sm font-semibold text-black transition hover:bg-stone-100 disabled:opacity-70"
      disabled={loading}
      onClick={onClick}
      type="button"
    >
      {loading ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <Icon className="size-4" />
      )}
      {label}
    </button>
  )
}
