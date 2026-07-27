'use client'
import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { FieldLabel, Input } from '@/components/ui/Field'
import { Button } from '@/components/ui/Button'

export function CreateTeamModal({
  onClose,
  onCreate,
  loading,
}: {
  onClose: () => void
  onCreate: (name: string) => void
  loading: boolean
}) {
  const [name, setName] = useState('')

  return (
    <Modal onClose={onClose} title="New Team" subtitle="Create a shared workspace for your team">
      <div className="space-y-4">
        <div>
          <FieldLabel>Team name *</FieldLabel>
          <Input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && name.trim() && onCreate(name.trim())}
            placeholder="Growth Team, Support Squad…"
          />
        </div>
        <div className="flex gap-2.5 pt-1">
          <Button variant="secondary" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button
            className="flex-1"
            loading={loading}
            disabled={!name.trim()}
            onClick={() => name.trim() && onCreate(name.trim())}
          >
            Create Team
          </Button>
        </div>
      </div>
    </Modal>
  )
}
