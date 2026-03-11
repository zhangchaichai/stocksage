import { create } from 'zustand';
import type { User } from '../types';
import { authApi } from '../api/endpoints';

interface AuthState {
  token: string | null;
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  fetchUser: () => Promise<void>;
  init: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('token'),
  user: null,
  loading: true,

  login: async (email, password) => {
    const { data } = await authApi.login({ email, password });
    localStorage.setItem('token', data.access_token);
    set({ token: data.access_token });
    await get().fetchUser();
  },

  register: async (username, email, password) => {
    const { data } = await authApi.register({ username, email, password });
    localStorage.setItem('token', data.access_token);
    set({ token: data.access_token });
    await get().fetchUser();
  },

  logout: () => {
    localStorage.removeItem('token');
    set({ token: null, user: null });
  },

  fetchUser: async () => {
    try {
      const { data } = await authApi.me();
      set({ user: data, loading: false });
    } catch {
      set({ token: null, user: null, loading: false });
      localStorage.removeItem('token');
    }
  },

  init: async () => {
    const token = localStorage.getItem('token');
    if (token) {
      await get().fetchUser();
    } else {
      set({ loading: false });
    }
  },
}));
