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


export const inputStyle = 'w-full border border-slate-300 dark:border-slate-600 rounded-lg p-2 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 disabled:bg-slate-100 dark:disabled:bg-slate-800';
export const buttonStyle = 'rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-800';
export const primaryButtonStyle = `${buttonStyle} bg-emerald-600 text-white hover:bg-emerald-700 dark:hover:bg-emerald-700`;

export const shortDigest = (digest) => (digest ? digest.slice(0, 7) : '—');
