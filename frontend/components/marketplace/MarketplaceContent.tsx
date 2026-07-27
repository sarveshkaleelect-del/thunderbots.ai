'use client'
import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Search, Store } from 'lucide-react'
import { marketplaceApi } from '@/lib/marketplace/api'
import type { MarketplaceTemplate } from '@/lib/marketplace/types'
import { getErrorMessage } from '@/lib/utils/errors'
import { useToast } from '@/components/ui/Toast'
import { SkeletonGrid, EmptyState, ErrorState } from '@/components/ui/States'
import { Input } from '@/components/ui/Field'
import { TemplateCard } from './TemplateCard'
import { CategoryFilter } from './CategoryFilter'
import { PreviewModal } from './PreviewModal'

export default function MarketplaceContent() {
  const router = useRouter()
  const { toast } = useToast()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<string | null>(null)
  const [previewing, setPreviewing] = useState<MarketplaceTemplate | null>(null)
  const [importingId, setImportingId] = useState<string | null>(null)

  const { data: templates = [], isLoading, error, refetch } = useQuery({
    queryKey: ['marketplace-templates'],
    queryFn: marketplaceApi.templates,
    staleTime: 5 * 60 * 1000, // catalog is static — no need to refetch aggressively
  })

  const importMutation = useMutation({
    mutationFn: (id: string) => marketplaceApi.importTemplate(id),
    onMutate: (id: string) => setImportingId(id),
    onSuccess: wf => {
      toast('success', `"${wf.name}" added to your workflows.`)
      setPreviewing(null)
      router.push(`/builder/${wf.id}`)
    },
    onError: err => toast('error', getErrorMessage(err, 'Could not import this template.')),
    onSettled: () => setImportingId(null),
  })

  const categories = useMemo(
    () => Array.from(new Set(templates.map(t => t.category))),
    [templates]
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return templates.filter(t => {
      if (category && t.category !== category) return false
      if (!q) return true
      return (
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.category.toLowerCase().includes(q) ||
        t.features.some(f => f.toLowerCase().includes(q))
      )
    })
  }, [templates, search, category])

  const featured = useMemo(() => templates.filter(t => t.featured), [templates])
  const recent = useMemo(
    () => [...templates].sort((a, b) => b.added_at.localeCompare(a.added_at)).slice(0, 6),
    [templates]
  )

  const showSections = !search && !category

  return (
    <main className="max-w-6xl mx-auto px-6 py-10">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-9 h-9 rounded-xl tb2-brand-mark flex items-center justify-center">
          <Store size={16} className="text-[#a5b4fc]" />
        </div>
        <h1 className="text-lg font-bold text-white">Thunder Marketplace</h1>
      </div>
      <p className="text-xs text-white/35 mb-6">
        Professionally designed bot templates — import one and start customizing instantly.
      </p>

      <div className="relative mb-5">
        <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/25" />
        <Input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search templates, industries, features…"
          className="pl-9"
        />
      </div>

      <div className="mb-8 overflow-x-auto -mx-1 px-1">
        <CategoryFilter categories={categories} active={category} onChange={setCategory} />
      </div>

      {isLoading && <SkeletonGrid count={6} />}

      {error && !isLoading && (
        <ErrorState
          title="Couldn't load the marketplace"
          description={getErrorMessage(error, 'Check your connection and try again.')}
          onRetry={() => refetch()}
        />
      )}

      {!isLoading && !error && (
        <>
          {showSections && featured.length > 0 && (
            <Section title="Featured Templates">
              <Grid
                items={featured}
                onPreview={setPreviewing}
                onUse={t => importMutation.mutate(t.id)}
                importingId={importingId}
              />
            </Section>
          )}

          {showSections && recent.length > 0 && (
            <Section title="Recently Added">
              <Grid
                items={recent}
                onPreview={setPreviewing}
                onUse={t => importMutation.mutate(t.id)}
                importingId={importingId}
              />
            </Section>
          )}

          <Section title={showSections ? 'All Templates' : `${filtered.length} result${filtered.length === 1 ? '' : 's'}`}>
            {filtered.length === 0 ? (
              <EmptyState
                icon={<Search size={28} />}
                title="No templates found"
                description="Try a different search term or category."
              />
            ) : (
              <Grid
                items={filtered}
                onPreview={setPreviewing}
                onUse={t => importMutation.mutate(t.id)}
                importingId={importingId}
              />
            )}
          </Section>
        </>
      )}

      {previewing && (
        <PreviewModal
          template={previewing}
          onClose={() => setPreviewing(null)}
          onUse={t => importMutation.mutate(t.id)}
          using={importingId === previewing.id}
        />
      )}
    </main>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-10">
      <h2 className="text-sm font-semibold text-white/70 mb-4">{title}</h2>
      {children}
    </div>
  )
}

function Grid({
  items,
  onPreview,
  onUse,
  importingId,
}: {
  items: MarketplaceTemplate[]
  onPreview: (t: MarketplaceTemplate) => void
  onUse: (t: MarketplaceTemplate) => void
  importingId: string | null
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {items.map((t, i) => (
        <TemplateCard
          key={t.id}
          template={t}
          style={{ animationDelay: `${Math.min(i, 8) * 35}ms` }}
          onPreview={onPreview}
          onUse={onUse}
          using={importingId === t.id}
        />
      ))}
    </div>
  )
}
