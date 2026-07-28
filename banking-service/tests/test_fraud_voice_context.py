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

from services.fraud_alerts import FraudAlertService


def test_voice_context_summary_enumerates_every_flagged_transaction_with_amount():
    transactions = [
        {"merchant_name": "GAME*TEST TOKEN ONLINE", "amount_cents": 499},
        {"merchant_name": "APPLE.COM*ONLINE", "amount_cents": 149900},
        {"merchant_name": "BEST BUY*MKTPLACE", "amount_cents": 215000},
        {"merchant_name": "RAZER GOLD GIFT CARD", "amount_cents": 125000},
        {"merchant_name": "TARGET.COM GIFT CARDS", "amount_cents": 95000},
    ]

    summary = FraudAlertService._build_voice_context_summary("6141", transactions)

    assert "card ending in 6141" in summary
    assert "$4.99 at GAME*TEST TOKEN ONLINE" in summary
    assert "$1,499.00 at APPLE.COM*ONLINE" in summary
    assert "$2,150.00 at BEST BUY*MKTPLACE" in summary
    assert "$1,250.00 at RAZER GOLD GIFT CARD" in summary
    assert "$950.00 at TARGET.COM GIFT CARDS" in summary
    assert "other" not in summary.lower()
