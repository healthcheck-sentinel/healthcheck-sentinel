"""Explicit Slack connectivity test. Reads .env locally; never prints credentials."""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from chatops.slack_client import SlackClient
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send-test', action='store_true', help='Send a clearly labeled test message to configured Slack')
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    client = SlackClient()
    values = [v for v in (client.webhook_url, client.bot_token) if v]
    configured = any(not any(p in v.lower() for p in ('your-', 'your_', 'placeholder', 'xxxx', 'changeme')) for v in values)
    if not configured:
        print('BLOCKED: configure SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN privately in .env; do not paste it in chat.')
        return 2
    if not client.webhook_url and not os.getenv('SLACK_ALERT_CHANNEL'):
        print('BLOCKED: bot delivery also needs SLACK_ALERT_CHANNEL.')
        return 2
    if not args.send_test:
        print('Slack settings present. Use --send-test to send an explicit connectivity-test message.')
        return 0
    try:
        client.send_message({'text': 'Healthcheck Sentinel: submission connectivity test. This is a test message, not a detected outage.'}, channel=os.getenv('SLACK_ALERT_CHANNEL'))
    except Exception as exc:
        print(f'FAIL Slack delivery ({type(exc).__name__}); credentials and response details are suppressed.')
        return 1
    print('PASS Slack accepted the connectivity-test message. Confirm it is visible in the intended channel.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
