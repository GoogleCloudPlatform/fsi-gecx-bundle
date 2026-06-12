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