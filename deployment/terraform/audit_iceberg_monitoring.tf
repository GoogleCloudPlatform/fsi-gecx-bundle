resource "google_logging_metric" "audit_outbox_relay_failures" {
  name        = "audit_outbox_relay_failures"
  description = "Unrecoverable failures from the bounded AlloyDB audit outbox relay."
  filter      = "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"audit-outbox-relay\" AND textPayload:\"audit_outbox_relay_failed\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_monitoring_alert_policy" "audit_iceberg_subscription_age" {
  display_name = "Audit Iceberg subscription oldest message exceeds 10 minutes"
  combiner     = "OR"

  conditions {
    display_name = "Oldest unacknowledged audit event"
    condition_threshold {
      filter          = "resource.type = \"pubsub_subscription\" AND resource.label.subscription_id = \"${google_pubsub_subscription.audit_events_iceberg_sub.name}\" AND metric.type = \"pubsub.googleapis.com/subscription/oldest_unacked_message_age\""
      comparison      = "COMPARISON_GT"
      threshold_value = 600
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  documentation {
    content   = "The Dataflow Iceberg sink is not consuming audit events within the ten-minute SLO. Inspect the Dataflow job, Pub/Sub subscription, and catalog authorization."
    mime_type = "text/markdown"
  }
}

resource "google_monitoring_alert_policy" "audit_iceberg_subscription_backlog" {
  display_name = "Audit Iceberg subscription backlog exceeds 1,000 events"
  combiner     = "OR"

  conditions {
    display_name = "Unacknowledged audit event backlog"
    condition_threshold {
      filter          = "resource.type = \"pubsub_subscription\" AND resource.label.subscription_id = \"${google_pubsub_subscription.audit_events_iceberg_sub.name}\" AND metric.type = \"pubsub.googleapis.com/subscription/num_undelivered_messages\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1000
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "audit_iceberg_dlq" {
  display_name = "Audit Iceberg dead-letter queue is non-empty"
  combiner     = "OR"

  conditions {
    display_name = "Malformed audit events await review"
    condition_threshold {
      filter          = "resource.type = \"pubsub_subscription\" AND resource.label.subscription_id = \"${google_pubsub_subscription.audit_events_dlq_sub.name}\" AND metric.type = \"pubsub.googleapis.com/subscription/num_undelivered_messages\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "60s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "dataflow_job_failed" {
  display_name = "Dataflow streaming job failed"
  combiner     = "OR"

  conditions {
    display_name = "Dataflow job failure signal"
    condition_threshold {
      filter          = "resource.type = \"dataflow_job\" AND metric.type = \"dataflow.googleapis.com/job/is_failed\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "audit_outbox_relay_failed" {
  display_name = "Audit outbox relay failed"
  combiner     = "OR"

  conditions {
    display_name = "Relay failure log entry"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_job\" AND metric.type = \"logging.googleapis.com/user/${google_logging_metric.audit_outbox_relay_failures.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
}
