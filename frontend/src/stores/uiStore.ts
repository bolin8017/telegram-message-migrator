import { create } from 'zustand';

interface UiState {
  theme: 'light' | 'dark';
  onboardingStep: number;
  sidebarOpen: boolean;
  setTheme: (theme: 'light' | 'dark') => void;
  setOnboardingStep: (step: number) => void;
  setSidebarOpen: (open: boolean) => void;
}

function getInitialTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'dark';
  const stored = localStorage.getItem('theme');
  return stored === 'light' ? 'light' : 'dark';
}

export const useUiStore = create<UiState>()((set) => ({
  theme: getInitialTheme(),
  onboardingStep: 0,
  sidebarOpen: false,
  setTheme: (theme) => {
    localStorage.setItem('theme', theme);
    document.documentElement.setAttribute('data-theme', theme);
    set({ theme });
  },
  setOnboardingStep: (step) => set({ onboardingStep: step }),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
}));
