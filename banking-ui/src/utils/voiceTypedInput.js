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

import { DataChannelEvent } from './constants.js';

export function encodeTypedCustomerTurn({ messageId, text, sentAt = new Date() }) {
  const normalizedText = text.trim();
  if (!messageId || !normalizedText || normalizedText.length > 1000) {
    throw new Error('Invalid typed customer turn');
  }
  return new TextEncoder().encode(JSON.stringify({
    type: DataChannelEvent.CUSTOMER_TEXT_INPUT,
    message_id: messageId,
    text: normalizedText,
    sent_at: sentAt.toISOString(),
  }));
}

export function resolveTypedDelivery(event, pendingMessageId) {
  if (!pendingMessageId || event.message_id !== pendingMessageId) {
    return { matched: false };
  }
  if (event.type === DataChannelEvent.CUSTOMER_TEXT_ACCEPTED) {
    return { matched: true, accepted: true, retryMessageId: null, error: '' };
  }
  if (event.type === DataChannelEvent.CUSTOMER_TEXT_REJECTED) {
    return {
      matched: true,
      accepted: false,
      retryMessageId: event.retryable ? event.message_id : null,
      error: event.message || 'The typed message was not accepted. Please try again.',
    };
  }
  return { matched: false };
}
