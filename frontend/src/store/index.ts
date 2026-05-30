import { create } from "zustand";
import type { User, Approval } from "@/types";
import type { TenantTheme } from "@/lib/theme";

// ─── User Store ──────────────────────────────────────────────────────────────

interface UserStore {
  user: User | null;
  setUser: (user: User | null) => void;
  clearUser: () => void;
}

export const useUserStore = create<UserStore>()((set) => ({
  user: null,
  setUser: (user) => set({ user }),
  clearUser: () => set({ user: null }),
}));

// ─── Notification Store ──────────────────────────────────────────────────────

export interface NotificationItem {
  id: string;
  tipo: string | null;
  titulo: string;
  corpo: string | null;
  lida: boolean;
  priority: string;
  link: string | null;
  created_at: string;
}

interface NotificationStore {
  notifications: NotificationItem[];
  unreadCount: number;
  loading: boolean;
  setNotifications: (items: NotificationItem[], unreadCount: number) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
  addNotification: (item: NotificationItem) => void;
  setLoading: (v: boolean) => void;
}

export const useNotificationStore = create<NotificationStore>()((set) => ({
  notifications: [],
  unreadCount: 0,
  loading: false,
  setNotifications: (items, unreadCount) =>
    set({ notifications: items, unreadCount }),
  markRead: (id) =>
    set((state) => ({
      notifications: state.notifications.map((n) =>
        n.id === id ? { ...n, lida: true } : n
      ),
      unreadCount: Math.max(0, state.unreadCount - 1),
    })),
  markAllRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, lida: true })),
      unreadCount: 0,
    })),
  addNotification: (item) =>
    set((state) => ({
      notifications: [item, ...state.notifications].slice(0, 50),
      unreadCount: item.lida ? state.unreadCount : state.unreadCount + 1,
    })),
  setLoading: (v) => set({ loading: v }),
}));

// ─── Approval Store ───────────────────────────────────────────────────────────

interface ApprovalStore {
  pendingCount: number;
  setPendingCount: (count: number) => void;
  incrementPending: () => void;
}

export const useApprovalStore = create<ApprovalStore>()((set) => ({
  pendingCount: 0,
  setPendingCount: (count) => set({ pendingCount: count }),
  incrementPending: () =>
    set((state) => ({ pendingCount: state.pendingCount + 1 })),
}));

// ─── Theme Store ──────────────────────────────────────────────────────────────

const DEFAULT_THEME: TenantTheme = {
  primaryColor: "#B8954A",
  secondaryColor: "#1E2229",
  accentColor: "#F4F0EA",
  appName: "AFJ CORE",
  logoUrl: null,
  logoDarkUrl: null,
  faviconUrl: null,
};

interface ThemeStore {
  theme: TenantTheme;
  setTheme: (t: TenantTheme) => void;
}

export const useThemeStore = create<ThemeStore>()((set) => ({
  theme: DEFAULT_THEME,
  setTheme: (theme) => set({ theme }),
}));
