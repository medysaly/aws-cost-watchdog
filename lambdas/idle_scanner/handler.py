import boto3
import json
import urllib.request
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta


# --- Notifiers (unchanged; duplicated from other Lambdas — refactor to Layer later) ---

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


# --- Scanners ---

def find_unattached_volumes():
    """EBS volumes with status 'available' (not attached to any instance)."""
    ec2 = boto3.client("ec2")
    response = ec2.describe_volumes(
        Filters=[{"Name": "status", "Values": ["available"]}]
    )
    return response["Volumes"]


def find_stopped_ec2_instances():
    """EC2 instances in the 'stopped' state."""
    ec2 = boto3.client("ec2")
    response = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
    )
    instances = []
    for reservation in response["Reservations"]:
        instances.extend(reservation["Instances"])
    return instances


def find_empty_s3_buckets():
    """S3 buckets with zero objects."""
    s3 = boto3.client("s3")
    buckets = s3.list_buckets()["Buckets"]
    empty = []
    for bucket in buckets:
        try:
            objects = s3.list_objects_v2(Bucket=bucket["Name"], MaxKeys=1)
            if objects.get("KeyCount", 0) == 0:
                empty.append(bucket)
        except Exception as e:
            print(f"Could not list bucket {bucket['Name']}: {e}")
    return empty


def find_old_snapshots(days=90):
    """EBS snapshots owned by this account older than N days."""
    ec2 = boto3.client("ec2")
    response = ec2.describe_snapshots(OwnerIds=["self"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [s for s in response["Snapshots"] if s["StartTime"] < cutoff]


# --- Finding builders (one per resource type) ---

def build_ebs_finding(volume):
    size_gb = volume["Size"]
    return {
        "finding_id":              str(uuid.uuid4()),
        "resource_id":             volume["VolumeId"],
        "resource_type":           "ebs_volume",
        "category":                "idle_ebs",
        "detected_at":             datetime.now(timezone.utc).isoformat(),
        "size_gb":                 size_gb,
        "volume_type":             volume.get("VolumeType", "unknown"),
        "availability_zone":       volume.get("AvailabilityZone", "unknown"),
        "estimated_monthly_cost":  round(size_gb * 0.08, 2),
    }


def build_ec2_finding(instance):
    return {
        "finding_id":              str(uuid.uuid4()),
        "resource_id":             instance["InstanceId"],
        "resource_type":           "ec2_instance",
        "category":                "stopped_ec2",
        "detected_at":             datetime.now(timezone.utc).isoformat(),
        "instance_type":           instance.get("InstanceType", "unknown"),
        "availability_zone":       instance.get("Placement", {}).get("AvailabilityZone", "unknown"),
        "estimated_monthly_cost":  0,
    }


def build_s3_finding(bucket):
    return {
        "finding_id":              str(uuid.uuid4()),
        "resource_id":             bucket["Name"],
        "resource_type":           "s3_bucket",
        "category":                "empty_s3",
        "detected_at":             datetime.now(timezone.utc).isoformat(),
        "creation_date":           bucket["CreationDate"].isoformat(),
        "estimated_monthly_cost":  0,
    }


def build_snapshot_finding(snapshot):
    size_gb = snapshot.get("VolumeSize", 0)
    age_days = (datetime.now(timezone.utc) - snapshot["StartTime"]).days
    return {
        "finding_id":              str(uuid.uuid4()),
        "resource_id":             snapshot["SnapshotId"],
        "resource_type":           "ebs_snapshot",
        "category":                "old_snapshot",
        "detected_at":             datetime.now(timezone.utc).isoformat(),
        "size_gb":                 size_gb,
        "age_days":                age_days,
        "estimated_monthly_cost":  round(size_gb * 0.05, 2),
    }


# --- DynamoDB write (generic, auto-types values) ---

def write_finding_to_dynamodb(finding):
    """Save a finding. Auto-detects String vs Number types."""
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

def format_finding(finding):
    """One-line human-readable string per finding."""
    cat = finding["category"]
    rid = finding["resource_id"]
    if cat == "idle_ebs":
        return f"  {rid}: {finding['size_gb']} GB {finding['volume_type']}, ~${finding['estimated_monthly_cost']:.2f}/mo"
    if cat == "stopped_ec2":
        return f"  {rid}: {finding['instance_type']} stopped"
    if cat == "empty_s3":
        return f"  {rid}: empty bucket"
    if cat == "old_snapshot":
        return f"  {rid}: {finding['size_gb']} GB, {finding['age_days']} days old, ~${finding['estimated_monthly_cost']:.2f}/mo"
    return f"  {rid}"


CATEGORY_LABELS = {
    "idle_ebs":      "Unattached EBS volumes",
    "stopped_ec2":   "Stopped EC2 instances",
    "empty_s3":      "Empty S3 buckets",
    "old_snapshot":  "Old EBS snapshots (>90 days)",
}


def build_summary(findings):
    if not findings:
        return "Idle scan: nothing to clean up."

    total_cost = sum(f["estimated_monthly_cost"] for f in findings)

    by_category = defaultdict(list)
    for f in findings:
        by_category[f["category"]].append(f)

    lines = [
        f"Idle scan: {len(findings)} finding(s), estimated waste ${total_cost:.2f}/mo",
        "",
    ]
    for cat_key, cat_label in CATEGORY_LABELS.items():
        cat_findings = by_category.get(cat_key, [])
        if not cat_findings:
            continue
        lines.append(f"{cat_label} ({len(cat_findings)}):")
        for f in cat_findings:
            lines.append(format_finding(f))
        lines.append("")

    return "\n".join(lines).strip()


# --- Handler ---

def handler(event, context):
    findings = []

    # Run each scanner
    for volume in find_unattached_volumes():
        findings.append(build_ebs_finding(volume))

    for instance in find_stopped_ec2_instances():
        findings.append(build_ec2_finding(instance))

    for bucket in find_empty_s3_buckets():
        findings.append(build_s3_finding(bucket))

    for snapshot in find_old_snapshots():
        findings.append(build_snapshot_finding(snapshot))

    # Persist all findings
    for finding in findings:
        write_finding_to_dynamodb(finding)

    # Build and send summary
    summary = build_summary(findings)
    print(summary)

    notify_slack(summary)
    notify_telegram(summary)

    return {"statusCode": 200, "body": summary}
