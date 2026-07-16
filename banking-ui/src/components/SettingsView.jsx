import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSettings } from '../context/SettingsContext.jsx';
import { enableCcai } from '../utils/constants.js';
import AnalyticsButton from './AnalyticsButton.jsx';


function SettingsView() {
  const navigate = useNavigate();
  const [isRestoreModalOpen, setIsRestoreModalOpen] = useState(false);
  const { 
    bankName, setBankName,
    siteTitle, setSiteTitle,
    brandColorFrom, setBrandColorFrom,
    brandColorTo, setBrandColorTo,
    logoIcon, setLogoIcon,
    customLogoUrl, setCustomLogoUrl,
    logoFit, setLogoFit,
    footerText, setFooterText,
    theme, setTheme,
    isCxAgentEnabled, setIsCxAgentEnabled,
    isCcaiAgentEnabled, setIsCcaiAgentEnabled,
    cardBgColor, setCardBgColor,
    setIsExportModalOpen,
    handleImport
  } = useSettings();

  return (
    <section className="relative pt-32 pb-24 md:pt-48 md:pb-32 px-6">
      <div className="max-w-4xl mx-auto bg-white dark:bg-slate-900 rounded-2xl p-8 border border-slate-200 dark:border-slate-800 shadow-xl">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Customization</h1>
          <AnalyticsButton trackingName="settings_view_back_to_home"
            onClick={() => navigate('/')}
            className="px-4 py-2 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-300 dark:hover:bg-slate-700 transition-colors"
          >
            Back to Home
          </AnalyticsButton>
        </div>
        
        <div className="space-y-6">
          <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-100 dark:border-slate-800">
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Bank Name
            </label>
            <input
              type="text"
              value={bankName}
              onChange={(e) => setBankName(e.target.value)}
              className="w-full px-4 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-100 dark:border-slate-800">
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Site Title
            </label>
            <input
              type="text"
              value={siteTitle}
              onChange={(e) => setSiteTitle(e.target.value)}
              className="w-full px-4 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-100 dark:border-slate-800">
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Brand Colors
            </label>
            <div className="flex space-x-4">
              <div className="flex-1">
                <label className="block text-xs text-slate-500 mb-1">Start Color</label>
                <input
                  type="color"
                  value={brandColorFrom}
                  onChange={(e) => setBrandColorFrom(e.target.value)}
                  className="w-full h-10 p-1 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 cursor-pointer"
                />
              </div>
              <div className="flex-1">
                <label className="block text-xs text-slate-500 mb-1">End Color</label>
                <input
                  type="color"
                  value={brandColorTo}
                  onChange={(e) => setBrandColorTo(e.target.value)}
                  className="w-full h-10 p-1 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 cursor-pointer"
                />
              </div>
            </div>
          </div>

          <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-100 dark:border-slate-800">
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Card Background Color
            </label>
            <input
              type="color"
              value={cardBgColor}
              onChange={(e) => setCardBgColor(e.target.value)}
              className="w-full h-10 p-1 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 cursor-pointer"
            />
          </div>

          <div className="p-6 bg-slate-100 dark:bg-slate-800/50 rounded-2xl border border-slate-200 dark:border-slate-700 space-y-4">
            <h3 className="text-sm font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Logo Customization</h3>
            
            <div className="p-4 bg-white dark:bg-slate-900 rounded-xl border border-slate-100 dark:border-slate-800">
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                Logo Icon
              </label>
              <select
                value={logoIcon}
                onChange={(e) => setLogoIcon(e.target.value)}
                disabled={customLogoUrl && customLogoUrl.trim() !== ''}
                className="w-full px-4 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <option value="Shield">Shield (Finance)</option>
                <option value="Globe">Globe (Finance)</option>
                <option value="Lock">Lock (Finance)</option>
                <option value="CreditCard">Credit Card (Finance)</option>
                <option value="Heart">Heart (Healthcare)</option>
                <option value="Activity">Activity (Healthcare)</option>
                <option value="Phone">Phone (Telco)</option>
                <option value="Wifi">Wifi (Telco)</option>
                <option value="ShoppingBag">Shopping Bag (Retail)</option>
                <option value="Store">Store (Retail)</option>
              </select>
            </div>

            <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-100 dark:border-slate-800">
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                Custom Logo URL
              </label>
              <input
                type="text"
                value={customLogoUrl}
                onChange={(e) => setCustomLogoUrl(e.target.value)}
                placeholder="https://example.com/logo.png"
                className="w-full px-4 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-100 dark:border-slate-800">
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                Logo Fit
              </label>
              <select
                value={logoFit}
                onChange={(e) => setLogoFit(e.target.value)}
                className="w-full px-4 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
              >
                <option value="contain">Keep Size (Contain)</option>
                <option value="cover">Fill Available Space (Cover)</option>
              </select>
            </div>
          </div>

          <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-100 dark:border-slate-800">
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Footer Regulatory Text
            </label>
            <textarea
              value={footerText}
              onChange={(e) => setFooterText(e.target.value)}
              rows="3"
              className="w-full px-4 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-100 dark:border-slate-800">
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Theme Mode
            </label>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              className="w-full px-4 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <option value="light">Light</option>
              <option value="dark">Dark</option>
              <option value="auto">System (Auto)</option>
            </select>
          </div>

          <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-100 dark:border-slate-800">
            <div>
              <div className="font-semibold text-slate-900 dark:text-white">CX Agent Studio Agent</div>
              <div className="text-sm text-slate-500 dark:text-slate-400">Enable the main chat assistant on the bottom left.</div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input 
                type="checkbox" 
                checked={isCxAgentEnabled} 
                onChange={(e) => setIsCxAgentEnabled(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-300 dark:bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
            </label>
          </div>

          {enableCcai() && (
            <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-100 dark:border-slate-800">
              <div>
                <div className="font-semibold text-slate-900 dark:text-white">CCAI Chat Agent</div>
                <div className="text-sm text-slate-500 dark:text-slate-400">Enable the secondary chat widget.</div>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input 
                  type="checkbox" 
                  checked={isCcaiAgentEnabled} 
                  onChange={(e) => setIsCcaiAgentEnabled(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-slate-300 dark:bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
              </label>
            </div>
          )}
          
          <div className="flex justify-end mt-6 space-x-4">
            <input
              type="file"
              id="import-settings"
              className="hidden"
              accept=".json,.yaml,.yml"
              onChange={handleImport}
            />
            <AnalyticsButton trackingName="settings_view_import"
              onClick={() => document.getElementById('import-settings').click()}
              className="px-4 py-2 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-300 dark:hover:bg-slate-700 transition-colors"
            >
              Import
            </AnalyticsButton>
            <AnalyticsButton trackingName="settings_view_export"
              onClick={() => setIsExportModalOpen(true)}
              className="px-4 py-2 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-300 dark:hover:bg-slate-700 transition-colors"
            >
              Export
            </AnalyticsButton>
            <AnalyticsButton trackingName="settings_view_restore_defaults"
              onClick={() => setIsRestoreModalOpen(true)}
              className="px-4 py-2 rounded-full bg-red-500 hover:bg-red-600 text-white font-semibold transition-colors"
            >
              Restore Defaults
            </AnalyticsButton>

            {isRestoreModalOpen && (
              <div className="fixed inset-0 z-[200] bg-black/50 backdrop-blur-sm flex items-center justify-center">
                <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 max-w-md w-full">
                  <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-4">Restore Defaults</h2>
                  <p className="text-slate-600 dark:text-slate-400 mb-6">Are you sure you want to restore all settings to their default values? This action cannot be undone.</p>
                  <div className="flex justify-end space-x-4">
                    <AnalyticsButton trackingName="settings_view_cancel"
                      onClick={() => setIsRestoreModalOpen(false)}
                      className="px-4 py-2 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-300 dark:hover:bg-slate-700 transition-colors"
                    >
                      Cancel
                    </AnalyticsButton>
                    <AnalyticsButton trackingName="settings_view_confirm"
                      onClick={() => {
                        setIsCxAgentEnabled(true);
                        setIsCcaiAgentEnabled(false);
                        setBankName('Nova Horizon');
                        setSiteTitle('Nova Horizon Credit Union | Premium Digital Banking');
                        setLogoIcon('Shield');
                        setCustomLogoUrl('');
                        setLogoFit('contain');
                        setBrandColorFrom('#10b981');
                        setBrandColorTo('#2dd4bf');
                        setCardBgColor('#0f172a');
                        setTheme('auto');
                        setFooterText('Nova Horizon Credit Union is a federally chartered credit union. All member deposits are federally insured by the NCUA.');
                        setIsRestoreModalOpen(false);
                      }}
                      className="px-4 py-2 rounded-full bg-red-500 hover:bg-red-600 text-white font-semibold transition-colors"
                    >
                      Confirm
                    </AnalyticsButton>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

export default SettingsView;
