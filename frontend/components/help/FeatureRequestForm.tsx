'use client'
import { useState } from 'react'
import { Lightbulb, Send } from 'lucide-react'
import { FieldLabel, Input, Textarea } from '@/components/ui/Field'
import { Button } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'
import { siteConfig } from '@/lib/siteConfig'

export function FeatureRequestForm() {
  const { toast } = useToast()
  const [title, setTitle] = useState('')
  const [details, setDetails] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) {
      toast('error', 'Please give your idea a short title.')
      return
    }
    const subject = `Feature request: ${title}`
    const body = [
      `Idea details:\n${details || '(not provided)'}`,
      `\n— sent from the ${siteConfig.name} Feature Request page`,
    ].join('\n')
    window.location.href = `mailto:${siteConfig.supportEmail}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
    toast('info', 'Opening your email client…')
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <FieldLabel>Feature title</FieldLabel>
        <Input
          placeholder="e.g. Add a Loop Node to the Workflow Builder"
          value={title}
          onChange={e => setTitle(e.target.value)}
          maxLength={140}
        />
      </div>
      <div>
        <FieldLabel hint="Optional">What problem would this solve?</FieldLabel>
        <Textarea rows={5} placeholder="Tell us what you're trying to do and why this would help." value={details} onChange={e => setDetails(e.target.value)} />
      </div>
      <Button type="submit" variant="primary" icon={<Send size={14} />}>
        Send Feature Request
      </Button>
      <p className="text-[11px] text-white/25 flex items-center gap-1.5">
        <Lightbulb size={11} /> This opens your email client addressed to {siteConfig.supportEmail}.
      </p>
    </form>
  )
}
