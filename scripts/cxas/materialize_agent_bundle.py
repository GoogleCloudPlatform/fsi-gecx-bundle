#!/usr/bin/env python3
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

"""Materialize environment-specific files required by a CES import bundle."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from urllib.parse import urlparse


TOOLSET_RELATIVE_PATH = Path(
    "toolsets/banking_service_mcp_toolset/banking_service_mcp_toolset.yaml"
)
UNRESOLVED_TEMPLATE_VARIABLE = re.compile(r"\$\{[^}]+}")


def materialize_toolset(agent_folder: Path, banking_service_url: str) -> Path:
    """Render the banking MCP toolset beside its tracked template."""
    parsed_url = urlparse(banking_service_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("banking-service URL must be an absolute HTTPS URL")

    output_path = agent_folder / TOOLSET_RELATIVE_PATH
    template_path = output_path.with_suffix(output_path.suffix + ".tftpl")
    if not template_path.is_file():
        raise FileNotFoundError(f"CES toolset template not found: {template_path}")

    rendered = template_path.read_text().replace(
        "${banking_service_url}", banking_service_url.rstrip("/")
    )
    unresolved = UNRESOLVED_TEMPLATE_VARIABLE.findall(rendered)
    if unresolved:
        raise ValueError(
            "CES toolset contains unresolved template variables: "
            + ", ".join(sorted(set(unresolved)))
        )

    output_path.write_text(rendered)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-folder", required=True, type=Path)
    parser.add_argument("--banking-service-url", required=True)
    args = parser.parse_args()

    output_path = materialize_toolset(
        args.agent_folder.resolve(), args.banking_service_url
    )
    print(f"Materialized CES toolset: {output_path}")


if __name__ == "__main__":
    main()
