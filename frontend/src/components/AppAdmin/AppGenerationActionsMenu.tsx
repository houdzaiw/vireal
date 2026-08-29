import { EllipsisVertical, Trash2 } from "lucide-react"
import { useState } from "react"

import { AdminAppService, type AppGenerationAdminPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmMenuAction } from "./ConfirmMenuAction"

interface AppGenerationActionsMenuProps {
  generation: AppGenerationAdminPublic
}

export function AppGenerationActionsMenu({
  generation,
}: AppGenerationActionsMenuProps) {
  const [open, setOpen] = useState(false)

  if (generation.status === "deleted") {
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
          label="Delete Generation"
          title="Delete App Generation"
          description="This soft deletes the AI work. It will no longer appear in the user's works list."
          confirmLabel="Delete"
          successMessage="Generation deleted successfully"
          queryKey="admin-app-generations"
          variant="destructive"
          onSuccess={() => setOpen(false)}
          mutationFn={() =>
            AdminAppService.deleteAppGeneration({
              path: { generation_id: generation.id },
            })
          }
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
