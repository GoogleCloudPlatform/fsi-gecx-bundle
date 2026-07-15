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

export const hasReleaseNotes = () => 
  window.env?.HAS_RELEASE_NOTES === true || window.env?.HAS_RELEASE_NOTES === 'true';

/**
 * Format the build time from the environment variable
 */
export const getFormattedBuildTime = () => {
  if (window.env?.BUILD_VERSION === 'local-dev') {
    window.env.BUILD_TIME = Date.now();
  }
  if (!window.env?.BUILD_TIME || window.env.BUILD_TIME === '${BUILD_TIME}' || window.env.BUILD_TIME === '0') return 'unknown';
  const buildTimeMs = parseInt(window.env.BUILD_TIME, 10);
  if (isNaN(buildTimeMs)) return 'unknown';
  return new Date(buildTimeMs).toLocaleString();
};
