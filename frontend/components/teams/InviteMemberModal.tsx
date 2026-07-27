'use client'
import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { FieldLabel, Input, Select } from '@/components/ui/Field'
import { Button } from '@/components/ui/Button'
import type { TeamRole } from '@/types/team'

const INVITE_ROLES: TeamRole[] = ['admin', 'editor', 'viewer']

export function InviteMemberModal({
  onClose,
  onInvite,
  loading,
}: {
  onClose: () => void
  onInvite: (email: string, role: TeamRole) => void
  loading: boolean
}) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<TeamRole>('editor')

  const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())

  return (
    <Modal onClose={onClose} title="Invite Member" subtitle="Send an invite by email">
      <div className="space-y-4">
        <div>
          <FieldLabel>Email address *</FieldLabel>
          <Input
            autoFocus
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && valid && onInvite(email.trim(), role)}
            placeholder="teammate@company.com"
          />
        </div>
        <div>
          <FieldLabel hint="Can be changed later">Role</FieldLabel>
          <Select value={role} onChange={e => setRole(e.target.value as TeamRole)}>
            {INVITE_ROLES.map(r => (
              <option key={r} value={r}>{r[0].toUpperCase() + r.slice(1)}</option>
            ))}
          </Select>
        </div>
        <div className="flex gap-2.5 pt-1">
          <Button variant="secondary" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button
            className="flex-1"
            loading={loading}
            disabled={!valid}
            onClick={() => valid && onInvite(email.trim(), role)}
          >
            Send Invite
          </Button>
        </div>
      </div>
    </Modal>
  )
}
