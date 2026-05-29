import boto3
from datetime import date, timedelta


def handler(event, context):
    ce = boto3.client("ce")

    today = date.today()
    yesterday = today - timedelta(days=1)

    response = ce.get_cost_and_usage(
        TimePeriod={
            "Start": yesterday.isoformat(),
            "End": today.isoformat(),
        },
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    # Pull out the per-service groups for yesterday
    groups = response["ResultsByTime"][0]["Groups"]

    # Build a list of (service_name, cost) tuples
    services = []
    for group in groups:
        name = group["Keys"][0]
        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
        services.append((name, amount))

    # Sort by cost, highest first
    services.sort(key=lambda item: item[1], reverse=True)

    # Total spend
    total = sum(amount for _, amount in services)

    # Build the summary text
    lines = [f"AWS spend for {yesterday.isoformat()}: ${total:.2f}", "Top services:"]
    for name, amount in services[:5]:
        lines.append(f"  {name}: ${amount:.4f}")

    summary = "\n".join(lines)
    print(summary)

    return {"statusCode": 200, "body": summary}
