import boto3
import json
import urllib.request
import uuid
from datetime import datetime, timezone


# --- Notifiers (duplicated from other Lambdas; refactor to Layer later) ---

def get_secret(secret_id):
    sm = boto3.client("secretsmanager")
    response = sm.get_secret_value(SecretId=secret_id)
    return response["SecretString"]


def notify_slack(message):
    webhook_url = get_secret("watchdog/slack-webhook")
    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as response:
        return response.status


def notify_telegram(message):
    secret_json = get_secret("watchdog/telegram-bot")
    creds = json.loads(secret_json)
    url = f"https://api.telegram.org/bot{creds['bot_token']}/sendMessage"
    payload = json.dumps({
        "chat_id": creds["chat_id"],
        "text": message,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as response:
        return response.status


# --- Anomaly parsing ---

def parse_anomaly(sns_message_str):
    """Extract meaningful fields from the anomaly JSON."""
    anomaly = json.loads(sns_message_str)

    impact = anomaly.get("impact", {})
    root_causes = anomaly.get("rootCauses", [])

    return {
        "anomaly_id":              anomaly.get("anomalyId", "unknown"),
        "account_id":              anomaly.get("accountId", ""),
        "start_date":              anomaly.get("anomalyStartDate", ""),
        "end_date":                anomaly.get("anomalyEndDate", ""),
        "total_actual_spend":      float(impact.get("totalActualSpend", 0)),
        "total_expected_spend":    float(impact.get("totalExpectedSpend", 0)),
        "total_impact_dollars":    float(impact.get("totalImpact", 0)),
        "total_impact_percentage": float(impact.get("totalImpactPercentage", 0)),
        "root_causes":             [rc.get("service", "unknown") for rc in root_causes],
        "detail_link":             anomaly.get("anomalyDetailsLink", ""),
    }


def build_summary(anomaly):
    """Human-readable summary."""
    services = ", ".join(anomaly["root_causes"]) if anomaly["root_causes"] else "unknown"

    lines = [
        f"Cost anomaly detected: ${anomaly['total_impact_dollars']:.2f} above expected",
        f"Period: {anomaly['start_date']} to {anomaly['end_date']}",
        f"Actual spend: ${anomaly['total_actual_spend']:.2f}",
        f"Expected spend: ${anomaly['total_expected_spend']:.2f}",
        f"Impact: {anomaly['total_impact_percentage']:.1f}% above baseline",
        f"Services: {services}",
    ]

    if anomaly["detail_link"]:
        lines.append(f"Details: {anomaly['detail_link']}")

    return "\n".join(lines)


def write_finding_to_dynamodb(anomaly, summary):
    """Save the anomaly as a finding in the shared table."""
    dynamodb = boto3.client("dynamodb")
    dynamodb.put_item(
        TableName="watchdog-findings",
        Item={
            "finding_id":         {"S": str(uuid.uuid4())},
            "resource_id":        {"S": anomaly["anomaly_id"]},
            "resource_type":      {"S": "cost_anomaly"},
            "category":           {"S": "cost_anomaly"},
            "detected_at":        {"S": datetime.now(timezone.utc).isoformat()},
            "anomaly_start":      {"S": anomaly["start_date"]},
            "anomaly_end":        {"S": anomaly["end_date"]},
            "impact_dollars":     {"N": str(anomaly["total_impact_dollars"])},
            "impact_percentage":  {"N": str(anomaly["total_impact_percentage"])},
            "services":           {"S": ", ".join(anomaly["root_causes"])},
            "summary":            {"S": summary},
        },
    )


# --- Handler ---

def handler(event, context):
    """SNS triggers this with an anomaly event."""
    for record in event.get("Records", []):
        sns_message = record.get("Sns", {}).get("Message", "{}")

        anomaly = parse_anomaly(sns_message)
        summary = build_summary(anomaly)

        print(summary)

        write_finding_to_dynamodb(anomaly, summary)
        notify_slack(summary)
        notify_telegram(summary)

    return {"statusCode": 200, "body": "processed"}
