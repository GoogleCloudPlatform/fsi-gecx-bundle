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

from fastmcp import FastMCP

# 1. Instantiate the Model Context Protocol (MCP) FastMCP Server directly
mcp = FastMCP("Banking Service MCP")

# 2. Create the MCP's ASGI app mounted under /mcp/
mcp_app = mcp.http_app(path="/", transport="http")

# Import sub-routers so their tool decorators register with the mcp instance
from . import loan as loan  # noqa: E402
from . import credit_card as credit_card  # noqa: E402

# Re-export tools and utility helpers for backward compatibility with existing tests and imports
from .loan import (  # noqa: E402
    get_loan_application_documents as get_loan_application_documents,
    generate_upload_session_url as generate_upload_session_url,
    bq_client as bq_client,
    storage as storage,
)
from .utils import (  # noqa: E402
    _extract_customer_identity as _extract_customer_identity,
    _mask_ssn as _mask_ssn,
    _mask_ein as _mask_ein,
)
