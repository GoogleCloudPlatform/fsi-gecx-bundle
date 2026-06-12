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

from typing import Optional, List

from pydantic import BaseModel


class SearchQueryRequest(BaseModel):
    query: str


class SearchResultItem(BaseModel):
    id: str
    title: str
    link: Optional[str] = None
    snippets: List[str]


class SearchQueryResponse(BaseModel):
    results: List[SearchResultItem]


class AnswerQueryRequest(BaseModel):
    query: str
    query_id: Optional[str] = None
    session: Optional[str] = None


class AnswerQueryResponse(BaseModel):
    answer: str
    session: str
    queryId: str
    relatedQuestions: List[str] = []
