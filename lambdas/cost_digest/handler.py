import boto3
import json
import urllib.request
from datetime import date, timedelta


def get_secret(secret_id):
    """Fetch a secret value (as string) from Secrets Manager."""
    sm = boto3.client("secretsmanager")
    response = sm.get_secret_value(SecretId=secret_id)
    return response["SecretString"]


def notify_slack(message):
    """POST a plain-text message to a Slack incoming webhook."""
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
    """Send a message via Telegram bot sendMessage API."""
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

    # Parse and sort by cost descending
    groups = response["ResultsByTime"][0]["Groups"]
    services = [
        (g["Keys"][0], float(g["Metrics"]["UnblendedCost"]["Amount"]))
        for g in groups
    ]
    services.sort(key=lambda item: item[1], reverse=True)
    total = sum(amount for _, amount in services)

    # Build the summary
    lines = [
        f"AWS spend for {yesterday.isoformat()}: ${total:.2f}",
        "Top services:",
    ]
    for name, amount in services[:5]:
        lines.append(f"  {name}: ${amount:.4f}")

    summary = "\n".join(lines)
    print(summary)

    # Send to both notifiers
    notify_slack(summary)
    notify_telegram(summary)

    return {"statusCode": 200, "body": summary}
