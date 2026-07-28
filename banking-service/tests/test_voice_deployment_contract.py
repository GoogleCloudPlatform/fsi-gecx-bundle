from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_cloud_run_retains_shutdown_headroom_beyond_voice_session_timeout():
    variables = (ROOT / "deployment/terraform/variables.tf").read_text()
    cloud_run = (ROOT / "deployment/terraform/cloud_run_v2.tf").read_text()

    assert 'variable "banking_service_timeout_seconds"' in variables
    assert "default = 720" in variables
    assert 'variable "banking_service_voice_session_timeout_seconds"' in variables
    assert "default     = 600" in variables
    assert "var.banking_service_voice_session_timeout_seconds + 60" in cloud_run
    assert 'name  = "VOICE_BIDI_SESSION_TIMEOUT_SECONDS"' in cloud_run
    assert (
        "value = tostring(var.banking_service_voice_session_timeout_seconds)"
        in cloud_run
    )
