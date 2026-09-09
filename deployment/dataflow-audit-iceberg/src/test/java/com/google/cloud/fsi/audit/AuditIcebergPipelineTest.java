/*
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

package com.google.cloud.fsi.audit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.apache.beam.sdk.io.gcp.pubsub.PubsubMessage;
import org.joda.time.Instant;
import org.junit.jupiter.api.Test;

final class AuditIcebergPipelineTest {
  private static PubsubMessage message(String body) {
    return new PubsubMessage(body.getBytes(StandardCharsets.UTF_8), Map.of("source", "test"));
  }

  @Test
  void packagesHadoopRuntimeRequiredByIcebergCatalog() {
    assertDoesNotThrow(
        () -> Class.forName("org.apache.hadoop.shaded.com.ctc.wstx.io.InputBootstrapper"));
    assertDoesNotThrow(() -> Class.forName("org.apache.iceberg.gcp.auth.GoogleAuthManager"));
  }

  @Test
  void parsesBalancedFinancialEventAndFansOutEntries() throws Exception {
    String payload = """
        {"event_id":"event-1","schema_version":1,"transaction_id":"tx-1",
         "posted_at":"2026-07-16T12:00:00Z","currency":"USD","source_type":"TEST",
         "source_references":{"case_id":"case-1"},"entries":[
           {"entry_id":"debit-1","account_id":"account-1","direction":"DEBIT","amount_cents":500},
           {"entry_id":"credit-1","account_id":"account-2","direction":"CREDIT","amount_cents":500}]}
        """.replace("\n", "").trim();
    String envelope = """
        {"event_id":"event-1","event_type":"FINANCIAL_TRANSACTION_POSTED","schema_version":1,
         "payload":%s,"created_at":"2026-07-16T12:00:00Z","published_at":"2026-07-16T12:00:01Z"}
        """.formatted(quote(payload)).replace("\n", "").trim();

    var parsed = AuditIcebergPipeline.parseMessage(message(envelope), Instant.parse("2026-07-16T12:00:02Z"));

    assertEquals("event-1", parsed.audit.getString("event_id"));
    assertEquals(2, parsed.ledgerEntries.size());
    assertEquals(500L, parsed.ledgerEntries.get(0).getInt64("amount_cents"));
  }

  @Test
  void rejectsUnbalancedFinancialEvent() {
    String payload = """
        {"event_id":"event-1","transaction_id":"tx-1","posted_at":"2026-07-16T12:00:00Z",
         "currency":"USD","source_type":"TEST","entries":[
           {"entry_id":"debit-1","account_id":"account-1","direction":"DEBIT","amount_cents":500},
           {"entry_id":"credit-1","account_id":"account-2","direction":"CREDIT","amount_cents":499}]}
        """.replace("\n", "").trim();
    String envelope = """
        {"event_id":"event-1","event_type":"FINANCIAL_TRANSACTION_POSTED","schema_version":1,
         "payload":%s,"created_at":"2026-07-16T12:00:00Z","published_at":"2026-07-16T12:00:01Z"}
        """.formatted(quote(payload)).replace("\n", "").trim();

    assertThrows(
        IllegalArgumentException.class,
        () -> AuditIcebergPipeline.parseMessage(message(envelope), Instant.now()));
  }

  @Test
  void deadLetterMessageAlwaysHasCoderCompatibleMessageId() {
    PubsubMessage malformed = message("{\"missing\":\"event_id\"}");

    PubsubMessage deadLetter =
        AuditIcebergPipeline.deadLetterMessage(
            malformed, new IllegalArgumentException("missing string field: event_id"));

    assertNotNull(deadLetter.getMessageId());
    assertEquals("validate-envelope-v1", deadLetter.getAttribute("dlq_stage"));
    assertEquals("missing string field: event_id", deadLetter.getAttribute("dlq_error"));
    assertEquals("{\"missing\":\"event_id\"}", new String(deadLetter.getPayload(), StandardCharsets.UTF_8));
  }

  private static String v2Payload(String currency, String amount, String entryCurrency) {
    return """
        {"event_id":"event-v2","schema_version":2,"transaction_id":"tx-v2",
         "posted_at":"2026-09-08T12:00:00Z","currency_code":"%s","source_type":"BILL_PAYMENT",
         "source_references":{"credit_account_id":"card-1"},"entries":[
           {"entry_id":"debit-v2","account_id":"account-1","direction":"DEBIT",
            "money":{"amount_minor":%s,"currency_code":"%s"}},
           {"entry_id":"credit-v2","account_id":"account-2","direction":"CREDIT",
            "money":{"amount_minor":%s,"currency_code":"%s"}}]}
        """.formatted(currency, amount, entryCurrency, amount, entryCurrency);
  }

  private static String v2Envelope(String payload) {
    return """
        {"event_id":"event-v2","event_type":"FINANCIAL_TRANSACTION_POSTED","schema_version":2,
         "payload":%s,"created_at":"2026-09-08T12:00:00Z","published_at":"2026-09-08T12:00:01Z"}
        """.formatted(quote(payload.replace("\n", "")));
  }

  @Test
  void parsesV2MoneyWithoutChangingRawHistoryOrIdentity() throws Exception {
    for (String currency : new String[]{"USD", "MXN", "JPY", "BHD"}) {
      String payload = v2Payload(currency, "9007199254740991", currency).replace("\n", "");
      var parsed = AuditIcebergPipeline.parseMessage(message(v2Envelope(payload)), Instant.now());
      assertEquals(payload, parsed.audit.getString("payload"));
      assertEquals("event-v2", parsed.audit.getString("event_id"));
      assertEquals(2, parsed.ledgerEntries.size());
      assertEquals(currency, parsed.ledgerEntries.get(0).getString("currency"));
      // This is a retained physical storage name, not the public Money contract.
      assertEquals(9007199254740991L, parsed.ledgerEntries.get(0).getInt64("amount_cents"));
      assertEquals("debit-v2", parsed.ledgerEntries.get(0).getString("entry_id"));
    }
  }

  @Test
  void rejectsMalformedV2MoneyAndCurrencyMismatch() {
    for (String amount : new String[]{"1.5", "true", "0", "-1", "9007199254740992", "\"125\""}) {
      assertThrows(IllegalArgumentException.class, () -> AuditIcebergPipeline.parseMessage(
          message(v2Envelope(v2Payload("USD", amount, "USD"))), Instant.now()));
    }
    for (String currency : new String[]{"usd", "EUR", "MXN"}) {
      assertThrows(IllegalArgumentException.class, () -> AuditIcebergPipeline.parseMessage(
          message(v2Envelope(v2Payload("USD", "125", currency))), Instant.now()));
    }
    assertThrows(IllegalArgumentException.class, () -> AuditIcebergPipeline.parseMessage(
        message(v2Envelope(v2Payload("USD", "125", "USD")).replace("schema_version\":2", "schema_version\":3")), Instant.now()));
  }

  @Test
  void rejectsDuplicateEntryIdentityAndEnvelopeMismatch() {
    String payload = v2Payload("MXN", "125", "MXN");
    assertThrows(IllegalArgumentException.class, () -> AuditIcebergPipeline.parseMessage(
        message(v2Envelope(payload.replace("credit-v2", "debit-v2"))), Instant.now()));
    assertThrows(IllegalArgumentException.class, () -> AuditIcebergPipeline.parseMessage(
        message(v2Envelope(payload.replace("event-v2", "different-event"))), Instant.now()));
  }

  @Test
  void mixedHistoricalAndCanonicalReplayKeepsStableIdsAndBalances() throws Exception {
    String canonical = v2Payload("MXN", "125", "MXN");
    String historical = canonical.replace("event-v2", "event-v1").replace("tx-v2", "tx-v1")
        .replace("debit-v2", "debit-v1").replace("credit-v2", "credit-v1")
        .replace("\"schema_version\":2", "\"schema_version\":1")
        .replace("\"currency_code\":\"MXN\"", "\"currency\":\"USD\"")
        .replace("\"money\":{\"amount_minor\":125,\"currency\":\"USD\"}", "\"amount_cents\":125");
    String oldEnvelope = v2Envelope(historical).replace("event-v2", "event-v1")
        .replace("\"schema_version\":2", "\"schema_version\":1");
    var auditIds = new java.util.HashSet<String>();
    var entryIds = new java.util.HashSet<String>();
    var totals = new java.util.HashMap<String, Long>();
    for (String envelope : new String[]{oldEnvelope, v2Envelope(canonical), oldEnvelope, v2Envelope(canonical)}) {
      var parsed = AuditIcebergPipeline.parseMessage(message(envelope), Instant.now());
      auditIds.add(parsed.audit.getString("event_id"));
      for (var entry : parsed.ledgerEntries) {
        if (entryIds.add(entry.getString("entry_id"))) {
          long signed = entry.getInt64("amount_cents") * (entry.getString("direction").equals("DEBIT") ? 1 : -1);
          totals.merge(entry.getString("currency"), signed, Long::sum);
        }
      }
    }
    assertEquals(2, auditIds.size());
    assertEquals(4, entryIds.size());
    assertEquals(Map.of("USD", 0L, "MXN", 0L), totals);
  }

  private static String quote(String value) {
    return '"' + value.replace("\\", "\\\\").replace("\"", "\\\"") + '"';
  }
}
