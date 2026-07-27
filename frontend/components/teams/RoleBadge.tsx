import { Badge } from '@/components/ui/Card'
import type { TeamRole } from '@/types/team'

const ROLE_TONE: Record<TeamRole, 'accent' | 'cyan' | 'success' | 'default'> = {
  owner: 'accent',
  admin: 'cyan',
  editor: 'success',
  viewer: 'default',
}

export function RoleBadge({ role }: { role: TeamRole }) {
  return <Badge tone={ROLE_TONE[role]}>{role}</Badge>
}
