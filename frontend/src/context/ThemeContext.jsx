import React, { createContext, useContext, useState, useEffect } from 'react';

const ThemeContext = createContext(null);

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('ppe_theme');
    return saved ? saved : 'white-blue'; // Default to White & Blue as requested
  });

  useEffect(() => {
    localStorage.setItem('ppe_theme', theme);
    if (theme === 'white-blue') {
      document.documentElement.classList.add('theme-white-blue');
      document.body.classList.add('theme-white-blue');
      document.documentElement.classList.remove('theme-dark');
      document.body.classList.remove('theme-dark');
    } else {
      document.documentElement.classList.remove('theme-white-blue');
      document.body.classList.remove('theme-white-blue');
      document.documentElement.classList.add('theme-dark');
      document.body.classList.add('theme-dark');
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'white-blue' ? 'dark' : 'white-blue'));
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    return {
      theme: 'white-blue',
      toggleTheme: () => {},
      setTheme: () => {},
    };
  }
  return context;
};
