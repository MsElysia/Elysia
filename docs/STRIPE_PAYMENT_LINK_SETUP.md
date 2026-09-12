# Stripe Payment Link Setup

## Why This Is The Pick
Use `Stripe Payment Links` first for `Capability Gap Remediation Sprint`.

Why this path:
- no-code checkout
- reusable payment link
- works for a product or service
- faster than building a custom checkout flow

## First Launch Goal
Create one live payment link for:
- `Signal Test` at `$79`

You can add the `$199` `Operator Sprint` link after the first page is live.

## Step-by-Step
1. Create a Stripe account.
2. Verify the business email and enable two-factor authentication.
3. Finish Stripe onboarding:
   - legal name
   - business details
   - payout bank account
   - tax information
4. In Stripe, create a product:
   - name: `Capability Gap Remediation Sprint`
   - description: use the short description from [FIRST_OFFER_LAUNCH_BUNDLE.md](</C:/Users/mrnat/Project guardian/docs/FIRST_OFFER_LAUNCH_BUNDLE.md>)
5. Create a one-time price for the first test:
   - `$79`
   - label: `Signal Test`
6. Create a `Payment Link` for that price.
7. Set the page details:
   - logo if available
   - brand color if available
   - call to action: `Book` or `Pay`
   - confirmation message: thank the buyer and tell them what happens next
8. Copy the live payment link.
9. Paste that link into your outreach message from [FIRST_OFFER_LAUNCH_BUNDLE.md](</C:/Users/mrnat/Project guardian/docs/FIRST_OFFER_LAUNCH_BUNDLE.md>).
10. Send it to 3 real prospects and log responses in [FIRST_BUYER_SIGNAL_LOG.md](</C:/Users/mrnat/Project guardian/docs/FIRST_BUYER_SIGNAL_LOG.md>).

## Suggested Confirmation Message
Thanks for your purchase. You will receive a short follow-up message with the next step and delivery expectations.

## What To Save Immediately
```text
platform=Stripe Payment Links
product_name=Capability Gap Remediation Sprint
price_signal_test=79
payment_link_url=
product_id=
price_id=
support_email=
date_link_created=
```

## Best First-Test Rule
Start with one link, one price, and one audience.

Do not add:
- too many pricing tiers
- custom automation
- a complicated intake form
- multiple offers at once

## After The First 3 Responses
Only change one thing:
- headline
- short description
- price
- target buyer

## Next Stripe Upgrade
After the first useful buyer signal:
1. create the `$199` `Operator Sprint` price
2. create a second payment link
3. add a short post-purchase intake question flow if needed
