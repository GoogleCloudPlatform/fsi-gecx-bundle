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

import axios from 'axios';

const backendUrl = window.env?.BANKING_API_URL || import.meta.env.VITE_BANKING_API_URL || "http://localhost:8080";

const api = axios.create({
  baseURL: backendUrl,
});

api.interceptors.request.use(
  async (config) => {
    // Only intercept and add token for relative backend API calls
    const isAbsolute = config.url.startsWith('http://') || config.url.startsWith('https://');
    const isBackend = !isAbsolute || config.url.startsWith(backendUrl);

    if (isBackend) {
      if (window.firebaseAuth && typeof window.firebaseAuth.getCurrentUser === 'function') {
        const user = window.firebaseAuth.getCurrentUser();
        if (user) {
          try {
            const token = await user.getIdToken();
            config.headers.Authorization = `Bearer ${token}`;
          } catch (error) {
            console.error('Error getting Firebase ID token:', error);
          }
        }
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export function getBackendApiUrl() {
  return backendUrl;
}

export async function getBackendAuthHeaders(initialHeaders = {}) {
  const headers = { ...initialHeaders };
  if (window.firebaseAuth && typeof window.firebaseAuth.getCurrentUser === 'function') {
    const user = window.firebaseAuth.getCurrentUser();
    if (user) {
      try {
        const token = await user.getIdToken();
        headers.Authorization = `Bearer ${token}`;
      } catch (error) {
        console.error('Error getting Firebase ID token:', error);
      }
    }
  }
  return headers;
}

// ---------------- API Operations ----------------

// Profile
export async function getCustomerProfile() {
  const res = await api.get('profile');
  return res.data;
}

export async function getCustomersList() {
  const res = await api.get('profile/customers');
  return res.data;
}

export async function updateCustomerProfile(profileData) {
  const res = await api.put('profile', profileData);
  return res.data;
}

export async function createApplication(applicationData) {
  const res = await api.post('applications', applicationData);
  return res.data;
}

// Secure Messaging (Customer)
export async function getMessages() {
  const res = await api.get('secure-messaging');
  return res.data;
}

export async function markMessagesRead(unreadMsgIds) {
  const res = await api.post('secure-messaging/read', unreadMsgIds);
  return res.data;
}

export async function createMessage(messageData) {
  const res = await api.post('secure-messaging', messageData);
  return res.data;
}

export async function deleteThread(tid) {
  const res = await api.delete(`secure-messaging/threads/${tid}`);
  return res.data;
}

export async function deleteMessage(msgId) {
  const res = await api.delete(`secure-messaging/messages/${msgId}`);
  return res.data;
}

// Secure Messaging (Admin)
export async function getCustomerMessages(customerId) {
  const res = await api.get(`secure-messaging/admin/customer/${customerId}`);
  return res.data;
}

export async function markMessagesAgentRead({ message_ids, user_id }) {
  const res = await api.post('secure-messaging/admin/read', { message_ids, user_id });
  return res.data;
}

export async function adminDeleteThread(tid, userId) {
  const res = await api.delete(`secure-messaging/admin/threads/${tid}?user_id=${userId}`);
  return res.data;
}

export async function adminDeleteMessage(msgId, userId) {
  const res = await api.delete(`secure-messaging/admin/messages/${msgId}?user_id=${userId}`);
  return res.data;
}

// Notifications
export async function registerDeviceToken(deviceToken) {
  const res = await api.post('notification/device', { device_token: deviceToken });
  return res.data;
}

export async function unregisterDeviceToken(deviceToken) {
  const res = await api.delete(`notification/device?device_token=${encodeURIComponent(deviceToken)}`);
  return res.data;
}

export async function sendNotification(payload) {
  const res = await api.post('notification/send', payload);
  return res.data;
}

// Artifact Upload & Validation
export async function uploadFileToGcs(signedUrl, file, mimeType) {
  const res = await api.put(signedUrl, file, {
    headers: {
      'Content-Type': file.type || mimeType
    }
  });
  return res.data;
}

export async function uploadAndValidateArtifact(artifactData) {
  const res = await api.post('artifacts/upload-and-validate', artifactData);
  return res.data;
}

// Auth Tokens
export async function getCxasAuthToken() {
  const res = await api.post('cxas/auth/token');
  return res.data;
}

export async function getCcaiAuthToken() {
  const res = await api.post('ccai/auth/token', {});
  return res.data;
}

// Search
export async function findAnswer({ query, query_id, session }) {
  const res = await api.post('answers', { query, query_id, session });
  return res.data;
}

export async function performSearch({ query }) {
  const res = await api.post('search', { query });
  return res.data;
}

export async function getCreditCardAccount(targetCustomerId = null, fallback = true) {
  const params = {};
  if (targetCustomerId) params.target_customer_id = targetCustomerId;
  if (fallback === false) params.fallback = 'false';
  const res = await api.get('credit-card/account', { params });
  return res.data;
}

export async function getCreditCardTransactions(targetCustomerId = null) {
  const params = targetCustomerId ? { target_customer_id: targetCustomerId } : {};
  const res = await api.get('credit-card/transactions', { params });
  return res.data;
}

export async function acknowledgeFraudAlert() {
  const res = await api.post('credit-card/fraud-alert/acknowledge');
  return res.data;
}

export async function getCreditCardVoiceToken(mode = 'audio') {
  const res = await api.get('credit-card/voice/token', { params: { mode } });
  return res.data;
}

export async function getCreditCardVoiceContext() {
  const res = await api.get('credit-card/voice/context');
  return res.data;
}

// Support Handoff Escalations
export async function getPendingEscalations() {
  const res = await api.get('support/escalations');
  return res.data;
}

export async function getAgentVoiceToken(roomName) {
  const res = await api.post(`support/token?room_name=${encodeURIComponent(roomName)}`);
  return res.data;
}

export async function completeEscalation(escalationId) {
  const res = await api.post(`support/escalations/${escalationId}/complete`);
  return res.data;
}

export async function reverseCreditCardFee(transactionId, targetCustomerId = null) {
  const params = targetCustomerId ? { target_customer_id: targetCustomerId } : {};
  const res = await api.post('credit-card/fee/reverse', null, {
    params: {
      transaction_id: transactionId,
      ...params
    }
  });
  return res.data;
}

export async function updateCreditCardLimit(requestedLimitCents, targetCustomerId = null) {
  const params = targetCustomerId ? { target_customer_id: targetCustomerId } : {};
  const res = await api.post('credit-card/limit', null, {
    params: {
      requested_limit_cents: requestedLimitCents,
      ...params
    }
  });
  return res.data;
}

export async function blockCreditCard(cardToken, targetCustomerId = null) {
  const params = targetCustomerId ? { target_customer_id: targetCustomerId } : {};
  const res = await api.post('credit-card/block', null, {
    params: {
      card_token: cardToken,
      ...params
    }
  });
  return res.data;
}

export async function resetDatabase(purgeAuditLogs = false, purgeDataLake = false) {
  const res = await api.post(`internal/debug/reset-db?purge_audit_logs=${purgeAuditLogs}&purge_data_lake=${purgeDataLake}`);
  return res.data;
}

export async function getSystemSettings() {
  const res = await api.get('settings');
  return res.data;
}

export async function updateSystemSettings(payload) {
  const res = await api.post('settings', payload);
  return res.data;
}

export async function getLocations({ lat, lng, address, type }) {
  const params = {};
  if (lat !== undefined && lat !== null) params.lat = lat;
  if (lng !== undefined && lng !== null) params.lng = lng;
  if (address) params.address = address;
  if (type) params.type = type;
  const res = await api.get('locator', { params });
  return res.data;
}

export async function createDepositAccount(depositData) {
  const idempotencyKey = 'IDEMP-UI-' + Math.random().toString(36).substring(2, 15) + '-' + Date.now();
  const res = await api.post('v1/accounts/deposit', depositData, {
    headers: {
      'X-Idempotency-Key': idempotencyKey
    }
  });
  return res.data;
}

export async function provisionMyDemo() {
  const res = await api.post('v1/simulation/provision-my-demo');
  return res.data;
}

export async function resetMyDemo() {
  const res = await api.post('v1/simulation/reset-my-demo');
  return res.data;
}

export async function triggerSpendSurge() {
  const res = await api.post('v1/simulation/surge');
  return res.data;
}

export async function injectFraudAnomaly() {
  const res = await api.post('v1/simulation/inject-anomaly');
  return res.data;
}

export async function injectLateFee() {
  const res = await api.post('v1/simulation/inject-late-fee');
  return res.data;
}

export async function getGlobalStream() {
  const res = await api.get('v1/simulation/global-stream');
  return res.data;
}

export async function getLakehouseStream() {
  const res = await api.get('v1/simulation/lakehouse-stream');
  return res.data;
}

export async function getCdcStatus() {
  const res = await api.get('v1/simulation/cdc-status');
  return res.data;
}

export async function getAccountsSummary() {
  const res = await api.get('v1/accounts/summary');
  return res.data;
}

export async function payCreditCard(paymentData) {
  const res = await api.post('v1/credit-card/pay', paymentData);
  return res.data;
}

export async function getDepositTransactions(accountId) {
  const res = await api.get(`v1/accounts/${accountId}/transactions`);
  return res.data;
}

export default api;
