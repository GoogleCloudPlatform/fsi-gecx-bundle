from unittest.mock import MagicMock, patch

from utils.database import get_iam_connection


def test_alloydb_iam_connection_uses_cloud_platform_token_and_tls() -> None:
    credentials = MagicMock()
    credentials.token = "short-lived-token"
    connection = MagicMock()

    with (
        patch("google.auth.default", return_value=(credentials, "example-project")) as default,
        patch("google.auth.transport.requests.Request", return_value=MagicMock()),
        patch("psycopg2.connect", return_value=connection) as connect,
    ):
        result = get_iam_connection(
            "postgresql+psycopg2://banking-service-sa@example-project.iam"
            "@10.20.30.40:5432/banking?sslmode=require"
        )

    assert result is connection
    default.assert_called_once_with(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh.assert_called_once()
    connect.assert_called_once_with(
        host="10.20.30.40",
        port=5432,
        database="banking",
        user="banking-service-sa@example-project.iam",
        password="short-lived-token",
        sslmode="require",
    )
