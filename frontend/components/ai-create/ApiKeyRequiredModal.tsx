'use client'
import { KeyRound } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'

export function ApiKeyRequiredModal({
  onGoToSettings,
  onCancel,
}: {
  onGoToSettings: () => void
  onCancel: () => void
}) {
  return (
    <Modal onClose={onCancel} title="API Key Required" maxWidth="max-w-sm">
      <div className="flex flex-col items-center text-center gap-4">
        <div className="w-12 h-12 rounded-2xl bg-[#6366f1]/10 border border-[#6366f1]/20 flex items-center justify-center">
          <KeyRound size={20} className="text-[#a5b4fc]" />
        </div>
        <p className="text-sm text-white/70 leading-relaxed">
          AI generation requires an API key.
        </p>
        <div className="flex gap-2.5 w-full pt-1">
          <Button variant="secondary" className="flex-1" onClick={onCancel}>
            Cancel
          </Button>
          <Button className="flex-1" onClick={onGoToSettings}>
            Go to API Settings
          </Button>
        </div>
      </div>
    </Modal>
  )
}
