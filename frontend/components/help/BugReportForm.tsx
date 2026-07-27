'use client'
import { useState } from 'react'
import { Bug, Send } from 'lucide-react'
import { FieldLabel, Input, Textarea } from '@/components/ui/Field'
import { Button } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'
import { siteConfig } from '@/lib/siteConfig'

export function BugReportForm() {
  const { toast } = useToast()
  const [title, setTitle] = useState('')
  const [steps, setSteps] = useState('')
  const [expected, setExpected] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) {
      toast('error', 'Please give the bug a short title.')
      return
    }
    const subject = `Bug report: ${title}`
    const body = [
      `Steps to reproduce:\n${steps || '(not provided)'}`,
      `\nExpected behavior:\n${expected || '(not provided)'}`,
      `\n— sent from the ${siteConfig.name} Report a Bug page`,
    ].join('\n')
    window.location.href = `mailto:${siteConfig.supportEmail}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
    toast('info', 'Opening your email client…')
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <FieldLabel>Bug title</FieldLabel>
        <Input
          placeholder="e.g. Condition Node fails to save on the Workflow Builder"
          value={title}
          onChange={e => setTitle(e.target.value)}
          maxLength={140}
        />
      </div>
      <div>
        <FieldLabel hint="Optional">Steps to reproduce</FieldLabel>
        <Textarea rows={4} placeholder="1. Go to...&#10;2. Click on...&#10;3. See error" value={steps} onChange={e => setSteps(e.target.value)} />
      </div>
      <div>
        <FieldLabel hint="Optional">Expected behavior</FieldLabel>
        <Textarea rows={3} placeholder="What did you expect to happen instead?" value={expected} onChange={e => setExpected(e.target.value)} />
      </div>
      <Button type="submit" variant="primary" icon={<Send size={14} />}>
        Send Bug Report
      </Button>
      <p className="text-[11px] text-white/25 flex items-center gap-1.5">
        <Bug size={11} /> This opens your email client addressed to {siteConfig.supportEmail}.
      </p>
    </form>
  )
}
