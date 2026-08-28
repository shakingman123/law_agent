import { create } from 'zustand';
import type { ThemeConfig, MappingAlgorithm } from 'antd';
import { theme as antdThemeCore } from 'antd';
import { storage } from '../utils/storage';

export type FontSize = '小' | '中' | '大';
export type BgTheme = '浅灰' | '米白' | '深色' | '护眼绿';

export interface UiSettings {
  fontSize: FontSize;
  bgTheme: BgTheme;
}

const STORAGE_KEY_PREFIX = 'ui_settings_v1';

/** 不同用户使用不同的存储 key，避免同一浏览器多账号共用一套设置 */
const storageKeyFor = (userId: string | null) =>
  userId ? `${STORAGE_KEY_PREFIX}:u:${userId}` : `${STORAGE_KEY_PREFIX}:anonymous`;

const FONT_SIZE_PX: Record<FontSize, number> = { 小: 12, 中: 14, 大: 16 };

/**
 * 每个主题的语义化配色：
 * - 深/浅模式算法用 algorithm（深色用 darkAlgorithm，保证所有 Antd 组件整体反色，对比度正确）
 * - 其余字段：布局背景、面板背景、边框、文字主/次色、侧栏背景、主色背景（primaryBg）
 * - 4 种主题整体对比度一致：文字/背景不会出现"白底白字"或"黑底黑字"
 */
interface ThemePalette {
  algorithm: MappingAlgorithm | undefined;
  primary: string;
  primaryHover: string;
  primaryBg: string;
  background: string; // colorBgLayout：整个页面背景
  panel: string;      // colorBgContainer：卡片/表单/输入框背景
  text: string;       // colorText：正文
  muted: string;      // colorTextSecondary：次级文字
  border: string;     // colorBorder：边框
  sidebarBg: string;  // 侧栏底色
  success: string;
  warning: string;
  danger: string;
  amber: string;
  green: string;
}

const PALETTES: Record<BgTheme, ThemePalette> = {
  // 默认浅灰
  浅灰: {
    algorithm: undefined,
    primary: '#1D4ED8',
    primaryHover: '#2563EB',
    primaryBg: '#EFF4FF',
    background: '#EEF2F7',
    panel: '#FFFFFF',
    text: '#0F172A',
    muted: '#64748B',
    border: '#E3E8EF',
    sidebarBg: '#F8FAFC',
    success: '#059669',
    warning: '#B45309',
    danger: '#DC2626',
    amber: '#B45309',
    green: '#059669',
  },
  // 米白暖色（降低对比，暖色调）
  米白: {
    algorithm: undefined,
    primary: '#1E40AF',
    primaryHover: '#1D4ED8',
    primaryBg: '#F4EEE3',
    background: '#FAF7F0',
    panel: '#FFFBF2',
    text: '#3B3A36',
    muted: '#8A8882',
    border: '#E8E3D5',
    sidebarBg: '#F7F2E6',
    success: '#2F6B4F',
    warning: '#92400E',
    danger: '#B91C1C',
    amber: '#92400E',
    green: '#2F6B4F',
  },
  // 深色：必须使用 darkAlgorithm 才能让所有 Antd 组件整体反色（按钮/输入框/下拉/表格/分页等）
  深色: {
    algorithm: antdThemeCore.darkAlgorithm,
    primary: '#3B82F6',
    primaryHover: '#2563EB',
    primaryBg: '#1E3A8A',
    background: '#0F172A', // 比面板再深一层，有层次感
    panel: '#1E293B',
    text: '#F1F5F9',
    muted: '#94A3B8',
    border: '#334155',
    sidebarBg: '#111827',
    success: '#34D399',
    warning: '#F59E0B',
    danger: '#F87171',
    amber: '#F59E0B',
    green: '#34D399',
  },
  // 护眼绿
  护眼绿: {
    algorithm: undefined,
    primary: '#065F46',
    primaryHover: '#047857',
    primaryBg: '#D1FAE5',
    background: '#ECF7EC',
    panel: '#FFFFFF',
    text: '#1F3A1F',
    muted: '#6B8A6B',
    border: '#C7E6C7',
    sidebarBg: '#F0F9F0',
    success: '#059669',
    warning: '#92400E',
    danger: '#B91C1C',
    amber: '#B45309',
    green: '#047857',
  },
};

const defaultSettings: UiSettings = { fontSize: '中', bgTheme: '浅灰' };

function loadSettings(userId: string | null): UiSettings {
  try {
    const raw = storage.get(storageKeyFor(userId));
    if (!raw) return defaultSettings;
    const parsed = JSON.parse(raw) as Partial<UiSettings>;
    return {
      fontSize: (parsed.fontSize && FONT_SIZE_PX[parsed.fontSize] ? parsed.fontSize : defaultSettings.fontSize),
      bgTheme: (parsed.bgTheme && PALETTES[parsed.bgTheme] ? parsed.bgTheme : defaultSettings.bgTheme),
    };
  } catch {
    return defaultSettings;
  }
}

/**
 * 把当前主题配色同步到 documentElement 的 CSS 变量上。
 * 这样 global.css 和代码中通过 var(--color-xxx) 引用的样式都会整体自适应。
 */
function applyCssVars(p: ThemePalette) {
  const root = document.documentElement;
  const setVar = (k: string, v: string) => root.style.setProperty(k, v);
  setVar('--color-primary', p.primary);
  setVar('--color-primary-hover', p.primaryHover);
  setVar('--color-primary-bg', p.primaryBg);
  setVar('--color-background', p.background);
  setVar('--color-panel', p.panel);
  setVar('--color-text', p.text);
  setVar('--color-muted', p.muted);
  setVar('--color-border', p.border);
  setVar('--color-sidebar-bg', p.sidebarBg);
  setVar('--color-success', p.success);
  setVar('--color-warning', p.warning);
  setVar('--color-danger', p.danger);
  setVar('--color-amber', p.amber);
  setVar('--color-green', p.green);
}

/**
 * 生成动态 antd 主题：
 * - algorithm 控制深色/浅色算法（深色必须走 darkAlgorithm，否则仅换背景色会导致组件样式没反色、对比度错误）
 * - 配色 token 全部取自 PALETTE，保证整体统一
 * - 字体大小按设置取值
 */
export function buildAntdTheme(s: UiSettings): ThemeConfig {
  const p = PALETTES[s.bgTheme];
  const config: ThemeConfig = {
    algorithm: p.algorithm,
    token: {
      colorPrimary: p.primary,
      colorInfo: p.primary,
      colorBgLayout: p.background,
      colorBgContainer: p.panel,
      colorBgElevated: p.panel,
      colorBorder: p.border,
      colorBorderSecondary: p.border,
      colorText: p.text,
      colorTextSecondary: p.muted,
      colorTextTertiary: p.muted,
      colorTextQuaternary: p.muted,
      colorError: p.danger,
      colorWarning: p.amber,
      colorSuccess: p.green,
      borderRadius: 8,
      fontFamily: 'PingFang SC, Microsoft YaHei, Segoe UI, -apple-system, BlinkMacSystemFont, sans-serif',
      fontSize: FONT_SIZE_PX[s.fontSize],
    },
    components: {
      Layout: {
        siderBg: p.sidebarBg,
        headerBg: p.panel,
        bodyBg: p.background,
        triggerBg: p.sidebarBg,
        triggerColor: p.text,
      },
      Card: {
        borderRadiusLG: 12,
        boxShadowTertiary:
          s.bgTheme === '深色'
            ? '0 1px 3px rgba(0,0,0,.5), 0 8px 24px rgba(0,0,0,.35)'
            : '0 1px 3px rgba(15,23,42,.08), 0 8px 24px rgba(15,23,42,.06)',
      },
      Button: { borderRadius: 8, controlHeight: 36 },
      Menu: {
        itemHeight: 38,
        itemBorderRadius: 8,
        itemSelectedBg: p.primaryBg,
        itemSelectedColor: p.primary,
        darkItemBg: p.sidebarBg,
      },
    },
  };
  return config;
}

interface UiState {
  /** 当前绑定的用户 id；null 表示未登录（匿名/登录前） */
  boundUserId: string | null;
  settings: UiSettings;
  palette: ThemePalette;
  antdTheme: ThemeConfig;
  /** 切换到指定用户的设置（登录/登出时调用），会重新加载该用户专属配置 */
  bindUser: (userId: string | null) => void;
  /** 修改设置（保存到当前用户的存储槽位） */
  update: (patch: Partial<UiSettings>) => void;
}

export const useUiStore = create<UiState>((set, get) => {
  // 首次启动：此时还未登录，先以 anonymous 为默认槽位；authStore initAuth 成功后会 bindUser 切换到当前用户
  const initialUser: string | null = null;
  const initial = loadSettings(initialUser);
  const palette = PALETTES[initial.bgTheme];
  const antdTheme = buildAntdTheme(initial);
  if (typeof document !== 'undefined') applyCssVars(palette);

  return {
    boundUserId: initialUser,
    settings: initial,
    palette,
    antdTheme,

    bindUser: (userId) => {
      if (get().boundUserId === userId) return; // 同一用户，无需重刷
      const next = loadSettings(userId);
      const newPalette = PALETTES[next.bgTheme];
      const newTheme = buildAntdTheme(next);
      if (typeof document !== 'undefined') applyCssVars(newPalette);
      set({ boundUserId: userId, settings: next, palette: newPalette, antdTheme: newTheme });
    },

    update: (patch) =>
      set((s) => {
        const merged: UiSettings = { ...s.settings, ...patch };
        const newPalette = PALETTES[merged.bgTheme];
        const newTheme = buildAntdTheme(merged);
        storage.set(storageKeyFor(s.boundUserId), JSON.stringify(merged));
        if (typeof document !== 'undefined') applyCssVars(newPalette);
        return { settings: merged, palette: newPalette, antdTheme: newTheme };
      }),
  };
});

