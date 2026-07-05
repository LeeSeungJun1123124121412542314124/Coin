export type UsVolumeSectionState = 'data' | 'loading' | 'error'

interface ApiSection {
  data: unknown
  loading: boolean
  error: unknown
}

function resolveSection(api: ApiSection): UsVolumeSectionState {
  if (api.data) return 'data'
  if (api.error) return 'error'
  return 'loading'
}

export function resolveUsVolumeSections(sections: {
  stock: ApiSection
  putcall: ApiSection
}): { stock: UsVolumeSectionState; putcall: UsVolumeSectionState } {
  return {
    stock: resolveSection(sections.stock),
    putcall: resolveSection(sections.putcall),
  }
}
