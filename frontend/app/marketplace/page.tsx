'use client'
import { useEffect } from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { TopBar } from '@/components/ui/TopBar'
import { PageLoader } from '@/components/ui/States'

// Code-split: MarketplaceContent (grid, search, preview modal, react-query
// calls) is only fetched when this route is actually visited — it is not
// part of the dashboard/builder bundles and is never preloaded at startup.
const MarketplaceContent = dynamic(() => import('@/components/marketplace/MarketplaceContent'), {
  ssr: false,
  loading: () => <PageLoader label="Loading marketplace…" />,
})

export default function MarketplacePage() {
  const router = useRouter()

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  return (
    <div className="tb2-shell">
      <TopBar />
      <MarketplaceContent />
    </div>
  )
}
