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

import logging
import os

import google.auth
from cachetools import cached, TTLCache
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import secretmanager

logger = logging.getLogger(__name__)

# Create the Secret Manager client
client = secretmanager.SecretManagerServiceClient()
secret_cache = TTLCache(maxsize=100, ttl=3600)

_cached_project_id = None


def get_project_id():
    global _cached_project_id
    if _cached_project_id:
        return _cached_project_id

    # Try environment variable first
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project_id:
        _cached_project_id = project_id
        return project_id

    # Try google auth
    try:
        credentials, project_id = google.auth.default()
        if project_id:
            _cached_project_id = project_id
            return project_id
    except DefaultCredentialsError:
        logger.error("🚨 Could not determine credentials.")
        logger.error(
            "Please run 'gcloud auth application-default login' "
            "or configure your environment."
        )
        raise
    except Exception:
        raise


@cached(cache=secret_cache)
def get_secret(
        secret_id: str, project_id: str = None, version_id: str = "latest"
) -> str:
    """
    Accesses a secret version from Google Cloud Secret Manager.
    """
    # If project_id is not set, use the default project
    if not project_id:
        project_id = get_project_id()

    name = client.secret_version_path(
        project=project_id, secret=secret_id, secret_version=version_id)

    # Access the secret version
    logger.info(f"Accessing secret: {name}")
    response = client.access_secret_version(name=name)

    # Decode the secret payload. Secrets are stored as bytes.
    secret_value = response.payload.data.decode("UTF-8")

    return secret_value
