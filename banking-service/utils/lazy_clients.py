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


class LazyClient:
    """Proxy that defers client construction until the first method/property access."""

    def __init__(self, factory):
        self._factory = factory
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = self._factory()
        return self._client

    def __getattr__(self, name):
        if name in {"_is_coroutine", "_is_coroutine_marker"} or (
            name.startswith("__") and name.endswith("__")
        ):
            raise AttributeError(name)
        return getattr(self._get_client(), name)
