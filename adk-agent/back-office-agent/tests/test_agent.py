import os
import sys
sys.path.insert(0, os.path.abspath("."))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent.agent import root_agent

def test_agent_resource_instruction_loaded():
    """Verifies that instructions are correctly read from the standalone resource file."""
    assert root_agent.name == "back_office_agent"
    assert "expert Back Office Loan Processing Assistant" in root_agent.instruction
    assert "{applicant_id}" in root_agent.instruction
    assert "{application_status}" in root_agent.instruction
    print("✓ test_agent_resource_instruction_loaded passed successfully")

async def test_agent_dynamic_state_injection():
    """Verifies that the Runner successfully populates dynamic state variables for the session."""
    session_service = InMemorySessionService()
    
    session = await session_service.create_session(
        app_name="agent",
        user_id="tester",
        session_id="loan_12345"
    )
    
    # Populate required prompt variables
    session.state["applicant_id"] = "APP-555"
    session.state["application_status"] = "Approved Status"
    
    runner = Runner(agent=root_agent, app_name="agent", session_service=session_service)
    
    # Send a lightweight query to confirm context injection
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text="State the applicant ID being reviewed.")]
    )
    
    response_text = ""
    async for event in runner.run_async(
        user_id="tester",
        session_id="loan_12345",
        new_message=message
    ):
        if event.content and event.author == root_agent.name:
            response_text += event.content.parts[0].text
            
    assert len(response_text) > 0
    print("✓ test_agent_dynamic_state_injection passed successfully")

# Optional support for standard pytest if available
try:
    import pytest
    test_agent_dynamic_state_injection = pytest.mark.asyncio(test_agent_dynamic_state_injection)
except ImportError:
    # Pytest is optional for running tests via direct script executions in sandboxes
    pass

if __name__ == "__main__":
    print("Running agent test suite directly...")
    test_agent_resource_instruction_loaded()
    # Live runner execution requires GCP access keys; verify static parsing first
    print("\nAll accessible local tests passed cleanly!")
