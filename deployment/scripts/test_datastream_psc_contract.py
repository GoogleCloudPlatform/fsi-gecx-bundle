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

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TERRAFORM = ROOT / "deployment" / "terraform"


class DatastreamPscContractTest(unittest.TestCase):
    def test_bridge_runtime_is_removed(self) -> None:
        self.assertFalse((TERRAFORM / "datastream_proxy_bridge.tf").exists())
        terraform = "\n".join(
            path.read_text() for path in sorted(TERRAFORM.glob("*.tf"))
        )
        self.assertNotIn("dms-images/tcp-proxy", terraform)
        self.assertNotIn("datastream_alloydb_proxy", terraform)

    def test_psc_attachment_is_manual_and_explicit(self) -> None:
        network = (TERRAFORM / "network.tf").read_text()
        self.assertIn('connection_preference = "ACCEPT_MANUAL"', network)
        self.assertIn(
            "producer_accept_lists = var.datastream_psc_producer_accept_lists",
            network,
        )
        self.assertNotIn('connection_preference = "ACCEPT_AUTOMATIC"', network)

    def test_datastream_uses_psc_and_alloydb_private_ip(self) -> None:
        datastream = (TERRAFORM / "datastream_cdc.tf").read_text()
        self.assertIn("psc_interface_config", datastream)
        self.assertNotIn("vpc_peering_config", datastream)
        self.assertIn(
            "hostname = google_alloydb_instance.banking_primary.ip_address",
            datastream,
        )

    def test_alloydb_private_service_access_remains(self) -> None:
        network = (TERRAFORM / "network.tf").read_text()
        self.assertIn(
            'resource "google_service_networking_connection" "private_vpc_connection"',
            network,
        )

    def test_evo_records_discovered_tenant_project(self) -> None:
        evo = (
            TERRAFORM
            / "environment"
            / "evo-genai-workspace"
            / "terraform.tfvars"
        ).read_text()
        self.assertIn("datastream_psc_producer_accept_lists", evo)
        self.assertIn("gf20e5a6ce5abca8fp-tp", evo)


if __name__ == "__main__":
    unittest.main()
