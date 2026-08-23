import { EllipsisVertical, ShieldBan, ShieldCheck, Trash2 } from "lucide-react"
import { useState } from "react"

import { AdminAppService, type AppUserAdminPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmMenuAction } from "./ConfirmMenuAction"

interface AppUserActionsMenuProps {
  user: AppUserAdminPublic
}

export function AppUserActionsMenu({ user }: AppUserActionsMenuProps) {
  const [open, setOpen] = useState(false)
  const isDisabled = user.status === "disabled"
  const nextStatus = isDisabled ? "active" : "disabled"

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
          icon={isDisabled ? ShieldCheck : ShieldBan}
          label={isDisabled ? "Enable User" : "Disable User"}
          title={isDisabled ? "Enable App User" : "Disable App User"}
          description={
            isDisabled
              ? "This user will be able to use App APIs again."
              : "This user will be blocked from App APIs and their content will be hidden from App feeds."
          }
          confirmLabel={isDisabled ? "Enable" : "Disable"}
          successMessage={`App user ${isDisabled ? "enabled" : "disabled"} successfully`}
          queryKey="admin-app-users"
          onSuccess={() => setOpen(false)}
          mutationFn={() =>
            AdminAppService.updateAppUserStatus({
              path: { app_user_id: user.id },
              body: { status: nextStatus },
            })
          }
        />
        <ConfirmMenuAction
          icon={Trash2}
          label="Delete User"
          title="Delete App User"
          description="This soft deletes the App user. The user will disappear from default lists and cannot use App APIs."
          confirmLabel="Delete"
          successMessage="App user deleted successfully"
          queryKey="admin-app-users"
          variant="destructive"
          onSuccess={() => setOpen(false)}
          mutationFn={() =>
            AdminAppService.deleteAppUser({
              path: { app_user_id: user.id },
            })
          }
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
