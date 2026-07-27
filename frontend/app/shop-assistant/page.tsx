'use client'
// ThunderBots Smart Shop Assistant — Shops list (NEW, independent product)
// Entry point: create a shop, then jump into its ONE lightweight Shop Admin
// page. This page itself intentionally stays simple — it is not a
// dashboard, just a launcher.
import { useState } from 'react'
import Link from 'next/link'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Store, Plus, QrCode, ArrowRight } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input, FieldLabel } from '@/components/ui/Field'
import { TopBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { useToast } from '@/components/ui/Toast'
import { shopAssistantApi } from '@/lib/api/shopAssistant'

export default function ShopAssistantPage() {
  const [name, setName] = useState('')
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const { data: shops, isLoading } = useQuery({
    queryKey: ['shop-assistant', 'shops'],
    queryFn: shopAssistantApi.listShops,
  })

  const createMutation = useMutation({
    mutationFn: shopAssistantApi.createShop,
    onSuccess: () => {
      setName('')
      queryClient.invalidateQueries({ queryKey: ['shop-assistant', 'shops'] })
      toast('success', 'Shop created')
    },
    onError: () => toast('error', 'Could not create shop'),
  })

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar />

      <div className="flex-1 px-4 sm:px-6 py-8 sm:py-10 max-w-3xl mx-auto w-full">
        <div className="flex items-center gap-3 mb-1">
          <Store className="w-6 h-6 text-[#a5b4fc]" />
          <h1 className="text-xl font-semibold text-white">Smart Shop Assistant</h1>
        </div>
        <p className="text-sm text-white/40 mb-8">
          Real-time inventory and customer reservations, scanned straight off the counter.
        </p>

        <Card className="p-5 mb-8" data-tutorial="shop-launcher-create">
          <FieldLabel>New shop name</FieldLabel>
          <div className="flex flex-col sm:flex-row gap-2">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Sharma Hardware Store"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && name.trim()) createMutation.mutate(name.trim())
              }}
            />
            <Button
              icon={<Plus className="w-4 h-4" />}
              loading={createMutation.isPending}
              disabled={!name.trim()}
              onClick={() => createMutation.mutate(name.trim())}
              className="sm:flex-shrink-0"
            >
              Create Shop
            </Button>
          </div>
        </Card>

        <div className="space-y-3" data-tutorial="shop-launcher-list">
          {isLoading && <p className="text-sm text-white/30">Loading shops…</p>}
          {shops?.length === 0 && (
            <p className="text-sm text-white/30">No shops yet — create one above to get a QR code.</p>
          )}
          {shops?.map((shop) => (
            <Card key={shop.id} hover className="p-4 flex items-center justify-between gap-3 flex-wrap sm:flex-nowrap">
              <div className="min-w-0">
                <p className="text-sm font-medium text-white truncate">{shop.name}</p>
                <p className="text-xs text-white/35 mt-0.5 truncate">{shop.public_url}</p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <Link href={`/shop-assistant/${shop.id}/admin`}>
                  <Button size="sm" variant="secondary" icon={<QrCode className="w-3.5 h-3.5" />}>
                    Shop Admin
                  </Button>
                </Link>
                <a href={shop.public_url} target="_blank" rel="noreferrer">
                  <Button size="sm" variant="ghost" icon={<ArrowRight className="w-3.5 h-3.5" />}>
                    Customer Page
                  </Button>
                </a>
              </div>
            </Card>
          ))}
        </div>
      </div>

      <Footer />
    </div>
  )
}
