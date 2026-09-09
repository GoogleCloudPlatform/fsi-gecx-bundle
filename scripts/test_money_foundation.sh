#!/usr/bin/env bash
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

set -euo pipefail
REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPOSITORY_ROOT}"
python3 scripts/check_legacy_money.py
cd banking-service
uv run --frozen pytest -q --confcutdir=../scripts/testing/money ../scripts/testing/money
cd "${REPOSITORY_ROOT}"
PYTHONPATH="${REPOSITORY_ROOT}:${REPOSITORY_ROOT}/banking-service" \
  uv run --project banking-service --frozen pytest -q \
  -p scripts.testing.money.conftest \
  banking-service/tests/test_financial_journal.py \
  banking-service/tests/test_ledger_idempotency.py \
  banking-service/tests/test_credit_services.py --log-cli-level=CRITICAL
