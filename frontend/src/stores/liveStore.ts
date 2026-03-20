import { create } from 'zustand';

interface LiveEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp: number;
}

interface LiveState {
  active: boolean;
  sourceChatId: number | null;
  mode: string | null;
  stats: Record<string, number>;
  events: LiveEvent[];
  setActive: (active: boolean) => void;
  setStatus: (status: {
    active: boolean;
    source_chat_id: number | null;
    mode: string | null;
    stats: Record<string, number>;
  }) => void;
  addEvent: (event: LiveEvent) => void;
  clearEvents: () => void;
  reset: () => void;
}

const initialState = {
  active: false,
  sourceChatId: null as number | null,
  mode: null as string | null,
  stats: {} as Record<string, number>,
  events: [] as LiveEvent[],
};

export const useLiveStore = create<LiveState>()((set) => ({
  ...initialState,
  setActive: (active) => set({ active }),
  setStatus: (status) =>
    set({
      active: status.active,
      sourceChatId: status.source_chat_id,
      mode: status.mode,
      stats: status.stats,
    }),
  addEvent: (event) =>
    set((state) => ({
      events: [event, ...state.events].slice(0, 200),
    })),
  clearEvents: () => set({ events: [] }),
  reset: () => set(initialState),
}));
