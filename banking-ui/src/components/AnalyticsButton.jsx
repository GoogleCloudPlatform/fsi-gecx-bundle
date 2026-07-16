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

import React from 'react';
import { useLocation } from 'react-router-dom';
import { logInteractionEvent } from '../utils/analytics.js';

/**
 * A wrapper for native buttons that explicitly handles analytics tracking.
 * Prevents the global click listener from firing a duplicate event.
 */
export const AnalyticsButton = ({
  trackingName,
  eventProperties = {},
  onClick,
  children,
  ...props
}) => {
  const location = useLocation();

  const handleClick = (e) => {
    // Determine the name to log: prefer trackingName, fallback to children text or aria-label
    let nameToLog = trackingName;
    if (!nameToLog) {
      if (typeof children === 'string') {
        nameToLog = children;
      } else {
        nameToLog = props['aria-label'] || 'unknown_button';
      }
    }

    const enhancedProperties = {
      ...eventProperties,
      page_path: location.pathname
    };

    logInteractionEvent('button_click', nameToLog, enhancedProperties);

    // Call original onClick if provided
    if (onClick) {
      onClick(e);
    }
  };

  return (
    <button
      onClick={handleClick}
      data-analytics-handled="true"
      {...props}
    >
      {children}
    </button>
  );
};

export default AnalyticsButton;
