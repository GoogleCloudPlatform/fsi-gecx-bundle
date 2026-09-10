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

"""Project a successful CES language-tool result into a display-only UI event."""
from utils.support_locale import SUPPORTED_SUPPORT_LOCALES


def ces_language_event(info):
    locale = None

    def visit(span, depth=0):
        nonlocal locale
        if not isinstance(span, dict) or depth > 20:
            return
        attrs = span.get("attributes")
        if span.get("name") == "Tool" and isinstance(attrs, dict):
            response = attrs.get("response")
            result = response.get("result") if isinstance(response, dict) else None
            if (attrs.get("name") == "set_conversation_language"
                    and isinstance(result, dict) and result.get("success") is True
                    and result.get("locale") in SUPPORTED_SUPPORT_LOCALES):
                locale = result["locale"]
        children = span.get("childSpans")
        for child in children[:200] if isinstance(children, list) else []:
            visit(child, depth + 1)

    if isinstance(info, dict):
        visit(info.get("rootSpan"))
    return {"type": "VOICE_LANGUAGE_CHANGED", "locale": locale} if locale else None
