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

import { PAGE_TITLES } from './constants.js';

/**
 * Derives a breadcrumb string from a given URL path.
 * e.g. "/admin/underwriting" -> "Admin > Underwriting"
 * @param {string} path - The URL path
 * @returns {string} The formatted breadcrumb string
 */
export const deriveBreadcrumbFromUrl = (path) => {
  if (!path || path === '/') return 'Home';
  
  const segments = path.split('/').filter(Boolean);
  if (segments.length === 0) return 'Home';

  return segments.map(segment => {
    // Basic formatting: replace hyphens with spaces and capitalize words
    return segment
      .split('-')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }).join(' > ');
};

/**
 * Logs a consistent interaction event to Firebase Analytics.
 * @param {string} category - 'button_click' or 'link_click'
 * @param {string} analyticsId - The name of the interaction (e.g., 'submit_loan', 'view_details')
 * @param {Object} [additionalProps] - Any extra properties to log
 */
export const logInteractionEvent = (category, analyticsId, additionalProps = {}) => {
  const payload = {
    content_type: category,
    item_id: analyticsId,
    page_path: window.location.pathname,
    page_location: window.location.href,
    view_name: PAGE_TITLES[window.location.pathname] || document.title,
    breadcrumb_path: deriveBreadcrumbFromUrl(window.location.pathname),
    ...additionalProps
  };

  // console.log(`[Analytics Event] ${category} -> ${analyticsId}`, payload);

  if (window.firebaseAnalytics && window.firebaseLogEvent) {
    // https://firebase.google.com/docs/reference/js/analytics.md#logevent_1f89527
    window.firebaseLogEvent(window.firebaseAnalytics, 'select_content', payload);
  }
};

/**
 * Logs a standard login event to Firebase Analytics.
 * @param {string} method - The authentication method used (e.g., 'Google', 'IAP')
 */
export const logLoginEvent = (method = 'Google') => {
  if (window.firebaseAnalytics && window.firebaseLogEvent) {
    window.firebaseLogEvent(window.firebaseAnalytics, 'login', { method });
  }
};

/**
 * Logs a custom logout event to Firebase Analytics.
 */
export const logLogoutEvent = () => {
  if (window.firebaseAnalytics && window.firebaseLogEvent) {
    window.firebaseLogEvent(window.firebaseAnalytics, 'logout');
  }
};

/**
 * Logs a standard tutorial_begin event to Firebase Analytics.
 */
export const logTutorialBeginEvent = () => {
  if (window.firebaseAnalytics && window.firebaseLogEvent) {
    window.firebaseLogEvent(window.firebaseAnalytics, 'tutorial_begin');
  }
};

/**
 * Logs a standard tutorial_complete event to Firebase Analytics.
 * @param {string} [status] - Optional status string for the completion event
 */
export const logTutorialCompleteEvent = (status) => {
  if (window.firebaseAnalytics && window.firebaseLogEvent) {
    window.firebaseLogEvent(window.firebaseAnalytics, 'tutorial_complete', { status });
  }
};
