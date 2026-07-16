import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, User, Phone, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { useSettings } from '../context/SettingsContext.jsx';
import { updateCustomerProfile } from '../utils/api.js';
import { formatPhoneNumber, getPhonePlaceholder } from '../utils/formatters.js';
import AnalyticsButton from './AnalyticsButton.jsx';





function EditProfileView({ customerProfile, setCustomerProfile, fbUser }) {
  const navigate = useNavigate();
  const { brandColorFrom, brandColorTo } = useSettings();

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  useEffect(() => {
    if (customerProfile) {
      setFirstName(customerProfile.first_name || '');
      setLastName(customerProfile.last_name || '');
      setPhoneNumber(formatPhoneNumber(customerProfile.phone_number || ''));
    }
  }, [customerProfile]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!firstName.trim()) {
      setErrorMsg('First name is required.');
      return;
    }
    if (!lastName.trim()) {
      setErrorMsg('Last name is required.');
      return;
    }

    setIsSubmitting(true);

    try {
      await updateCustomerProfile({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone_number: phoneNumber.trim() || null
      });

      // Update the parent state
      setCustomerProfile({
        ...customerProfile,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone_number: phoneNumber.trim() || null
      });

      setSuccessMsg('Profile updated successfully!');
      setTimeout(() => {
        navigate('/');
      }, 1500);
    } catch (err) {
      console.error('Error updating profile:', err);
      setErrorMsg(err.message || 'An unexpected error occurred. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="relative pt-32 pb-24 md:pt-48 md:pb-32 px-6">
      {/* Background Glows */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full bg-emerald-500/10 dark:bg-emerald-500/5 blur-[120px] pointer-events-none -z-10" />

      <div className="max-w-xl mx-auto bg-white dark:bg-slate-900 rounded-3xl p-8 border border-slate-200 dark:border-slate-800/80 shadow-2xl relative overflow-hidden">
        {/* Card Header */}
        <div className="flex items-center justify-between mb-8 pb-4 border-b border-slate-100 dark:border-slate-800/50">
          <div className="flex items-center space-x-3">
            <AnalyticsButton trackingName="button_click_edit_profile_view_01"
              onClick={() => navigate('/')}
              className="p-2 rounded-xl bg-slate-50 dark:bg-slate-800 text-slate-500 hover:text-slate-900 dark:hover:text-white transition-all hover:scale-105"
              aria-label="Back"
            >
              <ArrowLeft className="w-5 h-5" />
            </AnalyticsButton>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-slate-900 via-slate-700 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
              Edit Profile
            </h1>
          </div>

          {fbUser?.photoURL && (
            <img 
              src={fbUser.photoURL} 
              alt="Profile Photo" 
              className="w-12 h-12 rounded-full object-cover border-2 border-slate-200 dark:border-slate-800/50 shadow-md shrink-0"
            />
          )}
        </div>

        {/* Alerts */}
        {errorMsg && (
          <div className="mb-6 p-4 rounded-2xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/30 text-red-600 dark:text-red-400 text-sm flex items-center gap-2.5 animate-shake">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div className="mb-6 p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/30 text-emerald-600 dark:text-emerald-400 text-sm flex items-center gap-2.5">
            <CheckCircle2 className="w-5 h-5 shrink-0 animate-bounce" />
            <span>{successMsg}</span>
          </div>
        )}

        {/* Edit Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
              <label htmlFor="first_name" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                First Name
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-slate-400">
                  <User className="w-4 h-4" />
                </span>
                <input
                  id="first_name"
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="First Name"
                  className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                  required
                />
              </div>
            </div>

            <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
              <label htmlFor="last_name" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                Last Name
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-slate-400">
                  <User className="w-4 h-4" />
                </span>
                <input
                  id="last_name"
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder="Last Name"
                  className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                  required
                />
              </div>
            </div>
          </div>

          <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-2xl border border-slate-100 dark:border-slate-800/50">
            <label htmlFor="phone_number" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
              Phone Number
            </label>
            <div className="relative">
              <span className="absolute left-3 top-2.5 text-slate-400">
                <Phone className="w-4 h-4" />
              </span>
              <input
                id="phone_number"
                type="tel"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(formatPhoneNumber(e.target.value))}
                placeholder={getPhonePlaceholder()}
                className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
              />
            </div>
          </div>

          {/* Form Actions */}
          <div className="flex items-center justify-end gap-4 pt-4 border-t border-slate-100 dark:border-slate-800/50">
            <AnalyticsButton trackingName="button_click_edit_profile_view_02"
              type="button"
              onClick={() => navigate('/')}
              className="px-6 py-2.5 text-sm font-semibold rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all cursor-pointer"
            >
              Cancel
            </AnalyticsButton>
            <AnalyticsButton trackingName="button_click_edit_profile_view_03"
              type="submit"
              disabled={isSubmitting}
              className="px-6 py-2.5 text-sm font-semibold rounded-full text-slate-950 hover:scale-102 active:scale-98 transition-all flex items-center justify-center gap-2 shadow-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                backgroundImage: `linear-gradient(to right, ${brandColorFrom}, ${brandColorTo})`,
                boxShadow: `0 10px 15px -3px ${brandColorFrom}30`
              }}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  <span>Save Changes</span>
                </>
              )}
            </AnalyticsButton>
          </div>
        </form>
      </div>
    </section>
  );
}

export default EditProfileView;
