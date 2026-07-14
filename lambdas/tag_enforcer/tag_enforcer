import boto3
import json
import urllib.request
import uuid
from datetime import datetime, timezone


CONFIG_RULE_NAME = "watchdog-required-tags"


# --- Notifiers (duplicated from other Lambdas — refactor to Layer later) ---

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


# --- Config query ---

def get_non_compliant_resources(rule_name):
    """Query AWS Config for non-compliant resources of a specific rule.
    Handles pagination automatically."""
    config = boto3.client("config")
    results = []
    paginator = config.get_paginator("get_compliance_details_by_config_rule")
    for page in paginator.paginate(
        ConfigRuleName=rule_name,
        ComplianceTypes=["NON_COMPLIANT"],
    ):
        results.extend(page.get("EvaluationResults", []))
    return results


# --- Finding builder ---

def build_finding(evaluation_result):
    """Convert a Config EvaluationResult into a finding record."""
    qualifier = evaluation_result["EvaluationResultIdentifier"]["EvaluationResultQualifier"]
    return {
        "finding_id":              str(uuid.uuid4()),
        "resource_id":             qualifier["ResourceId"],
        "resource_type":           qualifier["ResourceType"],
        "category":                "missing_tags",
        "detected_at":             datetime.now(timezone.utc).isoformat(),
        "config_rule_name":        qualifier["ConfigRuleName"],
        "annotation":              evaluation_result.get("Annotation", ""),
        "estimated_monthly_cost":  0,
    }


# --- DynamoDB write (auto-typed values) ---

def write_finding_to_dynamodb(finding):
    dynamodb = boto3.client("dynamodb")
    item = {}
    for key, value in finding.items():
        if isinstance(value, bool):
            item[key] = {"BOOL": value}
        elif isinstance(value, (int, float)):
            item[key] = {"N": str(value)}
        else:
            item[key] = {"S": str(value)}
    dynamodb.put_item(TableName="watchdog-findings", Item=item)


# --- Summary ---

def build_summary(findings):
    if not findings:
        return "Tag scan: all resources have required tags."

    lines = [
        f"Tag scan: {len(findings)} resource(s) missing required tags (Project, Environment, ManagedBy)",
        "",
    ]
    for f in findings:
        # Resource type "AWS::S3::Bucket" → "S3 Bucket"
        parts = f["resource_type"].split("::")
        readable_type = " ".join(parts[1:]) if len(parts) >= 3 else f["resource_type"]
        lines.append(f"  {readable_type}: {f['resource_id']}")
    return "\n".join(lines).strip()


# --- Handler ---

def handler(event, context):
    evaluation_results = get_non_compliant_resources(CONFIG_RULE_NAME)

    findings = [build_finding(r) for r in evaluation_results]

    for finding in findings:
        write_finding_to_dynamodb(finding)

    summary = build_summary(findings)
    print(summary)

    notify_slack(summary)
    notify_telegram(summary)

    return {"statusCode": 200, "body": summary}
