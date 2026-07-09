-- Rehearsal proof query for the fraud alert voice mitigation demo.
-- Bind :fraud_alert_id to the alert id shown in the admin simulation or voice logs.
WITH selected_alert AS (
  SELECT
    id,
    customer_id,
    credit_account_id,
    card_id,
    card_last_four,
    status,
    remediation_status,
    triage_summary,
    selected_disputed_authorization_ids,
    selected_disputed_transaction_ids,
    provisional_credit_cents,
    replacement_card_id,
    triage_message_thread_id,
    triage_message_id,
    created_at,
    triaged_at,
    resolved_at
  FROM operations.fraud_alerts
  WHERE id = :fraud_alert_id
),
actions AS (
  SELECT
    fraud_alert_id,
    jsonb_agg(
      jsonb_build_object(
        'action_type', action_type,
        'status', status,
        'idempotency_key', idempotency_key,
        'request_payload', request_payload,
        'result_payload', result_payload,
        'created_at', created_at,
        'completed_at', completed_at
      )
      ORDER BY created_at
    ) AS action_history
  FROM operations.fraud_case_actions
  WHERE fraud_alert_id = :fraud_alert_id
  GROUP BY fraud_alert_id
),
audit_events AS (
  SELECT
    jsonb_agg(
      jsonb_build_object(
        'event_type', event_type,
        'event_id', event_id,
        'created_at', created_at,
        'payload', payload::jsonb
      )
      ORDER BY created_at
    ) AS audit_history
  FROM audit.audit_outbox
  WHERE payload::jsonb ->> 'fraud_alert_id' = :fraud_alert_id
     OR payload::jsonb ->> 'correlation_id' = :fraud_alert_id
)
SELECT
  selected_alert.*,
  COALESCE(actions.action_history, '[]'::jsonb) AS action_history,
  COALESCE(audit_events.audit_history, '[]'::jsonb) AS audit_history
FROM selected_alert
LEFT JOIN actions ON actions.fraud_alert_id = selected_alert.id
CROSS JOIN audit_events;
