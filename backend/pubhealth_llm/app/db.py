"""
Aurora Serverless v2 Data API client for pubHealthLLM.

Modeled on Alex's DataAPIClient pattern. Differences from Alex's version:
- Uses AWS_REGION env var (not DEFAULT_AWS_REGION)
- Default database is "pubhealth" (not "alex")
- Only read methods (query, query_one) — no insert/update/delete
- Module-level singleton via get_db()
"""

import json
import logging
import os
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class DataAPIClient:
    """Thin wrapper around AWS RDS Data API for Aurora Serverless v2."""

    def __init__(
        self,
        cluster_arn: Optional[str] = None,
        secret_arn: Optional[str] = None,
        database: Optional[str] = None,
        region: Optional[str] = None,
    ):
        self.cluster_arn = cluster_arn or os.environ.get("AURORA_CLUSTER_ARN")
        self.secret_arn = secret_arn or os.environ.get("AURORA_SECRET_ARN")
        self.database = database or os.environ.get("AURORA_DATABASE", "pubhealth")

        if not self.cluster_arn or not self.secret_arn:
            raise ValueError(
                "Missing Aurora configuration. "
                "Set AURORA_CLUSTER_ARN and AURORA_SECRET_ARN env vars."
            )

        self.region = region or os.environ.get("AWS_REGION", "us-west-1")
        self.client = boto3.client("rds-data", region_name=self.region)

    def execute(self, sql: str, parameters: Optional[list[dict]] = None) -> dict:
        """Execute a SQL statement. Returns raw Data API response."""
        try:
            kwargs = {
                "resourceArn": self.cluster_arn,
                "secretArn": self.secret_arn,
                "database": self.database,
                "sql": sql,
                "includeResultMetadata": True,
            }
            if parameters:
                kwargs["parameters"] = parameters
            return self.client.execute_statement(**kwargs)
        except ClientError as exc:
            logger.error("Aurora Data API error on SQL %r: %s", sql, exc)
            raise

    def query(self, sql: str, params: dict = None) -> list[dict]:
        """Execute SELECT and return list of row dicts."""
        built = self._build_parameters(params or {})
        response = self.execute(sql, built if built else None)

        if "records" not in response:
            return []

        columns = [col["name"] for col in response.get("columnMetadata", [])]
        results = []
        for record in response["records"]:
            row = {}
            for i, col in enumerate(columns):
                row[col] = self._extract_value(record[i])
            results.append(row)
        return results

    def query_one(self, sql: str, params: dict = None) -> Optional[dict]:
        """Execute SELECT and return first row dict, or None."""
        results = self.query(sql, params)
        return results[0] if results else None

    def _build_parameters(self, data: dict) -> list[dict]:
        """Convert {name: value} dict to Data API parameter list."""
        if not data:
            return []
        parameters = []
        for key, value in data.items():
            param = {"name": key}
            if value is None:
                param["value"] = {"isNull": True}
            elif isinstance(value, bool):
                param["value"] = {"booleanValue": value}
            elif isinstance(value, int):
                param["value"] = {"longValue": value}
            elif isinstance(value, float):
                param["value"] = {"doubleValue": value}
            elif isinstance(value, (dict, list)):
                param["value"] = {"stringValue": json.dumps(value)}
            else:
                param["value"] = {"stringValue": str(value)}
            parameters.append(param)
        return parameters

    def _extract_value(self, field: dict) -> Any:
        """Extract Python value from a Data API field dict."""
        if field.get("isNull"):
            return None
        for key in ("booleanValue", "longValue", "doubleValue"):
            if key in field:
                return field[key]
        if "stringValue" in field:
            val = field["stringValue"]
            if val and val[0] in ("{", "["):
                try:
                    return json.loads(val)
                except json.JSONDecodeError:
                    pass
            return val
        if "blobValue" in field:
            return field["blobValue"]
        logger.warning("_extract_value: unrecognized field type in %r, returning None", field)
        return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_client: Optional[DataAPIClient] = None


def get_db() -> DataAPIClient:
    """Return the shared DataAPIClient, creating it on first call.

    Thread-safety: FastAPI runs on a single asyncio event loop. The client
    is initialized by check_aurora_db() in the lifespan handler before any
    requests are served, so concurrent first-call races do not occur in practice.
    """
    global _client
    if _client is None:
        _client = DataAPIClient()
    return _client
