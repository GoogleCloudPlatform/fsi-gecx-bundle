from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_agent_build_and_terraform_share_capacity_contract() -> None:
    cloudbuild = (ROOT / "adk-agent/credit-support-agent/cloudbuild-deploy.yaml").read_text()
    cloud_build_tf = (ROOT / "deployment/terraform/cloud_build.tf").read_text()
    cloud_run_tf = (ROOT / "deployment/terraform/cloud_run_v2.tf").read_text()

    settings = (
        "VOICE_AGENT_MAX_CONCURRENT_SESSIONS",
        "VOICE_AGENT_AUDIO_SESSION_CAPACITY_UNITS",
        "VOICE_AGENT_VIDEO_SESSION_CAPACITY_UNITS",
        "VOICE_AGENT_USE_ACTION_PROPOSALS",
    )
    for setting in settings:
        assert setting in cloudbuild
        assert setting in cloud_run_tf

    trigger_start = cloud_build_tf.index(
        'resource "google_cloudbuild_trigger" "credit_support_agent_deploy_trigger"'
    )
    trigger_end = cloud_build_tf.index(
        'resource "google_cloudbuild_trigger" "data_generator_deploy_trigger"',
        trigger_start,
    )
    agent_trigger = cloud_build_tf[trigger_start:trigger_end]
    assert "_VOICE_AGENT_MAX_INSTANCE_REQUEST_CONCURRENCY" in agent_trigger
    assert "_VOICE_AGENT_MAX_CONCURRENT_SESSIONS" in agent_trigger

    ui_start = cloud_build_tf.index(
        'resource "google_cloudbuild_trigger" "banking_ui_deploy_trigger"'
    )
    ui_end = cloud_build_tf.index(
        'resource "google_cloudbuild_trigger" "iap_login_ui_deploy_trigger"',
        ui_start,
    )
    assert "_VOICE_AGENT_" not in cloud_build_tf[ui_start:ui_end]


def test_agent_archive_build_prepares_repository_for_linguist() -> None:
    cloudbuild = (ROOT / "adk-agent/credit-support-agent/cloudbuild-deploy.yaml").read_text()

    prepare_index = cloudbuild.index('id: "prepare-linguist-repository"')
    linguist_index = cloudbuild.index('id: "run-linguist"')

    assert prepare_index < linguist_index
    assert "git init -q /workspace" in cloudbuild
