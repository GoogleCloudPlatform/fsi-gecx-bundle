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

from enum import Enum

from pydantic import BaseModel


class DocumentType(str, Enum):
    w2 = "W2"
    pay_stub = "PAY_STUB"

    # TODO: Give this instructions for Gemini instead to allow it to be more dynamic in what we extract.
    @property
    def fields_to_extract(self) -> list[str]:
        mapping = {
            DocumentType.w2.value: ["Employer's name", "Wages, tips, other comp."]
        }
        return mapping.get(self.value, [])


class ArtifactUploadRequest(BaseModel):
    application_id: str
    artifact_type: DocumentType
    base64_content: str
    content_type: str


class SignedUrlRequest(BaseModel):
    application_id: str
    artifact_type: DocumentType | None = None
    content_type: str = "application/pdf"
