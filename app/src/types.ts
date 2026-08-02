export type Align = 'left' | 'center' | 'right'
export type Surface = 'emboss' | 'deboss' | 'flush'

export interface TextBlock {
  text: string
  align: Align
  font: string
  style: string
  size: number
  dx: number
  dy: number
}

export interface Fastener {
  show: boolean
  head: string
  shaft: string
  threads: string
  driver: string
  flange: boolean
  security: boolean
}

export interface Label {
  id: string
  name: string
  qty: number
  tags: string[]
  width_u: number
  surface: Surface
  text_color: string
  backward_compatible: boolean
  text1: TextBlock
  text2: TextBlock
  fastener: Fastener
  hardware: string
  created_at?: string | null
  updated_at?: string | null
}

export interface Meta {
  fonts: string[]
  font_styles: string[]
  fastener_heads: string[]
  fastener_shafts: string[]
  fastener_threads: string[]
  fastener_drivers: string[]
  hardware: string[]
  accessories: string[]
  fonts_missing: string[]
}

export interface PlatePlacement {
  label_id: string
  title: string
  x: number
  y: number
  w: number
  h: number
}

export interface PlateEstimate {
  parts: number
  rows: number
  used_y: number
  fits: boolean
  message: string
  plate_x: number
  plate_y: number
  placements: PlatePlacement[]
}

export const emptyLabel = (): Label => ({
  id: '',
  name: '',
  qty: 1,
  tags: [],
  width_u: 1,
  surface: 'emboss',
  text_color: '#333333',
  backward_compatible: true,
  text1: { text: '', align: 'left', font: 'Open Sans', style: 'Regular', size: 5, dx: 0, dy: 0 },
  text2: { text: '', align: 'right', font: 'Open Sans', style: 'Regular', size: 6, dx: 0, dy: 0 },
  fastener: { show: false, head: 'socket', shaft: 'machine', threads: 'full', driver: 'phillips', flange: false, security: false },
  hardware: 'none',
})

export const labelTitle = (l: Label) => l.name || l.text1.text || l.text2.text || '(untitled)'

/** Printed width in mm — matches label_size_mm() on the server. */
export const labelWidthMm = (l: Label) => l.width_u * 42 - 6
