import { Eye } from "lucide-react"
import { useState } from "react"

import type { AppAdminOperationLogPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { DateTime } from "./common"

interface AppOperationLogDetailsDialogProps {
  log: AppAdminOperationLogPublic
}

export function AppOperationLogDetailsDialog({
  log,
}: AppOperationLogDetailsDialogProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <Button variant="ghost" size="icon" onClick={() => setIsOpen(true)}>
        <Eye />
        <span className="sr-only">View operation details</span>
      </Button>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Operation Details</DialogTitle>
          <DialogDescription>{log.summary || log.action}</DialogDescription>
        </DialogHeader>

        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Action</dt>
            <dd className="break-all font-mono text-xs">{log.action}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Admin</dt>
            <dd className="break-all">{log.admin_email}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Target</dt>
            <dd className="break-all font-mono text-xs">
              {log.target_type}
              {log.target_id ? ` / ${log.target_id}` : ""}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Created</dt>
            <dd>
              <DateTime value={log.created_at} />
            </dd>
          </div>
        </dl>

        <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs">
          {JSON.stringify(log.details, null, 2)}
        </pre>
      </DialogContent>
    </Dialog>
  )
}
