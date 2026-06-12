import React, { createContext, useState, useEffect, useContext, useCallback } from 'react';
import yaml from 'js-yaml';

const SettingsContext = createContext();

export function SettingsProvider({ children }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'auto');
  const [isCxAgentEnabled, setIsCxAgentEnabled] = useState(() => {
    const saved = localStorage.getItem('isCxAgentEnabled');
    return saved !== null ? JSON.parse(saved) : true;
  });
  const [isCcaiAgentEnabled, setIsCcaiAgentEnabled] = useState(() => {
    const saved = localStorage.getItem('isCcaiAgentEnabled');
    return saved !== null ? JSON.parse(saved) : false;
  });
  const [bankName, setBankName] = useState(() => localStorage.getItem('bankName') || 'Nova Horizon');
  const [siteTitle, setSiteTitle] = useState(() => localStorage.getItem('siteTitle') || 'Nova Horizon Credit Union | Premium Digital Banking');
  const [footerText, setFooterText] = useState(() => {
    const saved = localStorage.getItem('footerText');
    return saved !== null ? saved : `${bankName} Credit Union is a federally chartered credit union. All member deposits are federally insured by the NCUA.`;
  });
  const [logoIcon, setLogoIcon] = useState(() => localStorage.getItem('logoIcon') || 'Shield');
  const [customLogoUrl, setCustomLogoUrl] = useState(() => localStorage.getItem('customLogoUrl') || '');
  const [logoFit, setLogoFit] = useState(() => localStorage.getItem('logoFit') || 'contain');
  const [brandColorFrom, setBrandColorFrom] = useState(() => localStorage.getItem('brandColorFrom') || '#10b981');
  const [brandColorTo, setBrandColorTo] = useState(() => localStorage.getItem('brandColorTo') || '#2dd4bf');
  const [cardBgColor, setCardBgColor] = useState(() => localStorage.getItem('cardBgColor') || '#0f172a');
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);

  const resolvedTheme = theme === 'dark' || (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';

  useEffect(() => {
    const applyTheme = (t) => {
      const resolved = t === 'dark' || (t === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
      if (resolved === 'dark') {
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
      }
    };

    applyTheme(theme);
    localStorage.setItem('theme', theme);

    if (theme === 'auto') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      const handleChange = () => applyTheme('auto');
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    }
  }, [theme]);

  useEffect(() => {
    localStorage.setItem('isCxAgentEnabled', JSON.stringify(isCxAgentEnabled));
    localStorage.setItem('isCcaiAgentEnabled', JSON.stringify(isCcaiAgentEnabled));
  }, [isCxAgentEnabled, isCcaiAgentEnabled]);

  useEffect(() => {
    localStorage.setItem('bankName', bankName);
  }, [bankName]);

  useEffect(() => {
    localStorage.setItem('siteTitle', siteTitle);
  }, [siteTitle]);

  useEffect(() => {
    localStorage.setItem('footerText', footerText);
  }, [footerText]);

  useEffect(() => {
    localStorage.setItem('logoIcon', logoIcon);
  }, [logoIcon]);

  useEffect(() => {
    localStorage.setItem('customLogoUrl', customLogoUrl);
  }, [customLogoUrl]);

  useEffect(() => {
    localStorage.setItem('logoFit', logoFit);
  }, [logoFit]);

  useEffect(() => {
    localStorage.setItem('brandColorFrom', brandColorFrom);
    localStorage.setItem('brandColorTo', brandColorTo);
  }, [brandColorFrom, brandColorTo]);

  useEffect(() => {
    localStorage.setItem('cardBgColor', cardBgColor);
    document.documentElement.style.setProperty('--card-bg-color', cardBgColor);
  }, [cardBgColor]);

  const handleExport = useCallback((format) => {
    const settings = {
      bankName,
      logoIcon,
      customLogoUrl,
      logoFit,
      footerText,
      theme,
      brandColorFrom,
      brandColorTo,
      cardBgColor,
      isCxAgentEnabled,
      isCcaiAgentEnabled,
      siteTitle
    };

    let content;
    let filename;
    let mimeType;

    if (format === 'json') {
      content = JSON.stringify(settings, null, 2);
      filename = `${bankName.replace(/\s+/g, '_')}_settings.json`;
      mimeType = 'application/json';
    } else {
      content = yaml.dump(settings);
      filename = `${bankName.replace(/\s+/g, '_')}_settings.yaml`;
      mimeType = 'text/yaml';
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    setIsExportModalOpen(false);
  }, [bankName, logoIcon, customLogoUrl, logoFit, footerText, theme, brandColorFrom, brandColorTo, cardBgColor, isCxAgentEnabled, isCcaiAgentEnabled, siteTitle]);

  const handleImport = useCallback((e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const content = event.target.result;
        let settings;
        if (file.name.endsWith('.json')) {
          settings = JSON.parse(content);
        } else if (file.name.endsWith('.yaml') || file.name.endsWith('.yml')) {
          settings = yaml.load(content);
        } else {
          throw new Error('Unsupported file format');
        }

        if (settings.bankName) setBankName(settings.bankName);
        if (settings.logoIcon) setLogoIcon(settings.logoIcon);
        if (settings.customLogoUrl !== undefined) setCustomLogoUrl(settings.customLogoUrl);
        if (settings.logoFit) setLogoFit(settings.logoFit);
        if (settings.footerText) setFooterText(settings.footerText);
        if (settings.theme) setTheme(settings.theme);
        if (settings.brandColorFrom) setBrandColorFrom(settings.brandColorFrom);
        if (settings.brandColorTo) setBrandColorTo(settings.brandColorTo);
        if (settings.cardBgColor) setCardBgColor(settings.cardBgColor);
        if (settings.isCxAgentEnabled !== undefined) setIsCxAgentEnabled(settings.isCxAgentEnabled);
        if (settings.isCcaiAgentEnabled !== undefined) setIsCcaiAgentEnabled(settings.isCcaiAgentEnabled);
        if (settings.siteTitle) setSiteTitle(settings.siteTitle);

        alert('Settings imported successfully!');
      } catch (error) {
        console.error('Import failed', error);
        alert(`Failed to import settings: ${error.message}`);
      }
    };
    reader.readAsText(file);
  }, []);

  const value = {
    theme, setTheme,
    isCxAgentEnabled, setIsCxAgentEnabled,
    isCcaiAgentEnabled, setIsCcaiAgentEnabled,
    bankName, setBankName,
    siteTitle, setSiteTitle,
    footerText, setFooterText,
    logoIcon, setLogoIcon,
    customLogoUrl, setCustomLogoUrl,
    logoFit, setLogoFit,
    brandColorFrom, setBrandColorFrom,
    brandColorTo, setBrandColorTo,
    cardBgColor, setCardBgColor,
    isExportModalOpen, setIsExportModalOpen,
    resolvedTheme,
    handleExport,
    handleImport
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSettings() {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
}
