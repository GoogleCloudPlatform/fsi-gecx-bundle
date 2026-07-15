#!/bin/sh

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

# Set default port if not provided
export PORT=${PORT:-8080}

# Replace environment variables in config template
envsubst "\$VITE_BANKING_API_URL \$VITE_DATA_GENERATOR_API_URL \$VITE_ENABLE_CCAI \$VITE_CCAI_COMPANY_ID \$VITE_CCAI_HOST \$VITE_CX_AGENT_STUDIO_DEPLOYMENT_NAME \$VITE_CX_AGENT_STUDIO_VOICE_AGENT_DEPLOYMENT_NAME \$VITE_CX_AGENT_STUDIO_UPLOAD_TOOL_NAME \$VITE_CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME \$VITE_CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME \$LIVEKIT_URL \$VITE_STABLE_ENV_URL \$VITE_FEEDBACK_URL \$VITE_ENABLE_AVATAR_MODALITY \$VITE_CONSOLE_VIEWER_GROUP_JOIN_URL" < /usr/share/nginx/html/config.template.js > /usr/share/nginx/html/config.js

# Replace environment variables in Firebase config template
envsubst "\$FIREBASE_API_KEY \$FIREBASE_AUTH_DOMAIN \$FIREBASE_PROJECT_ID \$FIREBASE_STORAGE_BUCKET \$FIREBASE_MESSAGING_SENDER_ID \$FIREBASE_APP_ID \$FIREBASE_MEASUREMENT_ID" < /usr/share/nginx/html/fbConfig.template.js > /usr/share/nginx/html/fbConfig.js

# Replace environment variables in Nginx config template
envsubst "\$PORT \$FIREBASE_PROJECT_ID \$VITE_CCAI_HOST" < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

# Replace environment variables in sitemap and robots templates
envsubst "\$SITEMAP_BASE_URL" < /usr/share/nginx/html/sitemap.template.xml > /usr/share/nginx/html/sitemap.xml
envsubst "\$SITEMAP_BASE_URL" < /usr/share/nginx/html/robots.template.txt > /usr/share/nginx/html/robots.txt

# Clean up template files from the serving directory so they are not served statically
rm -f /usr/share/nginx/html/config.template.js
rm -f /usr/share/nginx/html/fbConfig.template.js
rm -f /usr/share/nginx/html/sitemap.template.xml
rm -f /usr/share/nginx/html/robots.template.txt


# Log the generated files to stdout for debugging
echo "--- Generated config.js ---"
cat /usr/share/nginx/html/config.js
echo "---------------------------"

echo "--- Generated fbConfig.js ---"
cat /usr/share/nginx/html/fbConfig.js
echo "------------------------------"

echo "--- Generated default.conf ---"
cat /etc/nginx/conf.d/default.conf
echo "-------------------------------"

echo "--- Generated sitemap.xml ---"
cat /usr/share/nginx/html/sitemap.xml
echo "------------------------------"

echo "--- Generated robots.txt ---"
cat /usr/share/nginx/html/robots.txt
echo "----------------------------"


# Start Nginx
exec nginx -g "daemon off;"
