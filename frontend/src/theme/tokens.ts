import type { ThemeConfig } from 'antd';

/**
 * 设计令牌（Design Tokens）
 * 依据 docs/figma-design-spec.md §1 设计令牌表
 * 颜色 / 字体 / 圆角 / 阴影 / 间距
 */

// 颜色
export const colors = {
  primary: '#1D4ED8',
  primaryHover: '#2563EB',
  primaryBg: '#EFF4FF',
  background: '#EEF2F7',
  panel: '#FFFFFF',
  border: '#E3E8EF',
  text: '#0F172A',
  muted: '#64748B',
  danger: '#DC2626',
  amber: '#B45309',
  green: '#059669',
  sidebarBg: '#F8FAFC',
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
 * Antd 全局主题配置
 */
export const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: colors.primary,
    colorBgLayout: colors.background,
    colorBgContainer: colors.panel,
    colorBorder: colors.border,
    colorText: colors.text,
    colorTextSecondary: colors.muted,
    colorError: colors.danger,
    colorWarning: colors.amber,
    colorSuccess: colors.green,
    borderRadius: radius.button,
    fontFamily:
      'PingFang SC, Microsoft YaHei, Segoe UI, -apple-system, BlinkMacSystemFont, sans-serif',
    fontSize: 14,
  },
  components: {
    Layout: {
      siderBg: colors.sidebarBg,
      headerBg: colors.panel,
      bodyBg: colors.background,
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
      itemSelectedBg: colors.primaryBg,
      itemSelectedColor: colors.primary,
    },
  },
};
