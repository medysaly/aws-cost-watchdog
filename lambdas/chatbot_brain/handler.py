import boto3


MODEL_ID = "anthropic.claude-sonnet-5"


def handler(event, context):
    """Send a prompt to Claude Sonnet 5 via Bedrock and return the answer."""
    prompt = event.get("prompt", "Hello, are you working?")

    client = boto3.client("bedrock-runtime", region_name="us-east-1")

    messages = [
        {
            "role": "user",
            "content": [{"text": prompt}]
        }
    ]

    response = client.converse(
        modelId=MODEL_ID,
        messages=messages,
        inferenceConfig={"maxTokens": 1024}
    )

    answer = response["output"]["message"]["content"][0]["text"]

    return {"statusCode": 200, "body": answer}
