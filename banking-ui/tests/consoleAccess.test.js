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

import test from 'node:test';
import assert from 'node:assert/strict';
import { withConsoleAccount, consoleUrl } from '../src/utils/consoleAccess.js';

const BQ_URL = 'https://console.cloud.google.com/bigquery?project=fsi-demo-1841&ws=!1m5!1m4!3m2!1sfsi-demo-1841!2soltp_cdc!23sTREE_NODE_SELECTION';

test('appends authuser without re-encoding existing console params', () => {
  assert.equal(
    withConsoleAccount(BQ_URL, 'presenter@google.com'),
    `${BQ_URL}&authuser=presenter%40google.com`,
  );
});

test('uses ? when the console URL has no query string', () => {
  assert.equal(
    withConsoleAccount('https://console.cloud.google.com/bigquery', 'a@google.com'),
    'https://console.cloud.google.com/bigquery?authuser=a%40google.com',
  );
});

test('leaves the URL unchanged without an email', () => {
  assert.equal(withConsoleAccount(BQ_URL, undefined), BQ_URL);
  assert.equal(withConsoleAccount(BQ_URL, ''), BQ_URL);
});

test('consoleUrl uses the signed-in Firebase user and tolerates its absence', () => {
  const previous = globalThis.window;
  try {
    globalThis.window = undefined;
    assert.equal(consoleUrl(BQ_URL), BQ_URL);
    globalThis.window = { firebaseAuth: { getCurrentUser: () => null } };
    assert.equal(consoleUrl(BQ_URL), BQ_URL);
    globalThis.window = { firebaseAuth: { getCurrentUser: () => ({ email: 'eladsh@google.com' }) } };
    assert.equal(consoleUrl(BQ_URL), `${BQ_URL}&authuser=eladsh%40google.com`);
  } finally {
    globalThis.window = previous;
  }
});
