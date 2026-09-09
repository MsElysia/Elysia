# Transaction Setup Checklist

## Goal
Set up one seller account and one live payment link so Elysia has a real place to point buyers.

## Recommended First Path
Use a simple digital-product storefront first.

Why:
- fastest route to a first transaction
- no custom checkout build required
- easy to attach one offer page and one payment link

Recommended first offer:
- `Capability gap remediation sprint`
- `Signal Test` at `$79`
- `Operator Sprint` at `$199`

## Step-by-Step
1. Create a seller account with a business email you control.
2. Verify the email and turn on two-factor authentication.
3. Fill in the seller profile:
   - display name
   - short bio
   - support email
   - payout country
4. Complete identity and tax onboarding so payouts are allowed.
5. Connect the bank account or payout method you want to use.
6. Create one product for the first sellable offer:
   - name: `Capability gap remediation sprint`
   - format: service, digital product, or fixed-scope deliverable
   - short description: use the offer-pack `one_liner`
7. Add two pricing options:
   - `Signal Test` for `$79`
   - `Operator Sprint` for `$199`
8. Paste the buyer-facing copy from the offer pack:
   - problem
   - deliverables
   - why buy now
   - validation question
9. Publish the product and generate one live checkout or payment link.
10. Save the important transaction details for Elysia:
   - product URL
   - checkout URL
   - seller account email
   - platform name
   - support email
11. If the platform offers an API key, create one and store it in `.env` or your private config only.
12. Send the live link to one friendly test buyer or one real prospect and record the response.

## Minimum Data To Save After Setup
Save these values in a private operator note or config:

```text
platform=
seller_email=
product_name=Capability gap remediation sprint
product_url=
checkout_url=
price_signal_test=79
price_operator_sprint=199
support_email=
api_key_saved=yes/no
first_test_sent=yes/no
```

## Done When
You are ready to begin transactions when all of these are true:

- the seller account is verified
- payouts are connected
- the product is published
- one live checkout link exists
- one real person has received the link

## Next Step After Account Setup
Once the first link is live, Elysia should switch from "generate more ideas" to:
1. track buyer responses
2. refine the offer page
3. log objections
4. decide whether to keep, reprice, or replace the offer
