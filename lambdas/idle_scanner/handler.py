import boto3
import json
import urllib.request
import uuid
from datetime import datetime, timezone


# --- Notifiers (duplicated from cost_digest; will refactor to Lambda Layer later) ---

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


# --- EBS scanning ---

def find_unattached_volumes():
    """Return all EBS volumes with status 'available' (not attached to any instance)."""
    ec2 = boto3.client("ec2")
    response = ec2.describe_volumes(
        Filters=[{"Name": "status", "Values": ["available"]}]
    )
    return response["Volumes"]


def build_finding(volume):
    """Convert an EBS volume dict into a finding record."""
    size_gb = volume["Size"]
    # gp3 pricing baseline ($0.08/GB/month) — rough estimate, actual varies by type
    est_monthly_cost = size_gb * 0.08

    return {
        "finding_id": str(uuid.uuid4()),
        "resource_id": volume["VolumeId"],
        "resource_type": "ebs_volume",
        "category": "idle_ebs",
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "size_gb": size_gb,
        "volume_type": volume.get("VolumeType", "unknown"),
        "availability_zone": volume.get("AvailabilityZone", "unknown"),
        "estimated_monthly_cost": round(est_monthly_cost, 2),
    }


def write_finding_to_dynamodb(finding):
    """Save a finding to the watchdog-findings table."""
    dynamodb = boto3.client("dynamodb")
    dynamodb.put_item(
        TableName="watchdog-findings",
        Item={
            "finding_id":               {"S": finding["finding_id"]},
            "resource_id":              {"S": finding["resource_id"]},
            "resource_type":            {"S": finding["resource_type"]},
            "category":                 {"S": finding["category"]},
            "detected_at":              {"S": finding["detected_at"]},
            "size_gb":                  {"N": str(finding["size_gb"])},
            "volume_type":              {"S": finding["volume_type"]},
            "availability_zone":        {"S": finding["availability_zone"]},
            "estimated_monthly_cost":   {"N": str(finding["estimated_monthly_cost"])},
        },
    )


def build_summary(findings):
    """Human-readable text summarizing what was found."""
    if not findings:
        return "Idle scan: no unattached EBS volumes found."

    total_cost = sum(f["estimated_monthly_cost"] for f in findings)
    lines = [
        f"Idle scan: {len(findings)} unattached EBS volume(s) found",
        f"Estimated waste: ${total_cost:.2f}/mo",
        "",
        "Details:",
    ]
    for f in findings:
        lines.append(
            f"  {f['resource_id']}: {f['size_gb']} GB {f['volume_type']} "
            f"in {f['availability_zone']}, ~${f['estimated_monthly_cost']:.2f}/mo"
        )
    return "\n".join(lines)


# --- Handler ---

def handler(event, context):
    volumes = find_unattached_volumes()

    findings = []
    for volume in volumes:
        finding = build_finding(volume)
        findings.append(finding)
        write_finding_to_dynamodb(finding)

    summary = build_summary(findings)
    print(summary)

    notify_slack(summary)
    notify_telegram(summary)

    return {"statusCode": 200, "body": summary}
