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

FROM gcr.io/google.com/cloudsdktool/cloud-sdk:slim

# The cloud-sdk:slim base no longer ships a system python3 (same change that
# broke the release step in #310); the reconcile script needs it (stdlib only).
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY scripts/datastream/reconcile_lakehouse_views.py /app/reconcile_lakehouse_views.py
COPY deployment/bigquery /app/deployment/bigquery

ENTRYPOINT ["python3", "/app/reconcile_lakehouse_views.py"]
