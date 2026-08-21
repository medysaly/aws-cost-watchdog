import boto3
import json
import urllib.request
from datetime import datetime, timezone



# rule name for the AWS Config rule that checks for required tags
CONFIG_RULE_NAME = "watchdog-required-tags"

# Function to get non-compliant resources for a given AWS Config rule
def get_non_compliant_resources(rule_name):
    """Get the list of non-compliant resources for the specified AWS Config rule."""
    config = boto3.client("config")
    results = []
    paginator = config.get_paginator("get_compliance_details_by_config_rule")
    for page in paginator.paginate(
        ConfigRuleName=rule_name,
        ComplianceTypes=["NON_COMPLIANT"],
    ):
        results.extend(page.get("EvaluationResults", []))
    return results


# turn an AWS Config EvaluationResult into a finding record for DynamoDB table
def build_finding(evaluation_result):
    """Convert a Config EvaluationResult into a finding record."""
    qualifier = evaluation_result["EvaluationResultIdentifier"]["EvaluationResultQualifier"]
    return {
        "finding_id":              f"missing_tags:{qualifier['ResourceId']}",
        "resource_id":             qualifier["ResourceId"],
        "resource_type":           qualifier["ResourceType"],
        "category":                "missing_tags",
        "detected_at":             datetime.now(timezone.utc).isoformat(),
        "config_rule_name":        qualifier["ConfigRuleName"],
        "annotation":              evaluation_result.get("Annotation", ""),
        "estimated_monthly_cost":  0,
    }


# checks dynamoDB for new findings 
def is_new_finding(finding_id):
    """Check if a finding with this ID already exists in DynamoDB."""
    dynamodb = boto3.client("dynamodb")
    response = dynamodb.get_item(
        TableName="watchdog-findings",
        Key={"finding_id": {"S": finding_id}}
    )
    return "Item" not in response


# takes one finding dict built in build_finding and saves it as a row in the watchdog-findings DynamoDB table
def write_finding_to_dynamodb(finding):
    """Write a finding to DynamoDB, auto-typing values."""
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


#takes the list of new tag violations and turns it into ONE friendly, human-readable string that we send to Slack and Telegram.
def build_summary(findings):
    """Turn a list of tag violations into a friendly summary string"""
    lines = [
        f"Hey, found {len(findings)} resource(s) missing required tags (Project, Environment, ManagedBy).",
        "",
    ]
    for f in findings:
        parts = f["resource_type"].split("::")
        if len(parts) >= 3:
            readable_type = " ".join(parts[1:])
        else:
            readable_type = f["resource_type"]
        lines.append(f"  {readable_type}: {f['resource_id']}")
    text = "\n".join(lines)
    return text.strip()

#fetches ONE secret from AWS Secrets Manager and returns its raw string value
def get_secret(secret_id):
    """Retrieve a secret from AWS Secrets Manager."""
    sm = boto3.client("secretsmanager")
    response = sm.get_secret_value(SecretId=secret_id)
    return response["SecretString"]

#Send notifications to Slack/Telegram
def notify_slack(message):
    """Post a message to Slack via the incoming webhook."""
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
    """Post a message to Telegram via the bot API."""
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


#function that gets called when the schedule fires

def handler(event, context):
    """Lambda entry point. Checks Config for tag violations and alerts on new findings."""
    evaluation_results = get_non_compliant_resources(CONFIG_RULE_NAME)
    findings = []
    for r in evaluation_results:
        one_finding = build_finding(r)
        findings.append(one_finding)


    new_findings = []
    for finding in findings:
        if is_new_finding(finding["finding_id"]):
            write_finding_to_dynamodb(finding)
            new_findings.append(finding)

    if not new_findings:
        message = "No new tag violations. Silent run."
        print(message)
        return {"statusCode": 200, "body": message}

    summary = build_summary(new_findings)
    print(summary)
    notify_slack(summary)
    notify_telegram(summary)
    return {"statusCode": 200, "body": summary}


