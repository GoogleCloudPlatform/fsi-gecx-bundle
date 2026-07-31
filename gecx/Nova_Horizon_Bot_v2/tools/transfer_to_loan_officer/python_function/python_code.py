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

from typing import Any, Dict

def transfer_to_loan_officer(loan_officer_name: str, loan_officer_id: str, chat_summary: str, verified_data: Dict[str, Any]) -> dict[str, Any]:
    """
    Transfers the current chat session, along with relevant collected data, to a licensed human Loan Officer.

    Args:
        loan_officer_name (str): The name of the Loan Officer to transfer to.
        loan_officer_id (str): The NLMS ID or internal ID of the Loan Officer.
        chat_summary (str): A brief summary of the conversation history and user's intent.
        verified_data (Dict[str, Any]): A dictionary containing key pieces of verified information
                                        (e.g., ZIP code, target price, employer name).

    Returns:
        dict[str, Any]: A dictionary indicating the status of the transfer.
              Example: {"status": "success", "message": "Transfer initiated successfully."}
              Example: {"status": "failed", "message": "Loan Officer not available."}
    """
    # MOCK: This mock simulates the process of transferring a chat to a human agent.
    # In a real system, this would integrate with a CRM, contact center, or live chat platform.
    # It always returns success for demonstration purposes.

    # Store the transfer details in context for potential debugging or follow-up in a real system
    context.state["last_transfer_details"] = {
        "loan_officer_name": loan_officer_name,
        "loan_officer_id": loan_officer_id,
        "chat_summary": chat_summary,
        "verified_data": verified_data,
        "timestamp": context.state.get("current_date", "N/A") # Using current_date from context
    }

    if not loan_officer_name or not loan_officer_id:
        return {"status": "failed", "message": "Missing Loan Officer details for transfer."}

    # Simulate a successful transfer
    return {"status": "success", "message": f"Chat and data securely transferred to {loan_officer_name} (NLMS ID: {loan_officer_id})."}