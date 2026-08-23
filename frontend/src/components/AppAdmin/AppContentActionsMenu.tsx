import { EllipsisVertical, Trash2 } from "lucide-react"
import { useState } from "react"

import { AdminAppService, type AppContentAdminPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmMenuAction } from "./ConfirmMenuAction"

interface AppContentActionsMenuProps {
  content: AppContentAdminPublic
}

export function AppContentActionsMenu({ content }: AppContentActionsMenuProps) {
  const [open, setOpen] = useState(false)

  if (content.status === "deleted") {
    return null
  }

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon">
          <EllipsisVertical />
          <span className="sr-only">Open actions</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <ConfirmMenuAction
          icon={Trash2}
          label="Delete Content"
          title="Delete App Content"
          description="This soft deletes the content. It will no longer appear in the App feed."
          confirmLabel="Delete"
          successMessage="Content deleted successfully"
          queryKey="admin-app-contents"
          variant="destructive"
          onSuccess={() => setOpen(false)}
          mutationFn={() =>
            AdminAppService.deleteAppContent({
              path: { content_id: content.id },
            })
          }
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
