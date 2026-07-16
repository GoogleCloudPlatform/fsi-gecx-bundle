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
import { Link } from 'react-router-dom';
import { logInteractionEvent } from '../utils/analytics.js';

/**
 * A wrapper for React Router Links (or native anchors) that explicitly handles analytics tracking.
 * Prevents the global click listener from firing a duplicate event.
 */
export const AnalyticsLink = ({
  analyticsId,
  eventProperties = {},
  onClick,
  children,
  to,
  href,
  ...props
}) => {
  const handleClick = (e) => {
    let nameToLog = analyticsId;
    if (!nameToLog) {
      if (typeof children === 'string') {
        nameToLog = children;
      } else {
        nameToLog = props['aria-label'] || 'unknown_link';
      }
    }

    logInteractionEvent('link_click', nameToLog, eventProperties);

    if (onClick) {
      onClick(e);
    }
  };

  const isExternal = href && !to;

  if (isExternal) {
    return (
      <a
        href={href}
        onClick={handleClick}
        data-analytics-handled="true"
        {...props}
      >
        {children}
      </a>
    );
  }

  return (
    <Link
      to={to}
      onClick={handleClick}
      data-analytics-handled="true"
      {...props}
    >
      {children}
    </Link>
  );
};

export default AnalyticsLink;
