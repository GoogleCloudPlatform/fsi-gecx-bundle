package com.google.cloud.fsi.audit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.Serializable;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.apache.beam.sdk.Pipeline;
import org.apache.beam.sdk.io.gcp.pubsub.PubsubIO;
import org.apache.beam.sdk.io.gcp.pubsub.PubsubMessage;
import org.apache.beam.sdk.managed.Managed;
import org.apache.beam.sdk.extensions.gcp.options.GcpOptions;
import org.apache.beam.sdk.options.Default;
import org.apache.beam.sdk.options.Description;
import org.apache.beam.sdk.options.PipelineOptionsFactory;
import org.apache.beam.sdk.options.StreamingOptions;
import org.apache.beam.sdk.options.Validation;
import org.apache.beam.sdk.options.ValueProvider;
import org.apache.beam.sdk.schemas.Schema;
import org.apache.beam.sdk.transforms.DoFn;
import org.apache.beam.sdk.transforms.ParDo;
import org.apache.beam.sdk.values.PCollection;
import org.apache.beam.sdk.values.PCollectionTuple;
import org.apache.beam.sdk.values.Row;
import org.apache.beam.sdk.values.TupleTag;
import org.apache.beam.sdk.values.TupleTagList;
import org.joda.time.Instant;

public final class AuditIcebergPipeline {
  private static final ObjectMapper MAPPER = new ObjectMapper();
  static final TupleTag<Row> AUDIT_TAG = new TupleTag<>() {};
  static final TupleTag<Row> LEDGER_TAG = new TupleTag<>() {};
  static final TupleTag<PubsubMessage> DLQ_TAG = new TupleTag<>() {};

  static final Schema AUDIT_SCHEMA =
      Schema.builder()
          .addStringField("event_id")
          .addStringField("event_type")
          .addInt64Field("schema_version")
          .addStringField("payload")
          .addDateTimeField("source_created_at")
          .addDateTimeField("published_at")
          .addDateTimeField("ingested_at")
          .addNullableField("transport_message_id", Schema.FieldType.STRING)
          .addNullableField("transport_attributes", Schema.FieldType.STRING)
          .build();

  static final Schema LEDGER_SCHEMA =
      Schema.builder()
          .addStringField("entry_id")
          .addStringField("event_id")
          .addStringField("transaction_id")
          .addStringField("account_id")
          .addStringField("direction")
          .addInt64Field("amount_cents")
          .addStringField("currency")
          .addStringField("source_type")
          .addNullableField("source_references", Schema.FieldType.STRING)
          .addDateTimeField("posted_at")
          .addDateTimeField("source_created_at")
          .addDateTimeField("published_at")
          .addDateTimeField("ingested_at")
          .build();

  public interface Options extends StreamingOptions, GcpOptions {
    @Description("Pub/Sub subscription containing relay envelopes")
    @Validation.Required
    ValueProvider<String> getInputSubscription();
    void setInputSubscription(ValueProvider<String> value);

    @Description("Pub/Sub topic for malformed or contract-invalid envelopes")
    @Validation.Required
    ValueProvider<String> getDlqTopic();
    void setDlqTopic(ValueProvider<String> value);

    @Description("Lakehouse Iceberg REST catalog URI")
    @Default.String("https://biglake.googleapis.com/iceberg/v1/restcatalog")
    String getCatalogUri();
    void setCatalogUri(String value);

    @Description("BigLake warehouse identifier, bl://projects/PROJECT/catalogs/CATALOG")
    @Validation.Required
    String getWarehouse();
    void setWarehouse(String value);

    @Description("Local Managed I/O catalog name")
    @Default.String("nova_audit")
    String getCatalogName();
    void setCatalogName(String value);

    @Description("Iceberg audit destination")
    @Default.String("compliance_audit.audit_events")
    String getAuditTable();
    void setAuditTable(String value);

    @Description("Iceberg financial entry destination")
    @Default.String("financial_ledger.account_ledger_entries")
    String getLedgerTable();
    void setLedgerTable(String value);

    @Description("Seconds between batched Iceberg commits")
    @Default.Integer(60)
    Integer getCommitFrequencySeconds();
    void setCommitFrequencySeconds(Integer value);
  }

  static final class ParsedMessage implements Serializable {
    final Row audit;
    final List<Row> ledgerEntries;

    ParsedMessage(Row audit, List<Row> ledgerEntries) {
      this.audit = audit;
      this.ledgerEntries = ledgerEntries;
    }
  }

  static ParsedMessage parseMessage(PubsubMessage message, Instant ingestedAt) throws Exception {
    JsonNode envelope = MAPPER.readTree(message.getPayload());
    String eventId = requiredText(envelope, "event_id");
    String eventType = requiredText(envelope, "event_type");
    long schemaVersion = requiredLong(envelope, "schema_version");
    if (schemaVersion < 1) {
      throw new IllegalArgumentException("schema_version must be positive");
    }
    String payload = requiredText(envelope, "payload");
    Instant sourceCreatedAt = parseTimestamp(requiredText(envelope, "created_at"));
    Instant publishedAt = parseTimestamp(requiredText(envelope, "published_at"));

    List<Row> ledger = new ArrayList<>();
    if ("FINANCIAL_TRANSACTION_POSTED".equals(eventType)) {
      JsonNode financial = MAPPER.readTree(payload);
      String payloadEventId = requiredText(financial, "event_id");
      if (!eventId.equals(payloadEventId)) {
        throw new IllegalArgumentException("financial payload event_id differs from envelope");
      }
      String transactionId = requiredText(financial, "transaction_id");
      String currency = requiredText(financial, "currency");
      String sourceType = requiredText(financial, "source_type");
      Instant postedAt = parseTimestamp(requiredText(financial, "posted_at"));
      JsonNode sourceReferences = financial.path("source_references");
      JsonNode entries = financial.path("entries");
      if (!entries.isArray() || entries.isEmpty()) {
        throw new IllegalArgumentException("financial event requires entries");
      }
      long debits = 0L;
      long credits = 0L;
      for (JsonNode entry : entries) {
        String direction = requiredText(entry, "direction").toUpperCase();
        long amount = requiredLong(entry, "amount_cents");
        if (amount <= 0 || !(direction.equals("DEBIT") || direction.equals("CREDIT"))) {
          throw new IllegalArgumentException("invalid financial entry amount or direction");
        }
        if (direction.equals("DEBIT")) {
          debits = Math.addExact(debits, amount);
        } else {
          credits = Math.addExact(credits, amount);
        }
        ledger.add(
            Row.withSchema(LEDGER_SCHEMA)
                .addValues(
                    requiredText(entry, "entry_id"),
                    eventId,
                    transactionId,
                    requiredText(entry, "account_id"),
                    direction,
                    amount,
                    currency,
                    sourceType,
                    sourceReferences.isMissingNode() ? null : MAPPER.writeValueAsString(sourceReferences),
                    postedAt,
                    sourceCreatedAt,
                    publishedAt,
                    ingestedAt)
                .build());
      }
      if (debits != credits) {
        throw new IllegalArgumentException(
            "unbalanced financial event debits=" + debits + " credits=" + credits);
      }
    }

    Row audit =
        Row.withSchema(AUDIT_SCHEMA)
            .addValues(
                eventId,
                eventType,
                schemaVersion,
                payload,
                sourceCreatedAt,
                publishedAt,
                ingestedAt,
                message.getMessageId(),
                MAPPER.writeValueAsString(message.getAttributeMap()))
            .build();
    return new ParsedMessage(audit, ledger);
  }

  private static String requiredText(JsonNode node, String field) {
    JsonNode value = node.get(field);
    if (value == null || !value.isTextual() || value.asText().isBlank()) {
      throw new IllegalArgumentException("missing string field: " + field);
    }
    return value.asText();
  }

  private static long requiredLong(JsonNode node, String field) {
    JsonNode value = node.get(field);
    if (value == null || !value.canConvertToLong()) {
      throw new IllegalArgumentException("missing integer field: " + field);
    }
    return value.longValue();
  }

  private static Instant parseTimestamp(String value) {
    return new Instant(OffsetDateTime.parse(value).toInstant().toEpochMilli());
  }

  static final class ParseEvents extends DoFn<PubsubMessage, Row> {
    @ProcessElement
    public void process(@Element PubsubMessage message, MultiOutputReceiver output) {
      try {
        ParsedMessage parsed = parseMessage(message, Instant.now());
        output.get(AUDIT_TAG).output(parsed.audit);
        parsed.ledgerEntries.forEach(output.get(LEDGER_TAG)::output);
      } catch (Exception error) {
        output.get(DLQ_TAG).output(deadLetterMessage(message, error));
      }
    }
  }

  static PubsubMessage deadLetterMessage(PubsubMessage message, Exception error) {
    Map<String, String> attributes = new HashMap<>(message.getAttributeMap());
    String detail = error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    attributes.put("dlq_error", detail.substring(0, Math.min(detail.length(), 512)));
    attributes.put("dlq_stage", "validate-envelope-v1");

    // readMessagesWithAttributesAndMessageId assigns a coder that requires a
    // non-null message ID on every output branch. Dataflow can still surface a
    // null source ID, so use a deterministic payload-derived fallback. Pub/Sub
    // assigns a new server-side ID when this message is written to the DLQ.
    String messageId = message.getMessageId();
    if (messageId == null || messageId.isBlank()) {
      messageId = "dlq-" + Base64.getUrlEncoder().withoutPadding()
          .encodeToString(java.util.Arrays.copyOf(message.getPayload(), Math.min(18, message.getPayload().length)));
    }
    return new PubsubMessage(message.getPayload(), attributes, messageId);
  }

  private static Map<String, String> catalogProperties(Options options) {
    Map<String, String> properties = new LinkedHashMap<>();
    properties.put("type", "rest");
    properties.put("uri", options.getCatalogUri());
    properties.put("warehouse", options.getWarehouse());
    properties.put("header.x-goog-user-project", options.getProject());
    properties.put("rest.auth.type", "org.apache.iceberg.gcp.auth.GoogleAuthManager");
    properties.put("io-impl", "org.apache.iceberg.gcp.gcs.GCSFileIO");
    properties.put("header.X-Iceberg-Access-Delegation", "vended-credentials");
    properties.put("gcs.oauth2.refresh-credentials-endpoint", "https://oauth2.googleapis.com/token");
    properties.put("rest-metrics-reporting-enabled", "false");
    return properties;
  }

  private static Map<String, Object> writeConfig(
      Options options, String table, Map<String, String> catalogProperties) {
    Map<String, Object> config = new LinkedHashMap<>();
    config.put("table", table);
    config.put("catalog_name", options.getCatalogName());
    config.put("catalog_properties", catalogProperties);
    config.put("triggering_frequency_seconds", options.getCommitFrequencySeconds());
    return config;
  }

  public static void main(String[] args) {
    Options options = PipelineOptionsFactory.fromArgs(args).withValidation().as(Options.class);
    options.setStreaming(true);
    Pipeline pipeline = Pipeline.create(options);

    PCollection<PubsubMessage> messages =
        pipeline.apply(
            "ReadAuditEvents",
            PubsubIO.readMessagesWithAttributesAndMessageId()
                .fromSubscription(options.getInputSubscription()));
    PCollectionTuple parsed =
        messages.apply(
            "ValidateAndFanOut",
            ParDo.of(new ParseEvents())
                .withOutputTags(AUDIT_TAG, TupleTagList.of(LEDGER_TAG).and(DLQ_TAG)));

    PCollection<Row> auditRows = parsed.get(AUDIT_TAG).setRowSchema(AUDIT_SCHEMA);
    PCollection<Row> ledgerRows = parsed.get(LEDGER_TAG).setRowSchema(LEDGER_SCHEMA);
    parsed
        .get(DLQ_TAG)
        .apply("WriteMalformedToDlq", PubsubIO.writeMessages().to(options.getDlqTopic()));

    Map<String, String> catalogProperties = catalogProperties(options);
    auditRows.apply(
        "WriteAuditIceberg",
        Managed.write(Managed.ICEBERG)
            .withConfig(writeConfig(options, options.getAuditTable(), catalogProperties)));
    ledgerRows.apply(
        "WriteLedgerIceberg",
        Managed.write(Managed.ICEBERG)
            .withConfig(writeConfig(options, options.getLedgerTable(), catalogProperties)));

    pipeline.run();
  }

  private AuditIcebergPipeline() {}
}
