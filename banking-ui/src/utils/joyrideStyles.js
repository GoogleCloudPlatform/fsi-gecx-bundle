// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * Generates reusable, premium styles for react-joyride tooltips
 * aligned with the Nova Horizon design system.
 * 
 * @param {string} resolvedTheme - 'light' or 'dark'
 * @param {string} brandColorFrom - Hex brand color (e.g. '#10b981')
 * @returns {object} React Joyride styles configuration
 */
export function getJoyrideStyles(resolvedTheme, brandColorFrom) {
  const isDark = resolvedTheme === 'dark';
  const brandColor = brandColorFrom || '#10b981';

  return {
    options: {
      arrowColor: isDark ? '#0f172a' : '#ffffff',
      backgroundColor: isDark ? 'rgba(15, 23, 42, 0.8)' : 'rgba(255, 255, 255, 0.9)',
      overlayColor: 'rgba(0, 0, 0, 0.55)',
      primaryColor: brandColor,
      textColor: isDark ? '#f8fafc' : '#0f172a',
      zIndex: 1000,
    },
    tooltip: {
      borderRadius: '24px',
      padding: '20px 24px',
      backgroundColor: isDark ? 'rgba(15, 23, 42, 0.8)' : 'rgba(255, 255, 255, 0.9)',
      boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
      backdropFilter: 'blur(16px)',
      WebkitBackdropFilter: 'blur(16px)',
    },
    arrow: {
      color: isDark ? '#0f172a' : '#ffffff',
      opacity: isDark ? 0.8 : 0.9,
      WebkitBackdropFilter: 'blur(16px)',
      filter: 'drop-shadow(0 4px 10px rgba(0, 0, 0, 0.15))',
    },
    tooltipContainer: {
      textAlign: 'left',
      fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    },
    tooltipContent: {
      padding: '12px 32px 16px 0',
      fontSize: '14px',
      fontWeight: '500',
      lineHeight: '1.6',
      color: isDark ? '#cbd5e1' : '#334155',
    },
    tooltipFooter: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'flex-end',
      marginTop: '8px',
    },
    buttonPrimary: {
      borderRadius: '16px',
      fontSize: '13px',
      fontWeight: 'bold',
      padding: '10px 24px',
      backgroundColor: brandColor,
      color: '#ffffff',
      outline: 'none',
      border: 'none',
      cursor: 'pointer',
      boxShadow: isDark ? 'none' : '0 4px 6px -1px rgba(16, 185, 129, 0.2)',
    },
    buttonBack: {
      marginRight: '12px',
      fontSize: '13px',
      fontWeight: '600',
      color: isDark ? '#94a3b8' : '#64748b',
      outline: 'none',
      border: 'none',
      cursor: 'pointer',
    },
    buttonSkip: {
      fontSize: '13px',
      fontWeight: '600',
      color: isDark ? '#94a3b8' : '#64748b',
      outline: 'none',
      border: 'none',
      cursor: 'pointer',
    },
    buttonClose: {
      top: '16px',
      right: '16px',
      color: isDark ? '#f8fafc' : '#475569',
    }
  };
}
