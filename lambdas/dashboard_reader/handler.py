import boto3
import json
from decimal import Decimal


TABLE_NAME = "watchdog-findings"


class DecimalEncoder(json.JSONEncoder):
    """DynamoDB returns numbers as Decimal; JSON doesn't know how to serialize them.
    Convert to int if whole, float otherwise."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def scan_all_findings():
    """Read every finding from DynamoDB. Handles pagination automatically."""
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TABLE_NAME)

    response = table.scan()
    items = response.get("Items", [])

    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))

    return items


def handler(event, context):
    findings = scan_all_findings()

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({
            "findings": findings,
            "count": len(findings),
        }, cls=DecimalEncoder),
    }
