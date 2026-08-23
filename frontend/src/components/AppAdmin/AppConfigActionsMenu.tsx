import { EllipsisVertical, ToggleLeft, ToggleRight } from "lucide-react"
import { useState } from "react"

import { AdminAppService, type AppConfigPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { AppConfigDialog } from "./AppConfigDialog"
import { ConfirmMenuAction } from "./ConfirmMenuAction"

interface AppConfigActionsMenuProps {
  config: AppConfigPublic
}

export function AppConfigActionsMenu({ config }: AppConfigActionsMenuProps) {
  const [open, setOpen] = useState(false)
  const isEnabled = Boolean(config.is_enabled)

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon">
          <EllipsisVertical />
          <span className="sr-only">Open actions</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <AppConfigDialog config={config} onSuccess={() => setOpen(false)} />
        <ConfirmMenuAction
          icon={isEnabled ? ToggleLeft : ToggleRight}
          label={isEnabled ? "Disable Config" : "Enable Config"}
          title={isEnabled ? "Disable Config" : "Enable Config"}
          description={
            isEnabled
              ? "This key will stop being returned to App startup requests."
              : "This key will be returned to App startup requests again."
          }
          confirmLabel={isEnabled ? "Disable" : "Enable"}
          successMessage={`Config ${isEnabled ? "disabled" : "enabled"} successfully`}
          queryKey="admin-app-configs"
          onSuccess={() => setOpen(false)}
          mutationFn={() =>
            AdminAppService.updateAppConfig({
              path: { config_id: config.id },
              body: { is_enabled: !isEnabled },
            })
          }
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
