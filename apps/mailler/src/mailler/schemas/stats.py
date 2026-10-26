# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Statistics schemas."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class ProviderStatsItem(BaseModel):
    """Statistics for a single provider."""

    sent: int
    delivered: int
    bounced: int
    failed: int


class DailyStatsItem(BaseModel):
    """Statistics for a single day."""

    date: date
    sent: int
    delivered: int
    bounced: int
    failed: int


class StatsResponse(BaseModel):
    """Statistics response."""

    total: ProviderStatsItem
    by_provider: dict[str, ProviderStatsItem]
    by_date: list[DailyStatsItem]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": {
                    "sent": 1000,
                    "delivered": 950,
                    "bounced": 30,
                    "failed": 20,
                },
                "by_provider": {
                    "brevo": {
                        "sent": 500,
                        "delivered": 480,
                        "bounced": 15,
                        "failed": 5,
                    },
                    "sendgrid": {
                        "sent": 500,
                        "delivered": 470,
                        "bounced": 15,
                        "failed": 15,
                    },
                },
                "by_date": [
                    {
                        "date": "2026-01-27",
                        "sent": 100,
                        "delivered": 95,
                        "bounced": 3,
                        "failed": 2,
                    },
                    {
                        "date": "2026-01-28",
                        "sent": 150,
                        "delivered": 145,
                        "bounced": 3,
                        "failed": 2,
                    },
                ],
            }
        }
    )
