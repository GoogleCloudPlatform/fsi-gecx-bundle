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

import logging
import os
from typing import Optional
from google.cloud import discoveryengine_v1 as discoveryengine
from sqlalchemy.orm import Session

from models.authentication import ValidatedToken
from models.search import (
    SearchQueryRequest,
    SearchQueryResponse,
    AnswerQueryRequest,
    AnswerQueryResponse,
    SearchResultItem
)
from repositories import identity as identity_repo
from utils.gcp import get_project_id

logger = logging.getLogger(__name__)

PROJECT_ID = get_project_id()
DISCOVERY_ENGINE_ID = os.getenv("DISCOVERY_ENGINE_ID", "banking-site_1778875783412")
LOCATION = "global"


def _get_search_client():
    return discoveryengine.SearchServiceClient()


def _get_conversational_client():
    return discoveryengine.ConversationalSearchServiceClient()


class SearchService:
    """Service layer encapsulating Discovery Engine search and conversational answering."""

    def __init__(self, db: Session):
        self.db = db

    def execute_search(self, request: SearchQueryRequest) -> SearchQueryResponse:
        client = _get_search_client()
        serving_config = f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/engines/{DISCOVERY_ENGINE_ID}/servingConfigs/default_search"

        content_search_spec = discoveryengine.SearchRequest.ContentSearchSpec(
            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                return_snippet=True
            ),
            extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                max_extractive_answer_count=1
            )
        )

        search_request = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=request.query,
            page_size=10,
            content_search_spec=content_search_spec,
            query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO
            ),
            spell_correction_spec=discoveryengine.SearchRequest.SpellCorrectionSpec(
                mode=discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.AUTO
            )
        )

        page_result = client.search(search_request)
        results = []

        for result in page_result:
            doc = result.document
            struct_data = doc.derived_struct_data if doc.derived_struct_data else {}
            snippets = [s.get("snippet", "") for s in struct_data.get("snippets", [])]
            results.append(SearchResultItem(
                id=doc.id,
                title=struct_data.get("title", doc.name),
                link=struct_data.get("url"),
                snippets=snippets
            ))

        return SearchQueryResponse(results=results)

    def execute_answer_query(self, request: AnswerQueryRequest, token: Optional[ValidatedToken]) -> AnswerQueryResponse:
        client = _get_conversational_client()
        serving_config = f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/engines/{DISCOVERY_ENGINE_ID}/servingConfigs/default_search"

        answer_generation_spec = discoveryengine.AnswerQueryRequest.AnswerGenerationSpec(
            ignore_adversarial_query=True,
            ignore_non_answer_seeking_query=False,
            ignore_low_relevant_content=True,
            include_citations=True,
            prompt_spec=discoveryengine.AnswerQueryRequest.AnswerGenerationSpec.PromptSpec(
                preamble="""
                The company name is 'Nova Horizon'.
                Given the conversation between a user and a helpful assistant and some search results, create a final answer for the assistant. The answer should use all relevant information from the search results, not introduce any additional information, and use exactly the same words as the search results when possible. The assistant's answer should be brief, no more than 1 or 2 sentences.
                If you cannot find an answer, inform the user to contact customer service at (123) 123-4567.
                """
            ),
            model_spec=discoveryengine.AnswerQueryRequest.AnswerGenerationSpec.ModelSpec(
                model_version="stable"
            )
        )

        query_obj = discoveryengine.Query(
            text=request.query,
            query_id=request.query_id
        )

        query_understanding_spec = discoveryengine.AnswerQueryRequest.QueryUnderstandingSpec(
            query_rephraser_spec=discoveryengine.AnswerQueryRequest.QueryUnderstandingSpec.QueryRephraserSpec(
                disable=False,
                max_rephrase_steps=1,
            ),
            query_classification_spec=discoveryengine.AnswerQueryRequest.QueryUnderstandingSpec.QueryClassificationSpec(
                types=[
                    discoveryengine.AnswerQueryRequest.QueryUnderstandingSpec.QueryClassificationSpec.Type.ADVERSARIAL_QUERY,
                    discoveryengine.AnswerQueryRequest.QueryUnderstandingSpec.QueryClassificationSpec.Type.NON_ANSWER_SEEKING_QUERY,
                ]
            ),
        )

        end_user_spec = None
        user_id = None
        if token and token.user_id:
            user_id = token.user_id
            try:
                customer = identity_repo.get_customer(self.db, token.user_id)
                if customer:
                    profile_details = []
                    if customer.get('first_name'):
                        profile_details.append(f"First Name: {customer['first_name']}")
                    if customer.get('last_name'):
                        profile_details.append(f"Last Name: {customer['last_name']}")
                    if customer.get('email'):
                        profile_details.append(f"Email: {customer['email']}")
                    if customer.get('phone_number'):
                        profile_details.append(f"Phone: {customer['phone_number']}")

                    profile_content = "User Profile:\n" + "\n".join([f"- {d}" for d in profile_details])
                    profile_prompt = f"{profile_content}\nBased on the user's profile above, prioritize the user's needs and preferences when answering their question."

                    end_user_spec = discoveryengine.AnswerQueryRequest.EndUserSpec(
                        end_user_metadata=[
                            discoveryengine.AnswerQueryRequest.EndUserSpec.EndUserMetaData(
                                chunk_info=discoveryengine.AnswerQueryRequest.EndUserSpec.EndUserMetaData.ChunkInfo(
                                    content=profile_prompt,
                                    document_metadata=discoveryengine.AnswerQueryRequest.EndUserSpec.EndUserMetaData.ChunkInfo.DocumentMetadata(
                                        title=token.user_id
                                    )
                                )
                            )
                        ]
                    )
            except Exception as profile_err:
                logger.warning(f"Failed to retrieve or build end_user_spec: {profile_err}")

        answer_request = discoveryengine.AnswerQueryRequest(
            serving_config=serving_config,
            query=query_obj,
            session=request.session,
            answer_generation_spec=answer_generation_spec,
            related_questions_spec=discoveryengine.AnswerQueryRequest.RelatedQuestionsSpec(enable=True),
            query_understanding_spec=query_understanding_spec,
            user_pseudo_id=user_id,
            end_user_spec=end_user_spec
        )

        response = client.answer_query(answer_request)
        logger.info(f"Response: {response}")

        query_id = ""
        if response.answer and response.answer.name:
            query_id = response.answer.name.split("/")[-1]

        related_questions = list(response.answer.related_questions) if response.answer and response.answer.related_questions else []

        return AnswerQueryResponse(
            answer=response.answer.answer_text if response.answer else "",
            session=response.session.name if response.session else "",
            queryId=query_id,
            relatedQuestions=related_questions
        )
