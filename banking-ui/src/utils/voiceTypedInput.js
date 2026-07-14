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
