import { apiClient } from './client'
import type {
  PersonalEmailAccount,
  PersonalEmailMessage,
  PersonalEmailDraft,
  PersonalEmailDigest,
  PersonalEmailFolder,
  PersonalEmailDraftStyle,
  PersonalEmailSyncResult,
  PersonalEmailAutoReplyRule,
  PersonalEmailFollowUp,
  PersonalEmailAnalytics,
} from '@/types/personalEmail'

export const personalEmailApi = {
  listAccounts: () =>
    apiClient
      .get<{ accounts: PersonalEmailAccount[]; configured: boolean }>('/personal-email/accounts')
      .then(r => r.data),

  authorizeUrl: (provider: 'gmail' | 'outlook' = 'gmail') =>
    apiClient
      .get<{ authorize_url: string }>('/personal-email/oauth/authorize', { params: { provider } })
      .then(r => r.data),

  disconnect: (accountId: string) =>
    apiClient.post<{ disconnected: boolean }>(`/personal-email/accounts/${accountId}/disconnect`).then(r => r.data),

  sync: (accountId: string) =>
    apiClient.post<PersonalEmailSyncResult>(`/personal-email/accounts/${accountId}/sync`).then(r => r.data),

  toggleDigest: (accountId: string, enabled: boolean) =>
    apiClient
      .post<{ digest_enabled: boolean }>(`/personal-email/accounts/${accountId}/digest-toggle`, { enabled })
      .then(r => r.data),

  listMessages: (accountId: string, folder: PersonalEmailFolder, search?: string, page = 1) =>
    apiClient
      .get<{ messages: PersonalEmailMessage[]; page: number; page_size: number }>(
        `/personal-email/accounts/${accountId}/messages`,
        { params: { folder, search: search || undefined, page } }
      )
      .then(r => r.data),

  getMessage: (messageId: string) =>
    apiClient.get<PersonalEmailMessage>(`/personal-email/messages/${messageId}`).then(r => r.data),

  star: (messageId: string) =>
    apiClient.post<{ is_starred: boolean }>(`/personal-email/messages/${messageId}/star`).then(r => r.data),

  unstar: (messageId: string) =>
    apiClient.post<{ is_starred: boolean }>(`/personal-email/messages/${messageId}/unstar`).then(r => r.data),

  analyze: (messageId: string) =>
    apiClient.post<PersonalEmailMessage>(`/personal-email/messages/${messageId}/analyze`).then(r => r.data),

  generateDrafts: (messageId: string, styles: PersonalEmailDraftStyle[], instructions?: string) =>
    apiClient
      .post<{ drafts: PersonalEmailDraft[] }>(`/personal-email/messages/${messageId}/drafts/generate`, {
        styles,
        instructions: instructions || undefined,
      })
      .then(r => r.data.drafts),

  editDraft: (draftId: string, content: string) =>
    apiClient.patch<PersonalEmailDraft>(`/personal-email/drafts/${draftId}`, { content }).then(r => r.data),

  regenerateDraft: (draftId: string, instructions?: string) =>
    apiClient
      .post<PersonalEmailDraft>(`/personal-email/drafts/${draftId}/regenerate`, {
        instructions: instructions || undefined,
      })
      .then(r => r.data),

  translateDraft: (draftId: string, targetLanguage: string) =>
    apiClient
      .post<PersonalEmailDraft>(`/personal-email/drafts/${draftId}/translate`, { target_language: targetLanguage })
      .then(r => r.data),

  generateDigest: (accountId: string) =>
    apiClient.post<PersonalEmailDigest>(`/personal-email/accounts/${accountId}/digest/generate`).then(r => r.data),

  latestDigest: (accountId: string) =>
    apiClient
      .get<{ digest: PersonalEmailDigest | null }>(`/personal-email/accounts/${accountId}/digest/latest`)
      .then(r => r.data.digest),

  digestHistory: (accountId: string, limit = 14) =>
    apiClient
      .get<{ digests: PersonalEmailDigest[] }>(`/personal-email/accounts/${accountId}/digest/history`, {
        params: { limit },
      })
      .then(r => r.data.digests),

  // ── Part 2: send / schedule / approval ────────────────────────────────
  editRecipients: (draftId: string, payload: { to_addresses?: string; cc?: string; bcc?: string; subject_override?: string }) =>
    apiClient.patch<PersonalEmailDraft>(`/personal-email/drafts/${draftId}/recipients`, payload).then(r => r.data),

  setAttachments: (draftId: string, attachments: { filename: string; mime_type: string; content_base64: string }[]) =>
    apiClient.put<PersonalEmailDraft>(`/personal-email/drafts/${draftId}/attachments`, { attachments }).then(r => r.data),

  sendDraft: (draftId: string) =>
    apiClient.post<PersonalEmailDraft>(`/personal-email/drafts/${draftId}/send`).then(r => r.data),

  scheduleDraft: (draftId: string, scheduledAt: string) =>
    apiClient.post<PersonalEmailDraft>(`/personal-email/drafts/${draftId}/schedule`, { scheduled_at: scheduledAt }).then(r => r.data),

  cancelScheduledDraft: (draftId: string) =>
    apiClient.post<PersonalEmailDraft>(`/personal-email/drafts/${draftId}/cancel-schedule`).then(r => r.data),

  approveDraft: (draftId: string) =>
    apiClient.post<PersonalEmailDraft>(`/personal-email/drafts/${draftId}/approve`).then(r => r.data),

  rejectDraft: (draftId: string) =>
    apiClient.post<PersonalEmailDraft>(`/personal-email/drafts/${draftId}/reject`).then(r => r.data),

  // ── Part 2: bulk reply ────────────────────────────────────────────────
  bulkReply: (accountId: string, messageIds: string[], style: PersonalEmailDraftStyle, instructions?: string, autoSend = false) =>
    apiClient
      .post<{ drafts: PersonalEmailDraft[]; sent_count: number; errors: string[] }>(
        `/personal-email/accounts/${accountId}/messages/bulk-reply`,
        { message_ids: messageIds, style, instructions: instructions || undefined, auto_send: autoSend }
      )
      .then(r => r.data),

  // ── Part 2: unanswered reminders / follow-ups / analytics / thread ────
  unanswered: (accountId: string, hours?: number) =>
    apiClient
      .get<{ messages: PersonalEmailMessage[] }>(`/personal-email/accounts/${accountId}/messages/unanswered`, {
        params: { hours },
      })
      .then(r => r.data.messages),

  generateFollowUp: (messageId: string) =>
    apiClient.post<PersonalEmailFollowUp>(`/personal-email/messages/${messageId}/follow-up`).then(r => r.data),

  analytics: (accountId: string, days = 30) =>
    apiClient
      .get<PersonalEmailAnalytics>(`/personal-email/accounts/${accountId}/analytics`, { params: { days } })
      .then(r => r.data),

  thread: (messageId: string) =>
    apiClient.get<{ thread: PersonalEmailMessage[] }>(`/personal-email/messages/${messageId}/thread`).then(r => r.data.thread),

  downloadAttachment: async (messageId: string, attachmentId: string, filename: string) => {
    const res = await apiClient.get(`/personal-email/messages/${messageId}/attachments/${attachmentId}/download`, {
      responseType: 'blob',
    })
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },

  categorize: (messageId: string) =>
    apiClient.post<PersonalEmailMessage>(`/personal-email/messages/${messageId}/categorize`).then(r => r.data),

  editLabels: (messageId: string, labels: string[]) =>
    apiClient.patch<{ labels: string[] }>(`/personal-email/messages/${messageId}/labels`, { labels }).then(r => r.data),

  // ── Part 2: auto-reply rules ───────────────────────────────────────────
  listAutoReplyRules: (accountId: string) =>
    apiClient
      .get<{ rules: PersonalEmailAutoReplyRule[] }>(`/personal-email/accounts/${accountId}/auto-reply-rules`)
      .then(r => r.data.rules),

  createAutoReplyRule: (accountId: string, payload: Partial<PersonalEmailAutoReplyRule> & { name: string }) =>
    apiClient
      .post<PersonalEmailAutoReplyRule>(`/personal-email/accounts/${accountId}/auto-reply-rules`, payload)
      .then(r => r.data),

  updateAutoReplyRule: (ruleId: string, payload: Partial<PersonalEmailAutoReplyRule> & { name: string }) =>
    apiClient.patch<PersonalEmailAutoReplyRule>(`/personal-email/auto-reply-rules/${ruleId}`, payload).then(r => r.data),

  toggleAutoReplyRule: (ruleId: string, enabled: boolean) =>
    apiClient.post<{ is_active: boolean }>(`/personal-email/auto-reply-rules/${ruleId}/toggle`, { enabled }).then(r => r.data),

  deleteAutoReplyRule: (ruleId: string) =>
    apiClient.delete<{ deleted: boolean }>(`/personal-email/auto-reply-rules/${ruleId}`).then(r => r.data),
}
