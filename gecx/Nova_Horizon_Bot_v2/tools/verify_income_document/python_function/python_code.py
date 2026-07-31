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

from typing import Any

def verify_income_document(document_content: str) -> dict[str, Any]:
    """
    Verifies income information from an uploaded document (e.g., W-2, Pay Stub).

    Args:
        document_content (str): A string representing the content or type of the uploaded document.
                                In a real scenario, this would be a reference to an actual document.

    Returns:
        dict[str, Any]: A dictionary indicating the verification status and extracted employer name.
              Example: {"status": "verified", "employer_name": "Acme Corp"}
              Example: {"status": "unverified", "message": "Document format not recognized."}
              Example: {"error": True, "message": "Failed to process document."}
    """
    # MOCK: This mock simulates processing an uploaded income document.
    # In a real implementation, this would involve Document AI or OCR services.
    # It checks for a specific mock content to simulate success or failure.

    if "mock W-2" in document_content.lower() or "pay stub" in document_content.lower():
        # Simulate successful verification and extraction of employer name
        return {"status": "verified", "employer_name": "Acme Corp"}
    elif "invalid document" in document_content.lower():
        # Simulate a document that cannot be processed
        return {"status": "unverified", "message": "The uploaded document could not be processed. Please ensure it's a clear W-2 or Pay Stub."}
    else:
        # Default to unverified for any other content
        return {"status": "unverified", "message": "Document content not recognized as a valid income verification document."}