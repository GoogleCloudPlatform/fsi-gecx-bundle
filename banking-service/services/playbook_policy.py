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

"""Environment-owned playbook publication policy.

The policy is deployment configuration and is never editable through the admin
API: an editable toggle would let the checked person disable the check. Phase 1
supports direct publication only, so any configured approval requirement, or an
unparsable one, refuses publication instead of being silently ignored.

An empty or whitespace-only approvals value means unset, i.e. 0 (direct publish).
With 0 approvals the approver allowlist has no effect: publication stays direct and
only the allowlist size is reported.
"""

from dataclasses import dataclass
import os
import re
from services.playbook_repository import PlaybookConflict

APPROVALS_ENV = "PLAYBOOK_PUBLISH_APPROVALS_REQUIRED"
APPROVERS_ENV = "PLAYBOOK_APPROVER_EMAILS"


class ApprovalsNotImplemented(PlaybookConflict):
    code = "APPROVALS_NOT_IMPLEMENTED"


class PublishPolicyInvalid(PlaybookConflict):
    code = "PUBLISH_POLICY_INVALID"


@dataclass(frozen=True)
class PublishPolicy:
    approvals_required: int | None
    approver_allowlist_size: int

    @classmethod
    def from_env(cls, environ=None):
        environ = os.environ if environ is None else environ
        raw = environ.get(APPROVALS_ENV, "").strip() or "0"
        approvals = int(raw) if re.fullmatch(r"[0-9]{1,6}", raw) else None
        approvers = {
            email.strip().lower()
            for email in environ.get(APPROVERS_ENV, "").split(",")
            if email.strip()
        }
        return cls(approvals, len(approvers))

    @property
    def publish_mode(self):
        if self.approvals_required is None:
            return "INVALID"
        return "DIRECT" if self.approvals_required == 0 else "APPROVALS_NOT_IMPLEMENTED"

    def view(self):
        return dict(
            source="environment",
            editable=False,
            approvals_required=self.approvals_required,
            approver_allowlist_size=self.approver_allowlist_size,
            publish_mode=self.publish_mode,
        )

    def audit_view(self):
        return dict(
            publish_mode=self.publish_mode,
            approvals_required=self.approvals_required,
            approver_allowlist_size=self.approver_allowlist_size,
        )

    def require_direct_publish(self):
        if self.publish_mode == "INVALID":
            raise PublishPolicyInvalid(
                f"{APPROVALS_ENV} must be a non-negative integer; publication is refused."
            )
        if self.publish_mode != "DIRECT":
            raise ApprovalsNotImplemented(
                "Publication approvals are configured but not yet supported; "
                "publication is refused."
            )
