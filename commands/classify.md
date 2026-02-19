---
name: classify
aliases: [classify-emails]
description: Analyze recent unread emails and classify them into categories (receipts, newsletters, promotions)
usage: /classify [count]
examples:
  - /classify
  - /classify 20
help_text: |
  Analyzes your recent unread emails and classifies them into smart categories.

  The classifier will:
  1. Fetch recent unread emails from Gmail
  2. Analyze each email for patterns (receipts, newsletters, promotions)
  3. Calculate confidence scores for each classification
  4. Show you a summary with suggested actions
  5. Queue actions for your review

  Usage: /classify [count]
    count - Number of emails to process (default: 10)

  Example: /classify 20
---

# Classify Recent Emails

I'll analyze your recent unread emails and organize them into smart categories.

```bash
# Default: process 10 recent unread emails
/classify

# Or specify how many to analyze
/classify 20
```

## What This Does

1. **Fetches** recent unread emails from your Gmail inbox
2. **Analyzes** each email for patterns:
   - **Receipts**: Orders, confirmations, invoices
   - **Newsletters**: Subscriptions, digests, updates
   - **Promotions**: Sales, discounts, offers
3. **Calculates** confidence for each classification
4. **Shows** you a summary with suggested actions
5. **Queues** actions for your review before applying

## Example Output

```
📊 Classification Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━

Processed: 12 unread emails

📦 Receipts (6 found, confidence: 95%)
  ✓ Amazon - Order Confirmation (#123456)
  ✓ Stripe - Payment Receipt
  ✓ PayPal - Transaction Confirmation
  + 3 more
  Action: Archive

📰 Newsletters (4 found, confidence: 78%)
  ⚠ TechCrunch Daily (High quality)
  ⚠ Product Hunt Digest (Medium quality)
  ⚠ Email newsletter (Low quality)
  + 1 more
  Action: Review next

🎉 Promotions (2 found, confidence: 85%)
  ✓ Store.com - 50% OFF Sale
  ✓ Amazon Prime - Exclusive Offer
  Action: Archive

━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ready to proceed? Use /review-suggestions
```

## Next Steps

After classifying, run:

```
/review-suggestions
```

This will let you approve, reject, or adjust the suggested actions before they're applied.

## Tips

- Use higher counts (20-30) for first run to train the classifier
- The classifier learns from your feedback to improve over time
- Your learned preferences are stored and applied automatically
- You can always undo actions or adjust the configuration with `/organize-config`
