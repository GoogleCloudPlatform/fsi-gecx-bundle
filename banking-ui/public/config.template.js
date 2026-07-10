/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

window.env = {
  BANKING_API_URL: "${VITE_BANKING_API_URL}",
  ENABLE_CCAI: "${VITE_ENABLE_CCAI}",
  CCAI_COMPANY_ID: "${VITE_CCAI_COMPANY_ID}",
  CCAI_HOST: "${VITE_CCAI_HOST}",
  CX_AGENT_STUDIO_DEPLOYMENT_NAME: "${VITE_CX_AGENT_STUDIO_DEPLOYMENT_NAME}",
  CX_AGENT_STUDIO_VOICE_AGENT_DEPLOYMENT_NAME: "${VITE_CX_AGENT_STUDIO_VOICE_AGENT_DEPLOYMENT_NAME}",
  CX_AGENT_STUDIO_UPLOAD_TOOL_NAME: "${VITE_CX_AGENT_STUDIO_UPLOAD_TOOL_NAME}",
  CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME: "${VITE_CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME}",
  CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME: "${VITE_CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME}",
  LIVEKIT_URL: "${LIVEKIT_URL}",
  SHOW_INFO_MODALS: "${VITE_SHOW_INFO_MODALS}",
  BUILD_VERSION: "${BUILD_VERSION}",
  BUILD_COMMIT_ID: "${BUILD_COMMIT_ID}",
  STABLE_ENV_URL: "${VITE_STABLE_ENV_URL}",
  FEEDBACK_URL: "${VITE_FEEDBACK_URL}"
};
