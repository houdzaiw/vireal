import { useMutation, useQueryClient } from "@tanstack/react-query"
import type { LucideIcon } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

interface ConfirmMenuActionProps {
  icon: LucideIcon
  label: string
  title: string
  description: string
  confirmLabel: string
  successMessage: string
  queryKey: string
  variant?: "default" | "destructive"
  onSuccess?: () => void
  mutationFn: () => Promise<unknown>
}

export function ConfirmMenuAction({
  icon: Icon,
  label,
  title,
  description,
  confirmLabel,
  successMessage,
  queryKey,
  variant = "default",
  onSuccess,
  mutationFn,
}: ConfirmMenuActionProps) {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { handleSubmit } = useForm()

  const mutation = useMutation({
    mutationFn,
    onSuccess: () => {
      showSuccessToast(successMessage)
      setIsOpen(false)
      onSuccess?.()
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: [queryKey] })
    },
  })

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuItem
        variant={variant}
        onSelect={(event) => event.preventDefault()}
        onClick={() => setIsOpen(true)}
      >
        <Icon />
        {label}
      </DropdownMenuItem>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit(() => mutation.mutate())}>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4">
            <DialogClose asChild>
              <Button variant="outline" disabled={mutation.isPending}>
                Cancel
              </Button>
            </DialogClose>
            <LoadingButton
              variant={variant === "destructive" ? "destructive" : "default"}
              type="submit"
              loading={mutation.isPending}
            >
              {confirmLabel}
            </LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
