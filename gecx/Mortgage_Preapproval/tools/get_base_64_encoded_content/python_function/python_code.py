import json
from typing import Optional, Dict, Any

def get_base_64_encoded_content(application_id: str) -> Dict[str, Any]:
  artifact_type = 'W2'
  base64_content = None
  content_type = None
  if context.user_content and context.user_content.parts:
    for part in context.user_content.parts:
      if hasattr(part, 'inline_data') and part.inline_data.data:
        # .decode('utf-8') converts bytes object to a JSON-friendly string
        base64_content = part.inline_data.data.decode('utf-8')
        mime_type = part.inline_data.mime_type
        break

  payload = {
    "application_id": application_id,
    "artifact_type": artifact_type,
    "base64_content": base64_content,
    "content_type": mime_type
  }

  tools.banking_service_upload_and_validate_artifacts_upload_and_validate_post(payload)
  return {"artifact_type": artifact_type, "base64_content": base64_content, "content_type": mime_type}