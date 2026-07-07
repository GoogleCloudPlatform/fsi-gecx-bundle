# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
from fastapi import Header, HTTPException
from httpx import AsyncClient, ASGITransport

from main import app
from models.authentication import ValidatedToken
from utils.auth import get_current_user


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def override_auth():
    def mock_get_current_user(x_goog_iap_jwt_assertion: str = Header(None)):
        if x_goog_iap_jwt_assertion == "mock_token":
            return ValidatedToken(claims={"sub": "USER_123", "email": "test@example.com"})
        raise HTTPException(status_code=401, detail="Missing or invalid mock token")

    app.dependency_overrides[get_current_user] = mock_get_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_search_endpoint_success(async_client, monkeypatch):
    monkeypatch.setattr("utils.auth.get_secret", lambda x: "dummy_secret_key_that_is_long_enough_for_hs256")

    # Mock SearchServiceClient.search method
    class MockSearchPager:
        def __init__(self):
            from google.cloud.discoveryengine_v1.types import SearchResponse, Document
            self.results = [
                SearchResponse.SearchResult(
                    document=Document(
                        id="mock-1",
                        name="projects/fsi-gecx-2000/locations/global/collections/default_collection/engines/test_1778802748392/dataStores/default_data_store/documents/mock-1",
                        derived_struct_data={
                            "title": "Nova Horizon checking accounts",
                            "link": "http://localhost:5173/checking-accounts",
                            "snippets": [{
                                "snippet": "Nova Horizon offers premium interest checking accounts with no monthly fees, free mobile checks, and ATM fee reimbursements."}]
                        }
                    )
                )
            ]

        def __iter__(self):
            return iter(self.results)

    mock_client = type("MockSearchClient", (), {"search": lambda self, request: MockSearchPager()})()
    monkeypatch.setattr("services.search._get_search_client", lambda: mock_client)

    # Call /search
    response = await async_client.post(
        "/search",
        headers={"x-goog-iap-jwt-assertion": "mock_token"},
        json={"query": "checking account"}
    )
    assert response.status_code == 200
    resp_json = response.json()
    assert "results" in resp_json
    assert len(resp_json["results"]) > 0
    assert resp_json["results"][0]["title"] == "Nova Horizon checking accounts"


@pytest.mark.asyncio
async def test_answers_endpoint_success(async_client, monkeypatch):
    monkeypatch.setattr("utils.auth.get_secret", lambda x: "dummy_secret_key_that_is_long_enough_for_hs256")

    # Mock ConversationalSearchServiceClient.answer_query method
    class MockAnswerQueryResponse:
        def __init__(self):
            from google.cloud.discoveryengine_v1.types import Answer, Session
            self.answer = Answer(
                name="projects/fsi-gecx-2000/locations/global/collections/default_collection/engines/test_1778802748392/sessions/mock-session-id/answers/mock-query-id-999",
                answer_text="Nova Horizon offers four credit cards: Aura Elite Reserve, Velocity Cash Preferred, Equinox Horizon, and Vanguard Builder.",
                related_questions=["Which card has the lowest APR?", "How do I apply for a card?"]
            )
            self.session = Session(
                name="projects/fsi-gecx-2000/locations/global/collections/default_collection/engines/test_1778802748392/sessions/mock-session-id"
            )

    mock_client = type(
        "MockConversationalSearchClient",
        (),
        {"answer_query": lambda self, request: MockAnswerQueryResponse()},
    )()
    monkeypatch.setattr("services.search._get_conversational_client", lambda: mock_client)

    # Call /answers
    response = await async_client.post(
        "/answers",
        headers={"x-goog-iap-jwt-assertion": "mock_token"},
        json={
            "query": "What credit cards are available?",
            "session": "",
            "query_id": ""
        }
    )
    assert response.status_code == 200
    resp_json = response.json()
    assert "answer" in resp_json
    assert "session" in resp_json
    assert "queryId" in resp_json
    assert "four credit cards" in resp_json["answer"]
    assert resp_json["queryId"] == "mock-query-id-999"
    assert "relatedQuestions" in resp_json
    assert len(resp_json["relatedQuestions"]) == 2
    assert "lowest APR" in resp_json["relatedQuestions"][0]


@pytest.mark.asyncio
async def test_search_unauthorized(async_client):
    # Call /search with invalid Authorization header to trigger validation error
    response = await async_client.post(
        "/search",
        headers={"x-goog-iap-jwt-assertion": "invalid_token_value"},
        json={"query": "checking"}
    )
    assert response.status_code == 401
