package com.google.cloud.fsi.audit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
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

  private static String quote(String value) {
    return '"' + value.replace("\\", "\\\\").replace("\"", "\\\"") + '"';
  }
}
