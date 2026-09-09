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
from typing import Literal, get_args

SupportLocale = Literal["en-US", "es-MX", "es-ES", "es-US", "fr-CA", "fr-FR", "de-DE", "pt-BR"]
SUPPORTED_SUPPORT_LOCALES = get_args(SupportLocale)


def resolve_support_locale(profile_locale, override=None):
    if override is not None:
        if override not in SUPPORTED_SUPPORT_LOCALES:
            raise ValueError("Unsupported support language.")
        return override
    return profile_locale if profile_locale in SUPPORTED_SUPPORT_LOCALES else "en-US"
