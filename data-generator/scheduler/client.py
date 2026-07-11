from __future__ import annotations

from typing import Any

import httpx

from .schemas import ScheduledEventRecord


class SyntheticScheduleClient:
    def __init__(
        self,
        *,
        banking_service_url: str,
        headers: dict[str, str],
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.banking_service_url = banking_service_url.rstrip("/")
        self.headers = headers
        self.timeout_seconds = timeout_seconds
        self.client = client

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.banking_service_url}/api/v1/credit-card/synthetic-schedule{path}"
        if self.client:
            response = await self.client.request(
                method,
                url,
                headers=self.headers,
                timeout=self.timeout_seconds,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                headers=self.headers,
                timeout=self.timeout_seconds,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

    async def create_event(self, payload: dict[str, Any]) -> ScheduledEventRecord:
        data = await self._request("POST", "/events", json=payload)
        return ScheduledEventRecord.model_validate(data)

    async def list_events(
        self,
        *,
        schedule_id: str | None = None,
        status_filter: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if schedule_id:
            params["schedule_id"] = schedule_id
        if status_filter:
            params["status_filter"] = status_filter
        return await self._request("GET", "/events", params=params)

    async def get_event(self, event_record_id: str) -> ScheduledEventRecord:
        data = await self._request("GET", f"/events/{event_record_id}")
        return ScheduledEventRecord.model_validate(data)

    async def get_context(
        self, *, schedule_id: str, persona_id: str | None = None
    ) -> dict[str, Any]:
        params = {"persona_id": persona_id} if persona_id else None
        return await self._request(
            "GET", f"/schedules/{schedule_id}/context", params=params
        )

    async def mark_dispatching(self, event_record_id: str) -> ScheduledEventRecord:
        data = await self._request("POST", f"/events/{event_record_id}/dispatching")
        return ScheduledEventRecord.model_validate(data)

    async def mark_succeeded(
        self, event_record_id: str, result_payload: dict[str, Any]
    ) -> ScheduledEventRecord:
        data = await self._request(
            "POST",
            f"/events/{event_record_id}/succeeded",
            json={"result_payload": result_payload},
        )
        return ScheduledEventRecord.model_validate(data)

    async def mark_failed(
        self,
        event_record_id: str,
        *,
        error: str,
        result_payload: dict[str, Any] | None = None,
    ) -> ScheduledEventRecord:
        data = await self._request(
            "POST",
            f"/events/{event_record_id}/failed",
            json={"error": error, "result_payload": result_payload or {}},
        )
        return ScheduledEventRecord.model_validate(data)

    async def cancel_schedule(self, schedule_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/schedules/{schedule_id}/cancel")
