import type { ThemeConfig } from 'antd';

/**
 * 设计令牌（Design Tokens）
 * 依据 docs/figma-design-spec.md §1 设计令牌表
 *
 * colors.* 采用 `var(--xxx, 原始值)` 双写：
 *   - CSS 变量由 stores/uiStore.ts 切换主题时写入 documentElement
 *   - 未设置时（如首次渲染/SSR）使用右侧回退色，保持视觉一致
 * 这让所有页面通过 `colors.xxx` 引用的样式在切换主题时整体自适应。
 */

const _v = (name: string, fallback: string) => `var(${name}, ${fallback})`;

// 颜色
export const colors = {
  primary: _v('--color-primary', '#1D4ED8'),
  primaryHover: _v('--color-primary-hover', '#2563EB'),
  primaryBg: _v('--color-primary-bg', '#EFF4FF'),
  background: _v('--color-background', '#EEF2F7'),
  panel: _v('--color-panel', '#FFFFFF'),
  border: _v('--color-border', '#E3E8EF'),
  text: _v('--color-text', '#0F172A'),
  muted: _v('--color-muted', '#64748B'),
  danger: _v('--color-danger', '#DC2626'),
  amber: _v('--color-amber', '#B45309'),
  green: _v('--color-green', '#059669'),
  sidebarBg: _v('--color-sidebar-bg', '#F8FAFC'),
  /** 用于需要真实 #RRGGBB 色值的场景（例如生成渐变、SVG fill 等），默认浅色。 */
  _staticPrimary: '#1D4ED8',
} as const;

// 圆角
export const radius = {
  button: 8,
  card: 12,
  modal: 14,
  tag: 12,
} as const;

// 阴影
export const shadows = {
  card: '0 1px 3px rgba(15,23,42,.08), 0 8px 24px rgba(15,23,42,.06)',
  modal: '0 24px 64px rgba(15,23,42,.30)',
} as const;

// 间距基准 4px
export const spacing = {
  xs: 8,
  sm: 12,
  md: 16,
  lg: 24,
  xl: 32,
} as const;

/**
 * Antd 全局主题配置（默认）。
 * 注意：实际运行时主题由 stores/uiStore.ts 动态生成并传入 ConfigProvider，
 * 此处仅作为 SSR / 未加载 store 时的回退。
 */
export const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: '#1D4ED8',
    colorBgLayout: '#EEF2F7',
    colorBgContainer: '#FFFFFF',
    colorBorder: '#E3E8EF',
    colorText: '#0F172A',
    colorTextSecondary: '#64748B',
    colorError: '#DC2626',
    colorWarning: '#B45309',
    colorSuccess: '#059669',
    borderRadius: radius.button,
    fontFamily:
      'PingFang SC, Microsoft YaHei, Segoe UI, -apple-system, BlinkMacSystemFont, sans-serif',
    fontSize: 14,
  },
  components: {
    Layout: {
      siderBg: '#F8FAFC',
      headerBg: '#FFFFFF',
      bodyBg: '#EEF2F7',
    },
    Card: {
      borderRadiusLG: radius.card,
      boxShadowTertiary: shadows.card,
    },
    Button: {
      borderRadius: radius.button,
      controlHeight: 36,
    },
    Menu: {
      itemHeight: 38,
      itemBorderRadius: radius.button,
      itemSelectedBg: '#EFF4FF',
      itemSelectedColor: '#1D4ED8',
    },
  },
};
