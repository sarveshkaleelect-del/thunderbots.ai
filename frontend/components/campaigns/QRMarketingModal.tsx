'use client'
import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  QrCode, MessageCircle, Send, Facebook, Instagram, Download, Printer, Share2,
  Copy, Check, RefreshCw, Trash2, ScanLine, Store, LayoutGrid,
} from 'lucide-react'
import { campaignsApi } from '@/lib/api/campaigns'
import { getErrorMessage } from '@/lib/utils/errors'
import { cn } from '@/lib/utils/cn'
import type { CampaignQRCode, QRChannel, QRChannelOption, QRPlacement } from '@/types/campaigns'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Card, Badge } from '@/components/ui/Card'
import { Select } from '@/components/ui/Field'
import { PageLoader, EmptyState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'

const PLACEMENTS: [QRPlacement, string][] = [
  ['shop_entrance', 'Shop Entrance'],
  ['cash_counter', 'Cash Counter'],
  ['product_packaging', 'Product Packaging'],
  ['bills', 'Bills'],
  ['visiting_card', 'Visiting Card'],
  ['posters', 'Posters'],
  ['menu', 'Menu'],
  ['website', 'Website'],
  ['other', 'Other'],
]

const PLACEMENT_LABEL: Record<string, string> = Object.fromEntries(PLACEMENTS)

const CHANNEL_META: Record<QRChannel, { label: string; icon: any; tone: string }> = {
  telegram: { label: 'Telegram', icon: Send, tone: 'text-[#7dd3fc]' },
  whatsapp: { label: 'WhatsApp', icon: MessageCircle, tone: 'text-emerald-400' },
  facebook: { label: 'Facebook', icon: Facebook, tone: 'text-[#93c5fd]' },
  instagram: { label: 'Instagram', icon: Instagram, tone: 'text-fuchsia-400' },
}

// ── QR image + actions for a single generated code ──────────────────────────
function QRCodeTile({ qr, onChanged }: { qr: CampaignQRCode; onChanged: () => void }) {
  const { toast } = useToast()
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState(false)

  const { data: svgData, isLoading } = useQuery({
    queryKey: ['qr-svg', qr.id],
    queryFn: () => campaignsApi.qrSvg(qr.id),
  })

  const regenerateMutation = useMutation({
    mutationFn: () => campaignsApi.qrRegenerate(qr.id),
    onSuccess: () => { toast('success', 'QR code regenerated. The old printed code will stop working.'); onChanged() },
    onError: err => toast('error', getErrorMessage(err, 'Could not regenerate this QR code.')),
  })

  const deleteMutation = useMutation({
    mutationFn: () => campaignsApi.qrDelete(qr.id),
    onSuccess: () => { toast('success', 'QR code removed.'); onChanged() },
    onError: err => toast('error', getErrorMessage(err, 'Could not remove this QR code.')),
  })

  const copyLink = () => {
    navigator.clipboard.writeText(qr.invite_link).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  // SVG -> PNG data URL (canvas), used by both Download and Print so what
  // prints matches what's downloaded.
  const svgToPngDataUrl = (svg: string, sizePx = 1024): Promise<string> => {
    return new Promise((resolve, reject) => {
      const blob = new Blob([svg], { type: 'image/svg+xml' })
      const url = URL.createObjectURL(blob)
      const img = new Image()
      img.onload = () => {
        const canvas = document.createElement('canvas')
        canvas.width = sizePx
        canvas.height = sizePx
        const ctx = canvas.getContext('2d')
        if (!ctx) { reject(new Error('canvas unavailable')); return }
        ctx.fillStyle = '#ffffff'
        ctx.fillRect(0, 0, sizePx, sizePx)
        ctx.drawImage(img, 0, 0, sizePx, sizePx)
        URL.revokeObjectURL(url)
        resolve(canvas.toDataURL('image/png'))
      }
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('failed to render QR image')) }
      img.src = url
    })
  }

  const handleDownload = async () => {
    if (!svgData) return
    setBusy(true)
    try {
      const dataUrl = await svgToPngDataUrl(svgData.qr_svg)
      const a = document.createElement('a')
      a.href = dataUrl
      a.download = `thunderbots-qr-${qr.channel}-${qr.placement}.png`
      a.click()
    } catch {
      toast('error', 'Could not prepare the QR image for download.')
    } finally {
      setBusy(false)
    }
  }

  const handlePrint = async () => {
    if (!svgData) return
    setBusy(true)
    try {
      const dataUrl = await svgToPngDataUrl(svgData.qr_svg)
      const win = window.open('', '_blank')
      if (!win) { toast('error', 'Allow pop-ups to print this QR code.'); return }
      win.document.write(`
        <html><head><title>Print QR — ${PLACEMENT_LABEL[qr.placement] || qr.placement}</title></head>
        <body style="margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:sans-serif;">
          <div style="text-align:center;">
            <img src="${dataUrl}" style="width:320px;height:320px;" />
            <p style="font-size:14px;color:#111;margin-top:12px;">
              Scan to chat on ${CHANNEL_META[qr.channel].label} — ${PLACEMENT_LABEL[qr.placement] || qr.placement}
            </p>
          </div>
        </body></html>
      `)
      win.document.close()
      win.focus()
      win.print()
    } catch {
      toast('error', 'Could not prepare the QR image for printing.')
    } finally {
      setBusy(false)
    }
  }

  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: `Chat with us on ${CHANNEL_META[qr.channel].label}`,
          url: qr.invite_link,
        })
        return
      } catch {
        // user cancelled — fall through to copy
      }
    }
    copyLink()
    toast('success', 'Invite link copied — sharing isn\u2019t supported on this device.')
  }

  return (
    <Card className="p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold text-white/80">{PLACEMENT_LABEL[qr.placement] || qr.placement}</p>
          {qr.label && <p className="text-[11px] text-white/35 mt-0.5">{qr.label}</p>}
        </div>
        <Badge tone="accent">
          <ScanLine size={10} className="inline mr-1 -mt-0.5" />
          {qr.scan_count} scan{qr.scan_count === 1 ? '' : 's'}
        </Badge>
      </div>

      <div className="w-full aspect-square rounded-xl bg-white flex items-center justify-center overflow-hidden">
        {isLoading || !svgData ? (
          <RefreshCw size={20} className="animate-spin text-black/20" />
        ) : (
          <div
            className="w-[85%] h-[85%] [&>svg]:w-full [&>svg]:h-full"
            dangerouslySetInnerHTML={{ __html: svgData.qr_svg }}
          />
        )}
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        <Button size="sm" variant="secondary" onClick={handleDownload} disabled={busy || !svgData} icon={<Download size={12} />}>
          Download
        </Button>
        <Button size="sm" variant="secondary" onClick={handlePrint} disabled={busy || !svgData} icon={<Printer size={12} />}>
          Print
        </Button>
        <Button size="sm" variant="secondary" onClick={handleShare} icon={<Share2 size={12} />}>
          Share
        </Button>
        <Button size="sm" variant="secondary" onClick={copyLink} icon={copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}>
          {copied ? 'Copied' : 'Copy Link'}
        </Button>
      </div>

      <div className="flex items-center gap-1.5 pt-1 border-t border-white/[0.06]">
        <Button
          size="sm" variant="ghost" className="flex-1"
          onClick={() => regenerateMutation.mutate()}
          loading={regenerateMutation.isPending}
          icon={<RefreshCw size={12} />}
        >
          Regenerate
        </Button>
        <Button
          size="sm" variant="ghost"
          onClick={() => deleteMutation.mutate()}
          loading={deleteMutation.isPending}
          icon={<Trash2 size={12} className="text-red-400" />}
        />
      </div>
    </Card>
  )
}

// ── One connected channel's whole QR system (generator + its codes) ─────────
function ChannelQRSystem({
  option,
  codes,
  onChanged,
}: {
  option: QRChannelOption
  codes: CampaignQRCode[]
  onChanged: () => void
}) {
  const { toast } = useToast()
  const [placement, setPlacement] = useState<QRPlacement>('shop_entrance')
  const meta = CHANNEL_META[option.channel]
  const Icon = meta.icon

  const createMutation = useMutation({
    mutationFn: () => campaignsApi.qrCreate({
      workflow_id: option.workflow_id!,
      channel: option.channel,
      placement,
    }),
    onSuccess: () => { toast('success', 'QR code generated.'); onChanged() },
    onError: err => toast('error', getErrorMessage(err, 'Could not generate a QR code.')),
  })

  if (option.is_architecture_only) {
    return (
      <Card className="p-5 opacity-60">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl bg-white/[0.05] border border-white/10 flex items-center justify-center">
            <Icon size={16} className={meta.tone} />
          </div>
          <div>
            <p className="text-sm font-semibold text-white/80">{meta.label} QR</p>
            <p className="text-[11px] text-white/35">Coming soon</p>
          </div>
        </div>
        <p className="text-xs text-white/35">
          Architecture is in place for {meta.label} QR acquisition — it will light up here as soon as the {meta.label} channel connection supports a direct chat-open link.
        </p>
      </Card>
    )
  }

  if (!option.is_connected) {
    return (
      <Card className="p-5 opacity-70">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-white/[0.05] border border-white/10 flex items-center justify-center">
            <Icon size={16} className={meta.tone} />
          </div>
          <div>
            <p className="text-sm font-semibold text-white/80">{meta.label} — {option.bot_name}</p>
            <p className="text-[11px] text-amber-400/80">Connect and enable {meta.label} in Settings to generate a QR code.</p>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      <Card className="p-5">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-white/[0.05] border border-white/10 flex items-center justify-center flex-shrink-0">
              <Icon size={16} className={meta.tone} />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white/80 truncate">{meta.label} — {option.bot_name}</p>
              <p className="text-[11px] text-white/35 truncate">{option.identifier}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Select value={placement} onChange={e => setPlacement(e.target.value as QRPlacement)} className="!py-2 text-xs min-h-0 w-44">
              {PLACEMENTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </Select>
            <Button size="sm" onClick={() => createMutation.mutate()} loading={createMutation.isPending} icon={<QrCode size={13} />}>
              Generate QR
            </Button>
          </div>
        </div>
      </Card>

      {codes.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {codes.map(qr => <QRCodeTile key={qr.id} qr={qr} onChanged={onChanged} />)}
        </div>
      )}
    </div>
  )
}

export function QRMarketingModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()

  const { data: channels = [], isLoading: channelsLoading } = useQuery({
    queryKey: ['qr-channels'],
    queryFn: campaignsApi.qrChannels,
  })

  const { data: codes = [], isLoading: codesLoading } = useQuery({
    queryKey: ['qr-codes'],
    queryFn: () => campaignsApi.qrList(),
  })

  const codesByWorkflow = useMemo(() => {
    const map: Record<string, CampaignQRCode[]> = {}
    for (const qr of codes) {
      const key = `${qr.workflow_id}:${qr.channel}`
      if (!map[key]) map[key] = []
      map[key].push(qr)
    }
    return map
  }, [codes])

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['qr-codes'] })
    qc.invalidateQueries({ queryKey: ['qr-svg'] })
  }

  const isLoading = channelsLoading || codesLoading

  return (
    <Modal onClose={onClose} title="QR Marketing" subtitle="Turn foot traffic into subscribers with a scannable QR code per channel" maxWidth="max-w-5xl">
      <div className="flex items-start gap-3 mb-5 p-3 rounded-xl bg-[#6366f1]/[0.06] border border-[#6366f1]/15">
        <Store size={16} className="text-[#a5b4fc] flex-shrink-0 mt-0.5" />
        <p className="text-xs text-white/50 leading-relaxed">
          Print a QR at your Shop Entrance, Cash Counter, Bills, or Visiting Card — when a customer scans it and messages your bot, they become a permanent Telegram or WhatsApp subscriber automatically.
        </p>
      </div>

      {isLoading ? (
        <PageLoader />
      ) : channels.length === 0 ? (
        <EmptyState
          icon={<LayoutGrid size={22} />}
          title="No channels yet"
          description="Connect a Telegram bot or WhatsApp Business account first, then come back to generate its QR code."
        />
      ) : (
        <div className="space-y-5">
          {channels.map(option => (
            <ChannelQRSystem
              key={`${option.channel}:${option.workflow_id ?? 'none'}`}
              option={option}
              codes={option.workflow_id ? (codesByWorkflow[`${option.workflow_id}:${option.channel}`] || []) : []}
              onChanged={refresh}
            />
          ))}
        </div>
      )}
    </Modal>
  )
}
