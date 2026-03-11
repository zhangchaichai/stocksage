import { create } from 'zustand';
import { chatApi } from '../api/endpoints';

interface ChatMsg {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  intent?: string;
  action?: string;
  data?: Record<string, unknown>;
  timestamp: number;
}

interface ChatState {
  open: boolean;
  messages: ChatMsg[];
  loading: boolean;
  toggleOpen: () => void;
  setOpen: (open: boolean) => void;
  sendMessage: (text: string) => Promise<{ intent: string; action?: string; data?: Record<string, unknown> } | null>;
  loadHistory: () => Promise<void>;
}

let msgCounter = 0;

export const useChatStore = create<ChatState>((set, get) => ({
  open: false,
  messages: [],
  loading: false,

  toggleOpen: () => set((s) => ({ open: !s.open })),
  setOpen: (open) => set({ open }),

  sendMessage: async (text: string) => {
    const userMsg: ChatMsg = {
      id: `local-${++msgCounter}`,
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    set((s) => ({ messages: [...s.messages, userMsg], loading: true }));

    try {
      const { data } = await chatApi.sendMessage({ message: text });
      const assistantMsg: ChatMsg = {
        id: `local-${++msgCounter}`,
        role: 'assistant',
        content: data.reply,
        intent: data.intent,
        action: data.action ?? undefined,
        data: data.data ?? undefined,
        timestamp: Date.now(),
      };
      set((s) => ({ messages: [...s.messages, assistantMsg], loading: false }));
      return { intent: data.intent, action: data.action ?? undefined, data: data.data ?? undefined };
    } catch {
      const errMsg: ChatMsg = {
        id: `local-${++msgCounter}`,
        role: 'assistant',
        content: 'Failed to get a response. Please try again.',
        timestamp: Date.now(),
      };
      set((s) => ({ messages: [...s.messages, errMsg], loading: false }));
      return null;
    }
  },

  loadHistory: async () => {
    try {
      const { data } = await chatApi.history();
      const msgs: ChatMsg[] = data.map((m: any) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        intent: m.intent,
        action: m.action_data?.action,
        data: m.action_data?.data,
        timestamp: new Date(m.created_at).getTime(),
      }));
      set({ messages: msgs });
    } catch {
      // ignore
    }
  },
}));
