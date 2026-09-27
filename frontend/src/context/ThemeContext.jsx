import { createContext, useContext, useEffect, useState } from 'react';

const ThemeContext = createContext({
  theme: 'dark',
  setTheme: () => {},
  toggleTheme: () => {},
  accent: 'cyan',
  setAccent: () => {}
});

const THEMES = ['light', 'dark'];
const ACCENTS = ['cyan', 'violet', 'blue', 'green', 'amber', 'rose'];

function loadSaved(key, allowed) {
  try {
    const v = localStorage.getItem(key);
    return allowed.includes(v) ? v : null;
  } catch {
    return null;
  }
}

/**
 * ThemeProvider — light/dark theme + accent color, applied instantly via
 * data-attributes on <html> and persisted to localStorage so preferences
 * survive app restarts (Electron relaunches).
 */
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => loadSaved('sv-theme', THEMES) || 'dark');
  const [accent, setAccent] = useState(() => loadSaved('sv-accent', ACCENTS) || 'cyan');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem('sv-theme', theme);
    } catch {
      /* persistence is best-effort */
    }
  }, [theme]);

  useEffect(() => {
    document.documentElement.setAttribute('data-accent', accent);
    try {
      localStorage.setItem('sv-accent', accent);
    } catch {
      /* persistence is best-effort */
    }
  }, [accent]);

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'));

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme, accent, setAccent }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
