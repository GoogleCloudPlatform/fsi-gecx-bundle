/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
/* global importScripts, firebase */

importScripts('https://www.gstatic.com/firebasejs/12.16.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/12.16.0/firebase-messaging-compat.js');
importScripts('/fbConfig.js');

// Initialize Firebase app in service worker
firebase.initializeApp(self.firebaseConfig);

// Retrieve Firebase Messaging
const messaging = firebase.messaging();

// Handle background messages
messaging.onBackgroundMessage((payload) => {
  console.log('[firebase-messaging-sw.js] Received background message ', payload);
  
  // Only show a visual notification if the message contains a notification payload block
  if (payload.notification) {
    const notificationTitle = payload.notification.title || 'Push Notification';
    const notificationOptions = {
      body: payload.notification.body || 'New message received.',
      icon: '/favicon.svg',
      data: payload.data
    };
    self.registration.showNotification(notificationTitle, notificationOptions);
  }
});
