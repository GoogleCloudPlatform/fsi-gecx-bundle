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

const gcipCloudFunctions = require('gcip-cloud-functions');
const authClient = new gcipCloudFunctions.Auth();

const ALLOWED_DOMAINS = ['google.com', 'gcp.altostrat.com', 'gcp.solutions'];

exports.beforeCreate = authClient.functions().beforeCreateHandler((user, context) => {
  const email = user ? user.email : null;

  if (!email) {
    throw new gcipCloudFunctions.https.HttpsError(
      'invalid-argument',
      'Email is required for authentication.'
    );
  }

  const domain = email.split('@')[1];
  if (!domain || !ALLOWED_DOMAINS.includes(domain.toLowerCase())) {
    throw new gcipCloudFunctions.https.HttpsError(
      'invalid-argument',
      `Login is restricted. Domain ${domain || 'unknown'} is not allowed.`
    );
  }
});

exports.beforeSignIn = authClient.functions().beforeSignInHandler((user, context) => {
  const email = user ? user.email : null;

  if (!email) {
    throw new gcipCloudFunctions.https.HttpsError(
      'invalid-argument',
      'Email is required for authentication.'
    );
  }

  const domain = email.split('@')[1];
  if (!domain || !ALLOWED_DOMAINS.includes(domain.toLowerCase())) {
    throw new gcipCloudFunctions.https.HttpsError(
      'invalid-argument',
      `Login is restricted. Domain ${domain || 'unknown'} is not allowed.`
    );
  }
});
