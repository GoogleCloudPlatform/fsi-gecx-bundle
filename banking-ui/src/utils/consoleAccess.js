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

export function getConsoleViewerGroupUrl() {
  return window.env?.CONSOLE_VIEWER_GROUP_JOIN_URL || import.meta.env.VITE_CONSOLE_VIEWER_GROUP_JOIN_URL;
}

// Pins a Google Cloud console link to a specific signed-in Google account.
// Without authuser, the console opens as the browser's default account, which
// for presenters with several signed-in accounts is often one that lacks
// access to the demo project. The parameter is appended rather than
// re-serializing the query, so console encodings such as BigQuery's
// `ws=!1m5...` survive intact.
export function withConsoleAccount(url, email) {
  if (!email) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}authuser=${encodeURIComponent(email)}`;
}

// Builds a console link for the Google account signed in to this app.
export function consoleUrl(url) {
  return withConsoleAccount(url, globalThis.window?.firebaseAuth?.getCurrentUser?.()?.email);
}
