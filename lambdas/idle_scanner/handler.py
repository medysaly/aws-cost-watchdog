import boto3 
from collections import defaultdict
from datetime import datetime, timezone, timedelta




# Scanners for idle resources in AWS

def find_unattached_volumes():
    """EBS volumes with status 'available' (not attached to any instance)."""
    ec2 = boto3.client('ec2')
    response = ec2.describe_volumes(
        Filters=[{'Name': 'status', 'Values': ['available']}]
        )
    return response['Volumes']


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


#Builders for findings

def build_ebs_finding(volume):
    """Build a finding dictionary for each unattached EBS volume."""
    resource_id = volume["VolumeId"]
    size_gb = volume["Size"]
    return {
        "finding_id":              f"idle_ebs:{resource_id}",
        "resource_id":             resource_id,
        "resource_type":           "ebs_volume",
        "category":                "idle_ebs",
        "detected_at":             datetime.now(timezone.utc).isoformat(),
        "size_gb":                 size_gb,
        "volume_type":             volume.get("VolumeType", "unknown"),
        "availability_zone":       volume.get("AvailabilityZone", "unknown"),
        "estimated_monthly_cost":  round(size_gb * 0.08, 2),
    }


def build_ec2_finding(instance):
    """Build a finding dictionary for one stopped EC2 instance."""
    resource_id = instance["InstanceId"]
    return {
        "finding_id":              f"stopped_ec2:{resource_id}",
        "resource_id":             resource_id,
        "resource_type":           "ec2_instance",
        "category":                "stopped_ec2",
        "detected_at":             datetime.now(timezone.utc).isoformat(),
        "instance_type":           instance.get("InstanceType", "unknown"),
        "availability_zone":       instance.get("Placement", {}).get("AvailabilityZone", "unknown"),
        "estimated_monthly_cost":  0,
    }


def build_s3_finding(bucket):
    """Build a finding dictionary for one empty S3 bucket."""
    resource_id = bucket["Name"]
    return {
        "finding_id":              f"empty_s3:{resource_id}",
        "resource_id":             resource_id,
        "resource_type":           "s3_bucket",
        "category":                "empty_s3",
        "detected_at":             datetime.now(timezone.utc).isoformat(),
        "creation_date":           bucket["CreationDate"].isoformat(),
        "estimated_monthly_cost":  0,
    }


def build_snapshot_finding(snapshot):
    """Build a finding dictionary for one old EBS snapshot."""
    size_gb = snapshot.get("VolumeSize", 0)
    age_days = (datetime.now(timezone.utc) - snapshot["StartTime"]).days
    resource_id = snapshot["SnapshotId"]
    return {
        "finding_id":              f"old_snapshot:{resource_id}",
        "resource_id":             resource_id,
        "resource_type":           "ebs_snapshot",
        "category":                "old_snapshot",
        "detected_at":             datetime.now(timezone.utc).isoformat(),
        "size_gb":                 size_gb,
        "age_days":                age_days,
        "estimated_monthly_cost":  round(size_gb * 0.05, 2),
    }


#checking if a finding is new and writing to DynamoDB

def is_new_finding(finding_id):
    """Check if a finding with this ID already exists in DynamoDB."""
    dynamodb = boto3.client("dynamodb")
    response = dynamodb.get_item(
        TableName="watchdog-findings",
        Key={"finding_id": {"S": finding_id}}
    )
    return "Item" not in response


def write_finding_to_dynamodb(finding):
    """Write a finding to DynamoDB."""
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



CATEGORY_LABELS = {
    # Human-readable labels for each category of finding
    "idle_ebs":      "Unattached EBS volumes",
    "stopped_ec2":   "Stopped EC2 instances",
    "empty_s3":      "Empty S3 buckets",
    "old_snapshot":  "Old EBS snapshots (>90 days)",
}

def format_finding(finding):
    """Turn one finding into a short readable string for Slack/Telegram."""
    category = finding["category"]
    resource_id = finding["resource_id"]
    if category == "idle_ebs":
        return f"  {resource_id} is unattached, {finding['size_gb']} GB {finding['volume_type']}, wasting ~${finding['estimated_monthly_cost']:.2f}/month"
    if category == "stopped_ec2":
        return f"  {resource_id} is stopped, {finding['instance_type']} instance"
    if category == "empty_s3":
        return f"  {resource_id} is empty"
    if category == "old_snapshot":
        return f"  {resource_id} is {finding['age_days']} days old, {finding['size_gb']} GB, costing ~${finding['estimated_monthly_cost']:.2f}/month"  
    return f"  {resource_id}"


def build_summary(findings):
    """Turn a list of findings into a summary string for Slack/Telegram."""
    total_cost = sum(f["estimated_monthly_cost"] for f in findings)
    by_category = defaultdict(list)
    for f in findings:
        by_category[f["category"]].append(f)

    lines = [
        f"Hey, found {len(findings)} things worth cleaning up, costing about ${total_cost:.2f}/month total.",
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



