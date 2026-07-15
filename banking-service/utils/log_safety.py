# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Helpers for correlatable logs that do not expose customer data."""

import hashlib
import os


def stable_log_reference(value: object, prefix: str = "ref") -> str:
    """Return a bounded, one-way reference suitable for operational logs."""
    if value is None or str(value).strip() == "":
        return f"{prefix}:none"
    salt = os.getenv("LOG_REFERENCE_SALT", "fsi-gecx-log-reference")
    digest = hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:12]
    return f"{prefix}:{digest}"
