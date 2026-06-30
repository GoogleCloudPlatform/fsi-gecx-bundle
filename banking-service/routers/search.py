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
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from models.authentication import ValidatedToken
from models.search import SearchQueryRequest, SearchQueryResponse, AnswerQueryRequest, AnswerQueryResponse
from utils.auth import get_current_user
from utils.database import get_db
from services.search import SearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["search"], dependencies=[Depends(get_current_user)])


def get_search_service(db: Session = Depends(get_db)) -> SearchService:
    return SearchService(db)


@router.post("/search", response_model=SearchQueryResponse)
async def search_endpoint(
        request: SearchQueryRequest,
        service: SearchService = Depends(get_search_service)
):
    try:
        return service.execute_search(request)
    except Exception as e:
        logger.error(f"Error querying Discovery Engine search API: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve search results from Discovery Engine")


@router.post("/answers", response_model=AnswerQueryResponse)
async def answers_endpoint(
        request: AnswerQueryRequest,
        token: ValidatedToken = Depends(get_current_user),
        service: SearchService = Depends(get_search_service)
):
    try:
        return service.execute_answer_query(request, token)
    except Exception as e:
        logger.error(f"Error querying Discovery Engine Conversational Search API: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate answer from Discovery Engine")
