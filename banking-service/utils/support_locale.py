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

"""Supported voice locales, independent of currency and display preferences."""
from typing import Literal

SupportLocale = Literal["en-US", "es-MX"]


def resolve_support_locale(profile_locale, override=None):
    if override is not None:
        if override not in ("en-US", "es-MX"):
            raise ValueError("Support language must be en-US or es-MX.")
        return override
    return profile_locale if profile_locale in ("en-US", "es-MX") else "en-US"
