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

"""Per-session serialization of ordered Live tool calls."""

from __future__ import annotations

import asyncio


class OrderedToolGate:
    """Run ordered tool pipelines one at a time, first come first served.

    ADK 2.4 executes every function call of one Live ``tool_call`` message in
    its own task via ``asyncio.gather``. Each ordered call holds the gate from
    the start of ``before_tool_callback`` until its ``after_tool_callback`` or
    ``on_tool_error_callback`` finishes, so callback state checks, the banking
    call, and the state update of one call never interleave with another.

    The owner is the running task. ``release`` is idempotent and a task
    done-callback releases the gate if the task ends without reaching an after
    or error callback (cancellation or an unhandled exception).
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None

    def locked(self) -> bool:
        return self._lock.locked()

    async def acquire(self) -> None:
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("OrderedToolGate requires a running task.")
        if self._owner is task:
            return
        await self._lock.acquire()
        self._owner = task
        task.add_done_callback(self._release_for)

    def release(self) -> None:
        self._release_for(asyncio.current_task())

    def _release_for(self, task: asyncio.Task | None) -> None:
        if task is None or self._owner is not task:
            return
        self._owner = None
        task.remove_done_callback(self._release_for)
        self._lock.release()
