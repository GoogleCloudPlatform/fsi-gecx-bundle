# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os

import google
from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.adk.toolsets import McpToolset
from google.genai.types import ThinkingConfig

from .utils import is_env_flag_enabled

LOCATION = "us-central1"

credentials, project_id = google.auth.default()
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

NAME = "back_office_agent"
DESCRIPTION = "A back office agent that assists with loan application processing"

INSTRUCTION_PATH = os.path.join(os.path.dirname(__file__), "resources", "instruction.txt")
with open(INSTRUCTION_PATH, "r", encoding="utf-8") as f:
    INSTRUCTION_TEXT = f.read()

# Configure the FastMCP toolset mapping to our unified ASGI routing endpoint
mcp_toolset = McpToolset(
    url="http://localhost:8080/mcp"
)

root_agent = Agent(
    name=NAME,
    description=DESCRIPTION,
    model="gemini-2.5-flash",
    instruction=INSTRUCTION_TEXT,
    toolsets=[mcp_toolset],  # Register the secure FastMCP toolset!
    output_key="back_office_agent_output",
    planner=BuiltInPlanner(
        thinking_config=ThinkingConfig(
            include_thoughts=is_env_flag_enabled("SHOW_THOUGHTS")
        )
    ),
)
