import { apiClient } from './client'

export type TutorialStatus = 'not_started' | 'in_progress' | 'completed' | 'skipped'

export interface TutorialProgressDTO {
  feature_key: string
  status: TutorialStatus
  current_step: number
  completed_steps: number
}

export const tutorialApi = {
  list: async (): Promise<TutorialProgressDTO[]> => {
    const { data } = await apiClient.get('/tutorial/progress')
    return data
  },
  upsert: async (payload: TutorialProgressDTO): Promise<TutorialProgressDTO> => {
    const { data } = await apiClient.put('/tutorial/progress', payload)
    return data
  },
  restart: async (featureKey: string): Promise<TutorialProgressDTO> => {
    const { data } = await apiClient.post(`/tutorial/progress/${featureKey}/restart`)
    return data
  },
}
