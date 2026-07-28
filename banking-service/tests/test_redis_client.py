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

from utils import redis_client


def test_execute_redis_command_reconnects_once_after_closed_connection(monkeypatch):
    clients = [object(), object()]
    resets = []

    monkeypatch.setattr(redis_client, "get_redis_client", lambda: clients.pop(0))
    monkeypatch.setattr(redis_client, "reset_redis_client", lambda: resets.append(True))

    calls = []

    def operation(client):
        calls.append(client)
        if len(calls) == 1:
            raise redis_client.redis.ConnectionError("connection closed by server")
        return "ok"

    assert redis_client.execute_redis_command(operation) == "ok"
    assert resets == [True]
    assert len(calls) == 2
