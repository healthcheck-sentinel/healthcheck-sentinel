# Submission checklist

## Repository checks

- [x] Preserve the implemented monitoring architecture and existing tests.
- [x] Add localhost-only Compose port publishing.
- [x] Exclude raw exception/URL strings from Slack evidence.
- [x] Run the expanded automated suite: 52 passed, 74% coverage.
- [x] Check tracked/new non-ignored files for common credential patterns; no matches. `.env` remains ignored. This scan is not a guarantee that every possible secret format is detected.
- [x] Prepare DEMO.md, docs/SUBMISSION.md and docs/RUBRIC.md.
- [x] Add read-only preflight and secret-free Slack configuration/test helpers.
- [x] Fresh full Docker run passed; see docs/FINAL_RESULTS.md and docs/submission-validation.json.

## Submitter-owned steps

- [ ] Configure a real Slack webhook privately in `.env` if Slack workspace delivery is required. Run `python scripts/verify_slack.py --send-test`. Never include `.env` in an upload.
- [ ] Record the three-minute demo using DEMO.md; preview audio and screen readability.
- [ ] Enter team/member names and platform-specific fields in the submission form.
- [ ] Ensure judges can access the repository and video link.
- [ ] Upload/submit and verify the confirmation page before the deadline.

## Deferred rather than misrepresented

Kubernetes deployment, durable incident/outbox storage, automatic notification retries, distributed monitoring and interactive Slack restart controls. The demo can be submitted with these clearly disclosed limitations.
