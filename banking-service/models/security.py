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

from fastapi import Request, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials


class HTTPForwardedBearer(APIKeyHeader):
    def __init__(self, auto_error: bool = True):
        # This tells OpenAPI to use this header name
        super().__init__(name="X-Forwarded-User-Context", auto_error=auto_error)

    async def __call__(
            self, request: Request
    ) -> HTTPAuthorizationCredentials | None:
        # APIKeyHeader.__call__ retrieves the header value
        auth_header = await super().__call__(request)

        if not auth_header:
            return None

        if not auth_header.startswith("Bearer "):
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )
            return None

        token = auth_header.split(" ")[1]
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
