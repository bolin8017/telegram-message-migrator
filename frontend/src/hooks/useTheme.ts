import { useUiStore } from '../stores/uiStore';

export function useTheme() {
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);
  const toggle = () => setTheme(theme === 'dark' ? 'light' : 'dark');
  return { theme, setTheme, toggle };
}
