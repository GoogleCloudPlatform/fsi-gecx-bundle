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

"""Synthetic banking responses used only when a CES evaluation selects fake mode."""


def fake_tool_call(tool, input, callback_context):
    tool_id = (
        getattr(tool, "tool_id", "")
        or getattr(tool, "id", "")
        or getattr(tool, "name", "")
    )
    if isinstance(tool, dict):
        tool_id = tool.get("id") or tool.get("name") or tool_id
    tool_id = str(tool_id).rsplit("/", 1)[-1]
    # CES supplies MCP tool names with the toolset display-name prefix in
    # managed replays (for example,
    # banking_service_mcp_toolset_get_open_fraud_alert).
    known_tool_ids = (
        "get_open_fraud_alert",
        "propose_fraud_triage",
        "commit_fraud_triage",
        "propose_card_reissue",
        "commit_card_reissue",
        "propose_wallet_provisioning",
        "commit_wallet_provisioning",
        "decide_action_proposal",
        "request_credit_limit_increase",
    )
    tool_id = next(
        (
            known_tool_id
            for known_tool_id in known_tool_ids
            if tool_id.endswith(known_tool_id)
        ),
        tool_id,
    )
    authorizations = [{'authorization_id': 'eval-auth-1',
      'merchant_name': 'GAME*TEST TOKEN ONLINE',
      'money': {'amount_minor': 499, 'currency_code': 'USD'},
      'billing_money': {'amount_minor': 499, 'currency_code': 'USD'},
      'presentations': {'en-US': {'transaction': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                                  'locale': 'en-US',
                                                  'display_text': 'USD 4.99',
                                                  'speech_text': '4 US dollars and 99 cents'},
                                  'billing': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                              'locale': 'en-US',
                                              'display_text': 'USD 4.99',
                                              'speech_text': '4 US dollars and 99 cents'}},
                        'es-MX': {'transaction': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                                  'locale': 'es-MX',
                                                  'display_text': 'USD 4.99',
                                                  'speech_text': '4 dólares estadounidenses con 99 centavos'},
                                  'billing': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                              'locale': 'es-MX',
                                              'display_text': 'USD 4.99',
                                              'speech_text': '4 dólares estadounidenses con 99 centavos'}},
                        'es-ES': {'transaction': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                                  'locale': 'es-ES',
                                                  'display_text': 'USD 4.99',
                                                  'speech_text': '4 dólares estadounidenses con 99 centavos'},
                                  'billing': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                              'locale': 'es-ES',
                                              'display_text': 'USD 4.99',
                                              'speech_text': '4 dólares estadounidenses con 99 centavos'}},
                        'es-US': {'transaction': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                                  'locale': 'es-US',
                                                  'display_text': 'USD 4.99',
                                                  'speech_text': '4 dólares estadounidenses con 99 centavos'},
                                  'billing': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                              'locale': 'es-US',
                                              'display_text': 'USD 4.99',
                                              'speech_text': '4 dólares estadounidenses con 99 centavos'}},
                        'fr-CA': {'transaction': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                                  'locale': 'fr-CA',
                                                  'display_text': 'USD 4.99',
                                                  'speech_text': '4 dollars américains et 99 cents'},
                                  'billing': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                              'locale': 'fr-CA',
                                              'display_text': 'USD 4.99',
                                              'speech_text': '4 dollars américains et 99 cents'}},
                        'fr-FR': {'transaction': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                                  'locale': 'fr-FR',
                                                  'display_text': 'USD 4.99',
                                                  'speech_text': '4 dollars américains et 99 cents'},
                                  'billing': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                              'locale': 'fr-FR',
                                              'display_text': 'USD 4.99',
                                              'speech_text': '4 dollars américains et 99 cents'}},
                        'de-DE': {'transaction': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                                  'locale': 'de-DE',
                                                  'display_text': 'USD 4.99',
                                                  'speech_text': '4 US-Dollar und 99 Cent'},
                                  'billing': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                              'locale': 'de-DE',
                                              'display_text': 'USD 4.99',
                                              'speech_text': '4 US-Dollar und 99 Cent'}},
                        'pt-BR': {'transaction': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                                  'locale': 'pt-BR',
                                                  'display_text': 'USD 4.99',
                                                  'speech_text': '4 dólares americanos e 99 centavos'},
                                  'billing': {'money': {'amount_minor': 499, 'currency_code': 'USD'},
                                              'locale': 'pt-BR',
                                              'display_text': 'USD 4.99',
                                              'speech_text': '4 dólares americanos e 99 centavos'}}}},
     {'authorization_id': 'eval-auth-2',
      'merchant_name': 'APPLE.COM*ONLINE',
      'money': {'amount_minor': 149900, 'currency_code': 'USD'},
      'billing_money': {'amount_minor': 149900, 'currency_code': 'USD'},
      'presentations': {'en-US': {'transaction': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                                  'locale': 'en-US',
                                                  'display_text': 'USD 1,499.00',
                                                  'speech_text': '1499 US dollars and 0 cents'},
                                  'billing': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                              'locale': 'en-US',
                                              'display_text': 'USD 1,499.00',
                                              'speech_text': '1499 US dollars and 0 cents'}},
                        'es-MX': {'transaction': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                                  'locale': 'es-MX',
                                                  'display_text': 'USD 1,499.00',
                                                  'speech_text': '1499 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                              'locale': 'es-MX',
                                              'display_text': 'USD 1,499.00',
                                              'speech_text': '1499 dólares estadounidenses con 0 centavos'}},
                        'es-ES': {'transaction': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                                  'locale': 'es-ES',
                                                  'display_text': 'USD 1,499.00',
                                                  'speech_text': '1499 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                              'locale': 'es-ES',
                                              'display_text': 'USD 1,499.00',
                                              'speech_text': '1499 dólares estadounidenses con 0 centavos'}},
                        'es-US': {'transaction': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                                  'locale': 'es-US',
                                                  'display_text': 'USD 1,499.00',
                                                  'speech_text': '1499 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                              'locale': 'es-US',
                                              'display_text': 'USD 1,499.00',
                                              'speech_text': '1499 dólares estadounidenses con 0 centavos'}},
                        'fr-CA': {'transaction': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                                  'locale': 'fr-CA',
                                                  'display_text': 'USD 1,499.00',
                                                  'speech_text': '1499 dollars américains et 0 cents'},
                                  'billing': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                              'locale': 'fr-CA',
                                              'display_text': 'USD 1,499.00',
                                              'speech_text': '1499 dollars américains et 0 cents'}},
                        'fr-FR': {'transaction': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                                  'locale': 'fr-FR',
                                                  'display_text': 'USD 1,499.00',
                                                  'speech_text': '1499 dollars américains et 0 cents'},
                                  'billing': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                              'locale': 'fr-FR',
                                              'display_text': 'USD 1,499.00',
                                              'speech_text': '1499 dollars américains et 0 cents'}},
                        'de-DE': {'transaction': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                                  'locale': 'de-DE',
                                                  'display_text': 'USD 1,499.00',
                                                  'speech_text': '1499 US-Dollar und 0 Cent'},
                                  'billing': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                              'locale': 'de-DE',
                                              'display_text': 'USD 1,499.00',
                                              'speech_text': '1499 US-Dollar und 0 Cent'}},
                        'pt-BR': {'transaction': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                                  'locale': 'pt-BR',
                                                  'display_text': 'USD 1,499.00',
                                                  'speech_text': '1499 dólares americanos e 0 centavos'},
                                  'billing': {'money': {'amount_minor': 149900, 'currency_code': 'USD'},
                                              'locale': 'pt-BR',
                                              'display_text': 'USD 1,499.00',
                                              'speech_text': '1499 dólares americanos e 0 centavos'}}}},
     {'authorization_id': 'eval-auth-3',
      'merchant_name': 'BEST BUY*MKTPLACE',
      'money': {'amount_minor': 215000, 'currency_code': 'USD'},
      'billing_money': {'amount_minor': 215000, 'currency_code': 'USD'},
      'presentations': {'en-US': {'transaction': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                                  'locale': 'en-US',
                                                  'display_text': 'USD 2,150.00',
                                                  'speech_text': '2150 US dollars and 0 cents'},
                                  'billing': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                              'locale': 'en-US',
                                              'display_text': 'USD 2,150.00',
                                              'speech_text': '2150 US dollars and 0 cents'}},
                        'es-MX': {'transaction': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                                  'locale': 'es-MX',
                                                  'display_text': 'USD 2,150.00',
                                                  'speech_text': '2150 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                              'locale': 'es-MX',
                                              'display_text': 'USD 2,150.00',
                                              'speech_text': '2150 dólares estadounidenses con 0 centavos'}},
                        'es-ES': {'transaction': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                                  'locale': 'es-ES',
                                                  'display_text': 'USD 2,150.00',
                                                  'speech_text': '2150 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                              'locale': 'es-ES',
                                              'display_text': 'USD 2,150.00',
                                              'speech_text': '2150 dólares estadounidenses con 0 centavos'}},
                        'es-US': {'transaction': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                                  'locale': 'es-US',
                                                  'display_text': 'USD 2,150.00',
                                                  'speech_text': '2150 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                              'locale': 'es-US',
                                              'display_text': 'USD 2,150.00',
                                              'speech_text': '2150 dólares estadounidenses con 0 centavos'}},
                        'fr-CA': {'transaction': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                                  'locale': 'fr-CA',
                                                  'display_text': 'USD 2,150.00',
                                                  'speech_text': '2150 dollars américains et 0 cents'},
                                  'billing': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                              'locale': 'fr-CA',
                                              'display_text': 'USD 2,150.00',
                                              'speech_text': '2150 dollars américains et 0 cents'}},
                        'fr-FR': {'transaction': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                                  'locale': 'fr-FR',
                                                  'display_text': 'USD 2,150.00',
                                                  'speech_text': '2150 dollars américains et 0 cents'},
                                  'billing': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                              'locale': 'fr-FR',
                                              'display_text': 'USD 2,150.00',
                                              'speech_text': '2150 dollars américains et 0 cents'}},
                        'de-DE': {'transaction': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                                  'locale': 'de-DE',
                                                  'display_text': 'USD 2,150.00',
                                                  'speech_text': '2150 US-Dollar und 0 Cent'},
                                  'billing': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                              'locale': 'de-DE',
                                              'display_text': 'USD 2,150.00',
                                              'speech_text': '2150 US-Dollar und 0 Cent'}},
                        'pt-BR': {'transaction': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                                  'locale': 'pt-BR',
                                                  'display_text': 'USD 2,150.00',
                                                  'speech_text': '2150 dólares americanos e 0 centavos'},
                                  'billing': {'money': {'amount_minor': 215000, 'currency_code': 'USD'},
                                              'locale': 'pt-BR',
                                              'display_text': 'USD 2,150.00',
                                              'speech_text': '2150 dólares americanos e 0 centavos'}}}},
     {'authorization_id': 'eval-auth-4',
      'merchant_name': 'RAZER GOLD GIFT CARD',
      'money': {'amount_minor': 125000, 'currency_code': 'USD'},
      'billing_money': {'amount_minor': 125000, 'currency_code': 'USD'},
      'presentations': {'en-US': {'transaction': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                                  'locale': 'en-US',
                                                  'display_text': 'USD 1,250.00',
                                                  'speech_text': '1250 US dollars and 0 cents'},
                                  'billing': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                              'locale': 'en-US',
                                              'display_text': 'USD 1,250.00',
                                              'speech_text': '1250 US dollars and 0 cents'}},
                        'es-MX': {'transaction': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                                  'locale': 'es-MX',
                                                  'display_text': 'USD 1,250.00',
                                                  'speech_text': '1250 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                              'locale': 'es-MX',
                                              'display_text': 'USD 1,250.00',
                                              'speech_text': '1250 dólares estadounidenses con 0 centavos'}},
                        'es-ES': {'transaction': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                                  'locale': 'es-ES',
                                                  'display_text': 'USD 1,250.00',
                                                  'speech_text': '1250 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                              'locale': 'es-ES',
                                              'display_text': 'USD 1,250.00',
                                              'speech_text': '1250 dólares estadounidenses con 0 centavos'}},
                        'es-US': {'transaction': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                                  'locale': 'es-US',
                                                  'display_text': 'USD 1,250.00',
                                                  'speech_text': '1250 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                              'locale': 'es-US',
                                              'display_text': 'USD 1,250.00',
                                              'speech_text': '1250 dólares estadounidenses con 0 centavos'}},
                        'fr-CA': {'transaction': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                                  'locale': 'fr-CA',
                                                  'display_text': 'USD 1,250.00',
                                                  'speech_text': '1250 dollars américains et 0 cents'},
                                  'billing': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                              'locale': 'fr-CA',
                                              'display_text': 'USD 1,250.00',
                                              'speech_text': '1250 dollars américains et 0 cents'}},
                        'fr-FR': {'transaction': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                                  'locale': 'fr-FR',
                                                  'display_text': 'USD 1,250.00',
                                                  'speech_text': '1250 dollars américains et 0 cents'},
                                  'billing': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                              'locale': 'fr-FR',
                                              'display_text': 'USD 1,250.00',
                                              'speech_text': '1250 dollars américains et 0 cents'}},
                        'de-DE': {'transaction': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                                  'locale': 'de-DE',
                                                  'display_text': 'USD 1,250.00',
                                                  'speech_text': '1250 US-Dollar und 0 Cent'},
                                  'billing': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                              'locale': 'de-DE',
                                              'display_text': 'USD 1,250.00',
                                              'speech_text': '1250 US-Dollar und 0 Cent'}},
                        'pt-BR': {'transaction': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                                  'locale': 'pt-BR',
                                                  'display_text': 'USD 1,250.00',
                                                  'speech_text': '1250 dólares americanos e 0 centavos'},
                                  'billing': {'money': {'amount_minor': 125000, 'currency_code': 'USD'},
                                              'locale': 'pt-BR',
                                              'display_text': 'USD 1,250.00',
                                              'speech_text': '1250 dólares americanos e 0 centavos'}}}},
     {'authorization_id': 'eval-auth-5',
      'merchant_name': 'TARGET.COM GIFT CARDS',
      'money': {'amount_minor': 95000, 'currency_code': 'USD'},
      'billing_money': {'amount_minor': 95000, 'currency_code': 'USD'},
      'presentations': {'en-US': {'transaction': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                                  'locale': 'en-US',
                                                  'display_text': 'USD 950.00',
                                                  'speech_text': '950 US dollars and 0 cents'},
                                  'billing': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                              'locale': 'en-US',
                                              'display_text': 'USD 950.00',
                                              'speech_text': '950 US dollars and 0 cents'}},
                        'es-MX': {'transaction': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                                  'locale': 'es-MX',
                                                  'display_text': 'USD 950.00',
                                                  'speech_text': '950 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                              'locale': 'es-MX',
                                              'display_text': 'USD 950.00',
                                              'speech_text': '950 dólares estadounidenses con 0 centavos'}},
                        'es-ES': {'transaction': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                                  'locale': 'es-ES',
                                                  'display_text': 'USD 950.00',
                                                  'speech_text': '950 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                              'locale': 'es-ES',
                                              'display_text': 'USD 950.00',
                                              'speech_text': '950 dólares estadounidenses con 0 centavos'}},
                        'es-US': {'transaction': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                                  'locale': 'es-US',
                                                  'display_text': 'USD 950.00',
                                                  'speech_text': '950 dólares estadounidenses con 0 centavos'},
                                  'billing': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                              'locale': 'es-US',
                                              'display_text': 'USD 950.00',
                                              'speech_text': '950 dólares estadounidenses con 0 centavos'}},
                        'fr-CA': {'transaction': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                                  'locale': 'fr-CA',
                                                  'display_text': 'USD 950.00',
                                                  'speech_text': '950 dollars américains et 0 cents'},
                                  'billing': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                              'locale': 'fr-CA',
                                              'display_text': 'USD 950.00',
                                              'speech_text': '950 dollars américains et 0 cents'}},
                        'fr-FR': {'transaction': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                                  'locale': 'fr-FR',
                                                  'display_text': 'USD 950.00',
                                                  'speech_text': '950 dollars américains et 0 cents'},
                                  'billing': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                              'locale': 'fr-FR',
                                              'display_text': 'USD 950.00',
                                              'speech_text': '950 dollars américains et 0 cents'}},
                        'de-DE': {'transaction': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                                  'locale': 'de-DE',
                                                  'display_text': 'USD 950.00',
                                                  'speech_text': '950 US-Dollar und 0 Cent'},
                                  'billing': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                              'locale': 'de-DE',
                                              'display_text': 'USD 950.00',
                                              'speech_text': '950 US-Dollar und 0 Cent'}},
                        'pt-BR': {'transaction': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                                  'locale': 'pt-BR',
                                                  'display_text': 'USD 950.00',
                                                  'speech_text': '950 dólares americanos e 0 centavos'},
                                  'billing': {'money': {'amount_minor': 95000, 'currency_code': 'USD'},
                                              'locale': 'pt-BR',
                                              'display_text': 'USD 950.00',
                                              'speech_text': '950 dólares americanos e 0 centavos'}}}}]
    if tool_id == "get_open_fraud_alert":
        output = {
            "success": True,
            "fraud_alert": {
                "fraud_alert_id": "eval-alert-1",
                "status": "OPEN",
                "card_last_four": "0001",
                "suspicious_transactions": authorizations,
                "summary": (
                    "Customer has an active fraud alert on card ending in 0001. "
                    "Flagged transactions are USD 4.99 at GAME*TEST TOKEN ONLINE, "
                    "USD 1,499.00 at APPLE.COM*ONLINE, USD 2,150.00 at BEST "
                    "BUY*MKTPLACE, USD 1,250.00 at RAZER GOLD GIFT CARD, and "
                    "USD 950.00 at TARGET.COM GIFT CARDS."
                ),
            },
            "support_guidance": {
                "source": "knowledge_catalog",
                "topic_ids": ["fraud_golden_path", "replacement_card"],
                "snapshot_id": "eval-catalog-snapshot",
                "content_version": "2.2+2.4+2.5",
            },
        }
    elif tool_id == "propose_fraud_triage":
        output = {
            "success": True,
            "status": "PROPOSED",
            "action_type": "TRIAGE_FRAUD_CASE",
            "contract_version": "fraud-triage.v1",
            "proposal_id": "eval-proposal-1",
            "money_facts": authorizations,
            "presentations": {'en-US': {'locale': 'en-US',
                       'content_version': 'money-fraud-voice.v2',
                       'display_text': 'Please confirm that you want to dispute USD 4.99 at GAME*TEST TOKEN ONLINE.; USD '
                                       '1,499.00 at APPLE.COM*ONLINE.; USD 2,150.00 at BEST BUY*MKTPLACE.; USD 1,250.00 '
                                       'at RAZER GOLD GIFT CARD.; USD 950.00 at TARGET.COM GIFT CARDS on card ending in '
                                       '0001. We will block the current card and issue a replacement virtual card. We '
                                       'will request specialist review.',
                       'speech_text': 'Please confirm that you want to dispute 4 US dollars and 99 cents at GAME*TEST '
                                      'TOKEN ONLINE.; 1499 US dollars and 0 cents at APPLE.COM*ONLINE.; 2150 US dollars '
                                      'and 0 cents at BEST BUY*MKTPLACE.; 1250 US dollars and 0 cents at RAZER GOLD GIFT '
                                      'CARD.; 950 US dollars and 0 cents at TARGET.COM GIFT CARDS on card ending in '
                                      '0001. We will block the current card and issue a replacement virtual card. We '
                                      'will request specialist review.'},
             'es-MX': {'locale': 'es-MX',
                       'content_version': 'money-fraud-voice.v2',
                       'display_text': 'Confirme que desea presentar una reclamación por los siguientes cargos de la '
                                       'tarjeta que termina en 0001: USD 4.99 en GAME*TEST TOKEN ONLINE.; USD 1,499.00 '
                                       'en APPLE.COM*ONLINE.; USD 2,150.00 en BEST BUY*MKTPLACE.; USD 1,250.00 en RAZER '
                                       'GOLD GIFT CARD.; USD 950.00 en TARGET.COM GIFT CARDS. Bloquearemos la tarjeta '
                                       'actual y emitiremos una tarjeta virtual de reemplazo. Solicitaremos una revisión '
                                       'por un especialista.',
                       'speech_text': 'Confirme que desea presentar una reclamación por los siguientes cargos de la '
                                      'tarjeta que termina en 0001: 4 dólares estadounidenses con 99 centavos en '
                                      'GAME*TEST TOKEN ONLINE.; 1499 dólares estadounidenses con 0 centavos en '
                                      'APPLE.COM*ONLINE.; 2150 dólares estadounidenses con 0 centavos en BEST '
                                      'BUY*MKTPLACE.; 1250 dólares estadounidenses con 0 centavos en RAZER GOLD GIFT '
                                      'CARD.; 950 dólares estadounidenses con 0 centavos en TARGET.COM GIFT CARDS. '
                                      'Bloquearemos la tarjeta actual y emitiremos una tarjeta virtual de reemplazo. '
                                      'Solicitaremos una revisión por un especialista.'},
             'es-ES': {'locale': 'es-ES',
                       'content_version': 'money-fraud-voice.v2',
                       'display_text': 'Confirme que desea presentar una reclamación por los siguientes cargos de la '
                                       'tarjeta que termina en 0001: USD 4.99 en GAME*TEST TOKEN ONLINE.; USD 1,499.00 '
                                       'en APPLE.COM*ONLINE.; USD 2,150.00 en BEST BUY*MKTPLACE.; USD 1,250.00 en RAZER '
                                       'GOLD GIFT CARD.; USD 950.00 en TARGET.COM GIFT CARDS. Bloquearemos la tarjeta '
                                       'actual y emitiremos una tarjeta virtual de reemplazo. Solicitaremos una revisión '
                                       'por un especialista.',
                       'speech_text': 'Confirme que desea presentar una reclamación por los siguientes cargos de la '
                                      'tarjeta que termina en 0001: 4 dólares estadounidenses con 99 centavos en '
                                      'GAME*TEST TOKEN ONLINE.; 1499 dólares estadounidenses con 0 centavos en '
                                      'APPLE.COM*ONLINE.; 2150 dólares estadounidenses con 0 centavos en BEST '
                                      'BUY*MKTPLACE.; 1250 dólares estadounidenses con 0 centavos en RAZER GOLD GIFT '
                                      'CARD.; 950 dólares estadounidenses con 0 centavos en TARGET.COM GIFT CARDS. '
                                      'Bloquearemos la tarjeta actual y emitiremos una tarjeta virtual de reemplazo. '
                                      'Solicitaremos una revisión por un especialista.'},
             'es-US': {'locale': 'es-US',
                       'content_version': 'money-fraud-voice.v2',
                       'display_text': 'Confirme que desea presentar una reclamación por los siguientes cargos de la '
                                       'tarjeta que termina en 0001: USD 4.99 en GAME*TEST TOKEN ONLINE.; USD 1,499.00 '
                                       'en APPLE.COM*ONLINE.; USD 2,150.00 en BEST BUY*MKTPLACE.; USD 1,250.00 en RAZER '
                                       'GOLD GIFT CARD.; USD 950.00 en TARGET.COM GIFT CARDS. Bloquearemos la tarjeta '
                                       'actual y emitiremos una tarjeta virtual de reemplazo. Solicitaremos una revisión '
                                       'por un especialista.',
                       'speech_text': 'Confirme que desea presentar una reclamación por los siguientes cargos de la '
                                      'tarjeta que termina en 0001: 4 dólares estadounidenses con 99 centavos en '
                                      'GAME*TEST TOKEN ONLINE.; 1499 dólares estadounidenses con 0 centavos en '
                                      'APPLE.COM*ONLINE.; 2150 dólares estadounidenses con 0 centavos en BEST '
                                      'BUY*MKTPLACE.; 1250 dólares estadounidenses con 0 centavos en RAZER GOLD GIFT '
                                      'CARD.; 950 dólares estadounidenses con 0 centavos en TARGET.COM GIFT CARDS. '
                                      'Bloquearemos la tarjeta actual y emitiremos una tarjeta virtual de reemplazo. '
                                      'Solicitaremos una revisión por un especialista.'},
             'fr-CA': {'locale': 'fr-CA',
                       'content_version': 'money-fraud-voice.v2',
                       'display_text': 'Veuillez confirmer que vous souhaitez contester les opérations suivantes sur la '
                                       'carte se terminant par 0001 : USD 4.99 chez GAME*TEST TOKEN ONLINE.; USD '
                                       '1,499.00 chez APPLE.COM*ONLINE.; USD 2,150.00 chez BEST BUY*MKTPLACE.; USD '
                                       '1,250.00 chez RAZER GOLD GIFT CARD.; USD 950.00 chez TARGET.COM GIFT CARDS. Nous '
                                       'bloquerons la carte actuelle et émettrons une carte virtuelle de remplacement. '
                                       'Nous demanderons un examen par un spécialiste.',
                       'speech_text': 'Veuillez confirmer que vous souhaitez contester les opérations suivantes sur la '
                                      'carte se terminant par 0001 : 4 dollars américains et 99 cents chez GAME*TEST '
                                      'TOKEN ONLINE.; 1499 dollars américains et 0 cents chez APPLE.COM*ONLINE.; 2150 '
                                      'dollars américains et 0 cents chez BEST BUY*MKTPLACE.; 1250 dollars américains et '
                                      '0 cents chez RAZER GOLD GIFT CARD.; 950 dollars américains et 0 cents chez '
                                      'TARGET.COM GIFT CARDS. Nous bloquerons la carte actuelle et émettrons une carte '
                                      'virtuelle de remplacement. Nous demanderons un examen par un spécialiste.'},
             'fr-FR': {'locale': 'fr-FR',
                       'content_version': 'money-fraud-voice.v2',
                       'display_text': 'Veuillez confirmer que vous souhaitez contester les opérations suivantes sur la '
                                       'carte se terminant par 0001 : USD 4.99 chez GAME*TEST TOKEN ONLINE.; USD '
                                       '1,499.00 chez APPLE.COM*ONLINE.; USD 2,150.00 chez BEST BUY*MKTPLACE.; USD '
                                       '1,250.00 chez RAZER GOLD GIFT CARD.; USD 950.00 chez TARGET.COM GIFT CARDS. Nous '
                                       'bloquerons la carte actuelle et émettrons une carte virtuelle de remplacement. '
                                       'Nous demanderons un examen par un spécialiste.',
                       'speech_text': 'Veuillez confirmer que vous souhaitez contester les opérations suivantes sur la '
                                      'carte se terminant par 0001 : 4 dollars américains et 99 cents chez GAME*TEST '
                                      'TOKEN ONLINE.; 1499 dollars américains et 0 cents chez APPLE.COM*ONLINE.; 2150 '
                                      'dollars américains et 0 cents chez BEST BUY*MKTPLACE.; 1250 dollars américains et '
                                      '0 cents chez RAZER GOLD GIFT CARD.; 950 dollars américains et 0 cents chez '
                                      'TARGET.COM GIFT CARDS. Nous bloquerons la carte actuelle et émettrons une carte '
                                      'virtuelle de remplacement. Nous demanderons un examen par un spécialiste.'},
             'de-DE': {'locale': 'de-DE',
                       'content_version': 'money-fraud-voice.v2',
                       'display_text': 'Bitte bestätigen Sie, dass Sie die folgenden Umsätze auf der Karte mit den '
                                       'Endziffern 0001 beanstanden möchten: USD 4.99 bei GAME*TEST TOKEN ONLINE.; USD '
                                       '1,499.00 bei APPLE.COM*ONLINE.; USD 2,150.00 bei BEST BUY*MKTPLACE.; USD '
                                       '1,250.00 bei RAZER GOLD GIFT CARD.; USD 950.00 bei TARGET.COM GIFT CARDS. Wir '
                                       'werden die aktuelle Karte sperren und eine virtuelle Ersatzkarte ausstellen. Wir '
                                       'werden eine Prüfung durch eine Fachkraft anfordern.',
                       'speech_text': 'Bitte bestätigen Sie, dass Sie die folgenden Umsätze auf der Karte mit den '
                                      'Endziffern 0001 beanstanden möchten: 4 US-Dollar und 99 Cent bei GAME*TEST TOKEN '
                                      'ONLINE.; 1499 US-Dollar und 0 Cent bei APPLE.COM*ONLINE.; 2150 US-Dollar und 0 '
                                      'Cent bei BEST BUY*MKTPLACE.; 1250 US-Dollar und 0 Cent bei RAZER GOLD GIFT CARD.; '
                                      '950 US-Dollar und 0 Cent bei TARGET.COM GIFT CARDS. Wir werden die aktuelle Karte '
                                      'sperren und eine virtuelle Ersatzkarte ausstellen. Wir werden eine Prüfung durch '
                                      'eine Fachkraft anfordern.'},
             'pt-BR': {'locale': 'pt-BR',
                       'content_version': 'money-fraud-voice.v2',
                       'display_text': 'Confirme que deseja contestar as seguintes transações no cartão com final 0001: '
                                       'USD 4.99 em GAME*TEST TOKEN ONLINE.; USD 1,499.00 em APPLE.COM*ONLINE.; USD '
                                       '2,150.00 em BEST BUY*MKTPLACE.; USD 1,250.00 em RAZER GOLD GIFT CARD.; USD '
                                       '950.00 em TARGET.COM GIFT CARDS. Bloquearemos o cartão atual e emitiremos um '
                                       'cartão virtual substituto. Solicitaremos uma análise por um especialista.',
                       'speech_text': 'Confirme que deseja contestar as seguintes transações no cartão com final 0001: 4 '
                                      'dólares americanos e 99 centavos em GAME*TEST TOKEN ONLINE.; 1499 dólares '
                                      'americanos e 0 centavos em APPLE.COM*ONLINE.; 2150 dólares americanos e 0 '
                                      'centavos em BEST BUY*MKTPLACE.; 1250 dólares americanos e 0 centavos em RAZER '
                                      'GOLD GIFT CARD.; 950 dólares americanos e 0 centavos em TARGET.COM GIFT CARDS. '
                                      'Bloquearemos o cartão atual e emitiremos um cartão virtual substituto. '
                                      'Solicitaremos uma análise por um especialista.'}},
            "customer_safe_summary": (
                "Confirm that you want to dispute USD 4.99 at GAME*TEST TOKEN ONLINE, "
                "USD 1,499.00 at APPLE.COM*ONLINE, USD 2,150.00 at BEST BUY*MKTPLACE, "
                "USD 1,250.00 at RAZER GOLD GIFT CARD, and USD 950.00 at TARGET.COM "
                "GIFT CARDS on card ending 0001, block the current card, and issue "
                "a replacement."
            ),
        }
    elif tool_id == "commit_fraud_triage":
        output = {
            "success": True,
            "status": "COMMITTED",
            "action_type": "TRIAGE_FRAUD_CASE",
            "contract_version": "fraud-triage.v1",
            "proposal_id": "eval-proposal-1",
            "outcome": "PENDING_SPECIALIST_REVIEW",
            "replacement_card": {
                "new_last_four": "0002",
                "is_virtual": True,
                "status": "ACTIVE",
            },
            "customer_safe_result_summary": (
                "Your fraud report was submitted for specialist review. Five "
                "pending charges were released. Your compromised card was blocked, "
                "and a replacement virtual card ending in 0002 is active. A secure "
                "message with the case details was sent."
            ),
        }
    elif tool_id == "propose_card_reissue":
        output = {
            "success": True,
            "status": "PROPOSED",
            "action_type": "REISSUE_CARD",
            "contract_version": "card-reissue.v1",
            "proposal_id": "eval-reissue-proposal-1",
            "customer_safe_summary": (
                "Confirm that you want to block the card ending 0001 and issue "
                "a replacement virtual card."
            ),
        }
    elif tool_id == "commit_card_reissue":
        output = {
            "success": True,
            "status": "COMMITTED",
            "action_type": "REISSUE_CARD",
            "contract_version": "card-reissue.v1",
            "proposal_id": "eval-reissue-proposal-1",
            "replacement_card": {
                "new_last_four": "0002",
                "is_virtual": True,
                "status": "ACTIVE",
            },
        }
    elif tool_id == "propose_wallet_provisioning":
        output = {
            "success": True,
            "status": "PROPOSED",
            "action_type": "PROVISION_GOOGLE_WALLET",
            "contract_version": "wallet-provisioning.v1",
            "proposal_id": "eval-wallet-proposal-1",
            "customer_safe_summary": (
                "Confirm that you want to queue the virtual card ending 0002 "
                "for Google Wallet."
            ),
        }
    elif tool_id == "commit_wallet_provisioning":
        output = {
            "success": True,
            "status": "COMMITTED",
            "action_type": "PROVISION_GOOGLE_WALLET",
            "contract_version": "wallet-provisioning.v1",
            "proposal_id": "eval-wallet-proposal-1",
            "message": "Virtual card provisioning is queued for Google Wallet.",
            "card_token": "eval-replacement-token",
            "wallet_provider": "GOOGLE_WALLET",
            "wallet_provisioning_status": "QUEUED",
        }
    elif tool_id == "decide_action_proposal":
        decision = str((input or {}).get("decision") or "").strip().upper()
        output = {
            "success": decision in {"DECLINE", "REVISE", "CANCEL"},
            "status": "DECLINED" if decision == "DECLINE" else "INVALIDATED",
            "action_type": "TRIAGE_FRAUD_CASE",
            "contract_version": "fraud-triage.v1",
            "proposal_id": "eval-proposal-1",
            "decision": decision,
            "invalidation_reason": {
                "DECLINE": "CUSTOMER_DECLINED",
                "REVISE": "CUSTOMER_REVISED",
                "CANCEL": "CUSTOMER_CANCELLED",
            }.get(decision),
        }
    elif tool_id == "request_credit_limit_increase":
        requested_limit = int(
            (input or {}).get("amount")
            or (input or {}).get("requested_limit")
            or 0
        )
        output = {
            "success": requested_limit > 0,
            "new_limit": requested_limit,
            "message": "Credit limit increase approved.",
        }
    else:
        return None
    # ToolFakeConfig callbacks return the tool's logical response directly.
    # The MCP transport envelope is added only by the real remote MCP client;
    # returning that envelope here causes CES to expose an empty response to
    # the model during stable replay.
    return output


def fake_get_open_fraud_alert(tool, input, callback_context):
    return fake_tool_call({"id": "get_open_fraud_alert"}, input, callback_context)


def fake_propose_fraud_triage(tool, input, callback_context):
    return fake_tool_call({"id": "propose_fraud_triage"}, input, callback_context)


def fake_commit_fraud_triage(tool, input, callback_context):
    return fake_tool_call({"id": "commit_fraud_triage"}, input, callback_context)


def fake_propose_card_reissue(tool, input, callback_context):
    return fake_tool_call({"id": "propose_card_reissue"}, input, callback_context)


def fake_commit_card_reissue(tool, input, callback_context):
    return fake_tool_call({"id": "commit_card_reissue"}, input, callback_context)


def fake_propose_wallet_provisioning(tool, input, callback_context):
    return fake_tool_call({"id": "propose_wallet_provisioning"}, input, callback_context)


def fake_commit_wallet_provisioning(tool, input, callback_context):
    return fake_tool_call({"id": "commit_wallet_provisioning"}, input, callback_context)


def fake_decide_action_proposal(tool, input, callback_context):
    return fake_tool_call({"id": "decide_action_proposal"}, input, callback_context)
