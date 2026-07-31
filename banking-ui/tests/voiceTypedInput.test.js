/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import { DataChannelEvent } from '../src/utils/constants.js';
import {
  encodeTypedCustomerTurn,
  resolveTypedDelivery,
} from '../src/utils/voiceTypedInput.js';


test('encodes a bounded reliable customer turn envelope', () => {
  const payload = encodeTypedCustomerTurn({
    messageId: 'turn-12345678',
    text: '  Yes, please freeze it.  ',
    sentAt: new Date('2026-07-14T12:00:00Z'),
  });

  assert.deepEqual(JSON.parse(new TextDecoder().decode(payload)), {
    type: DataChannelEvent.CUSTOMER_TEXT_INPUT,
    message_id: 'turn-12345678',
    text: 'Yes, please freeze it.',
    sent_at: '2026-07-14T12:00:00.000Z',
  });
});

test('retryable rejection preserves the message id for idempotent retry', () => {
  const result = resolveTypedDelivery({
    type: DataChannelEvent.CUSTOMER_TEXT_REJECTED,
    message_id: 'turn-12345678',
    retryable: true,
    message: 'Try again.',
  }, 'turn-12345678');

  assert.equal(result.matched, true);
  assert.equal(result.accepted, false);
  assert.equal(result.retryMessageId, 'turn-12345678');
});

test('an unrelated acknowledgement cannot clear the pending turn', () => {
  const result = resolveTypedDelivery({
    type: DataChannelEvent.CUSTOMER_TEXT_ACCEPTED,
    message_id: 'other-turn',
  }, 'turn-12345678');

  assert.deepEqual(result, { matched: false });
});
