from services.voice_language import ces_language_event


def info(*results):
    return {"rootSpan": {"childSpans": [
        {"name": "Tool", "attributes": {"name": "set_conversation_language",
          "args": {"locale": "de-DE"}, "response": {"result": result}}}
        for result in results]}}


def test_only_successful_tool_result_changes_display_and_excludes_banking_payload():
    assert ces_language_event(info({"success": True, "locale": "it-IT", "proposal_facts": {"private": "value"}})) == {
        "type": "VOICE_LANGUAGE_CHANGED", "locale": "it-IT"}
    assert ces_language_event(info({"success": True, "locale": "it-IT"}, {"success": True, "locale": "en-US"}))["locale"] == "en-US"


def test_rejected_requests_transcripts_variables_and_unknown_locales_do_not_change_display():
    for result in [{"success": False, "locale": "it-IT"}, {"locale": "it-IT"}, {"success": True, "locale": "unknown"}]:
        assert ces_language_event(info(result)) is None
    assert ces_language_event({"messages": [{"text": "Speak Italian", "updatedVariables": {"runtime_language_code": "it-IT"}}]}) is None
    assert ces_language_event(None) is None
    unrelated = info({"success": True, "locale": "it-IT"})
    unrelated["rootSpan"]["childSpans"][0]["attributes"]["name"] = "other_tool"
    assert ces_language_event(unrelated) is None
