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

import json
import logging
import os
import re
import uuid

from google.adk import Runner
from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.adk.sessions import InMemorySessionService
from google.cloud import storage
from google import genai
from google.genai import types
from google.genai.types import ThinkingConfig
from pydantic import BaseModel

from utils.env import is_env_flag_enabled

logger = logging.getLogger(__name__)

os.environ.setdefault("SHOW_THOUGHTS", "True")


storage_client = storage.Client()

extractor_agent = Agent(
    name="extractor_agent",
    model="gemini-2.5-flash",
    instruction="""
    You are a banking assistant. Use the provided document artifacts to 
    extract the fields specified by the user. Always return valid JSON.
    """,
    planner=BuiltInPlanner(
        thinking_config=ThinkingConfig(
            include_thoughts=is_env_flag_enabled("SHOW_THOUGHTS")
        )
    ),
)

# artifact_svc = GcsArtifactService(bucket_name="fsi-gecx-2000_banking-interaction-artifacts")

# session_svc = VertexAiSessionService(
#     project="fsi-gecx-2000",
#     location="us-central1"
# )

session_service = InMemorySessionService()
runner = Runner(
    app_name="extractor_app",
    agent=extractor_agent,
    session_service=session_service,
    # artifact_service=artifact_svc
    auto_create_session=True
)


async def extract_data(gcs_uri: str, mime_type: str, fields: list[str], user_id: str):
    """
    Connects an existing GCS file to the agent session and extracts data.
    """
    logger.info(f"Extracting data from {gcs_uri} for fields: {fields} and user {user_id}")

    message = types.Content(
        role="user",
        parts=[
            types.Part(text=f"Please extract the following data attributes "
                            f"from the provided document: {','.join(fields)}."
                            f"If the requested attributes are not found, return an empty JSON object."),
            types.Part(
                file_data=types.FileData(
                    mime_type=mime_type,
                    file_uri=gcs_uri
                )
            )
        ]
    )

    logger.info(f"Message: {message}")

    # Generate a unique session ID to avoid race conditions
    session_id = str(uuid.uuid4())

    stream = runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message
    )

    thoughts = ""
    response = ""

    async for event in stream:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.thought is None:
                    response += part.text
                else:
                    thoughts += part.text

    json_response = parse_json_response(response)
    return json_response


def parse_json_response(response_str: str):
    # 1. Use regex to extract content inside the ```json ... ``` blocks
    # re.DOTALL allows the dot (.) to match newlines as well
    match = re.search(r'```json\s*(.*?)\s*```', response_str, re.DOTALL)

    if match:
        # Extract the captured group containing the actual JSON
        json_content = match.group(1)
    else:
        # Fallback: if the model didn't use markdown blocks, try the raw string
        # after stripping potential leading/trailing whitespace
        json_content = response_str.strip()

    try:
        # 2. Parse the cleaned string into a Python object (dict or list)
        return json.loads(json_content)
    except json.JSONDecodeError as e:
        logger.error(f"🚨 Failed to parse JSON: {e}")
        logger.error(f"Original content was:\n{json_content}")
        return None


class GeocodingCoords(BaseModel):
    latitude: float
    longitude: float


async def geocode_address(address: str) -> tuple[float, float] | None:
    try:
        client = genai.Client()
        prompt = f"Geocode the following address/location to latitude and longitude: {address}"
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeocodingCoords,
            )
        )
        data = GeocodingCoords.model_validate_json(response.text)
        return data.latitude, data.longitude
    except Exception as e:
        logger.error(f"Geocoding address '{address}' failed: {e}")
        return None

