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
from typing import Optional, Dict, Any

def generate_signed_url(application_id: str, content_type: str) -> Dict[str, Any]:
  artifact_type = 'W2'

  payload = {
    "application_id": application_id,
    "artifact_type": artifact_type,
    "content_type": content_type
  }

  response = tools.banking_service_generate_upload_url_artifacts_signed_url_post(payload)
  if isinstance(response, dict):
      return response

  if hasattr(response, 'to_dict') and callable(getattr(response, 'to_dict')):
      return response.to_dict()

  if hasattr(response, 'data'):
      data = response.data
      if isinstance(data, dict):
          return data
      if isinstance(data, str):
          try:
              return json.loads(data)
          except Exception:
              pass

  if hasattr(response, 'body'):
      body = response.body
      if isinstance(body, dict):
          return body
      if isinstance(body, str):
          try:
              return json.loads(body)
          except Exception:
              pass

  response_str = str(response)
  try:
      return json.loads(response_str)
  except Exception:
      pass

  try:
      attrs = {}
      for attr in dir(response):
          if not attr.startswith('_') and not callable(getattr(response, attr)):
              val = getattr(response, attr)
              attrs[attr] = val
      if attrs:
          return attrs
  except Exception:
      # Intentionally best-effort introspection; ignore errors to fall back to raw string response parse.
      pass

  return {"error": "Failed to parse response", "raw": response_str}