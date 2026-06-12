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

from models.authentication import ForwardedUserContextType

# Configuration for endpoint restrictions when authenticating with X-Forwarded-User-Context (forwarded_auth)
# Maps the token type (extracted from the 'type' claim) to its list of allowed endpoints/methods.
ALLOWED_FORWARDED_AUTH_ROUTES = {
    ForwardedUserContextType.CXAS_AGENT.value: [
        {"method": "GET", "path": "/profile"},
        {"method": "POST", "path": "/profile"},
        {"method": "POST", "path": "/applications"},
        {"method": "POST", "path": "/artifacts/signed-url"},
    ]
}
