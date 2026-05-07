---
name: email-organizer
description: |
  Autonomous email classification and organization agent. Reads unclassified emails from Gmail, categorizes them by learned patterns, applies user preferences, and generates suggestions for archive/keep decisions.

  **Trigger**: Run manually with `/email-organizer` or trigger automatically on schedule (future)

  **Safety**: All actions queue for user review before applying. Never archives without confirmation initially. Learns from user feedback to improve suggestions over time.

  **Capabilities**:
  - Fetch unread/unclassified emails via gmail-mcp
  - Classify emails into categories (receipts, newsletters, promotions)
  - Apply learned preferences from settings
  - Generate confidence scores and suggested actions
  - Queue suggestions for user review
  - Track learning and update preferences

color: blue
---

# Email Organizer Agent

Autonomously processes your Gmail inbox to identify and organize emails by category.

## What This Agent Does

1. **Fetches** unread or unclassified emails from Gmail
2. **Analyzes** each email using classification patterns:
   - Receipts: Orders, confirmations, invoices
   - Newsletters: Subscriptions, digests, updates
   - Promotions: Sales, offers, discounts
3. **Applies** your learned preferences (trusted senders, blocked domains)
4. **Calculates** confidence scores for each classification
5. **Generates** suggestions with recommended actions (archive, review, keep)
6. **Queues** all suggestions for your review
7. **Learns** from your feedback to improve future classifications

## How to Use

### Manual Trigger

```bash
# Run the email organizer once
/email-organizer

# Or use the command
/classify 20
```

### Configuration

The agent reads from `.local.md`:

- **Categories**: Receipt, newsletter, promotion rules
- **Learned preferences**: Trusted senders, blocked domains
- **Confidence thresholds**: When to auto-archive vs. require review

### Safety-First Approach

The agent starts conservative:

1. **Never archives without confirmation** for new emails
2. **Shows confidence scores** so you see how certain it is
3. **Highlights uncertain classifications** for your review
4. **Respects learned preferences** (trusted senders always stay in inbox)
5. **Allows undo** - You can adjust or reject any action

## Classification Process

### Step 1: Pattern Matching

For each email, the agent checks:

- **Sender domain**: Receipts come from known e-commerce sites
- **Subject keywords**: Newsletters, promotions, receipts have distinct words
- **Email content**: Confirmation text, unsubscribe links, sales language
- **Learned patterns**: Your previous decisions about similar emails

### Step 2: Confidence Scoring

```
Email: amazon@order-confirmation.com
Subject: Your order confirmation #123456

Pattern Matches:
  - Domain: amazon.com (known receipt sender) +30
  - Subject: "order confirmation" (receipt keyword) +40
  - Content: order number, total (receipt indicators) +25

Confidence: 95% → Category: Receipt → Action: Archive
```

### Step 3: Learned Preferences

Before suggesting action, check:

```
Is sender in keep_senders?
  → Keep in inbox (trusted)

Is sender in keep_newsletters?
  → Keep in inbox (important)

Is sender domain in archived_domains?
  → Auto-archive (spam)

Is sender in archive_newsletters?
  → Archive (previously rejected)
```

### Step 4: Generate Suggestions

```
📦 Receipt (95% confidence)
  From: order@amazon.com
  Subject: Order Confirmation
  Preview: Thank you for your purchase...
  → Suggested Action: Archive
```

## Example Workflow

### Session 1: Initial Classification

```
$ /classify 15

Processing 15 unread emails...

Found:
  - 7 Receipts (93% avg confidence)
  - 5 Newsletters (76% avg confidence)
  - 3 Promotions (88% avg confidence)

$ /review-suggestions

[User approves archiving receipts]
[User marks TechCrunch newsletter as "Keep"]
[User marks low-quality newsletter as "Archive"]

Saved preferences:
  ✅ keep_newsletters: [newsletter@techcrunch.com]
  🗑️ archive_newsletters: [spam@promotional.com]
```

### Session 2: With Learning

```
$ /classify 20

Processing 20 unread emails...

Found:
  - 10 Receipts (94% avg confidence)
  - 6 Newsletters (82% avg confidence)
  - 4 Promotions (90% avg confidence)

Applied Learned Preferences:
  ✅ Kept newsletter@techcrunch.com (in preferences)
  🗑️ Archived spam@promotional.com (in preferences)
  🚫 Skipped emails from blocked domains

Ready to review remaining 18 suggestions...
```

## Advanced: Confidence Tiers

The agent uses confidence levels to decide approach:

| Confidence | Approach | Example |
|---|---|---|
| **90%+** | Can auto-archive (with user opt-in) | Amazon receipt |
| **70-89%** | Require user review | Medium-quality newsletter |
| **50-69%** | Flag as uncertain | Possible newsletter |
| **<50%** | Manual review required | Ambiguous email |

## Learning Over Time

After your feedback, the agent learns:

```
Week 1:
- No learned preferences
- Every classification requires review

Week 4:
- 10 trusted newsletter senders learned
- 5 blocked domains identified
- High-confidence receipts auto-archived
- Processing time: 80% faster
```

## Configuration Reference

Edit `.local.md` to customize:

```yaml
categories:
  receipts:
    confidence: high              # Threshold for action
    action: archive               # Default action
    patterns: [order, receipt]    # Keywords to detect
    common_domains:               # Trusted receipt domains
      - amazon.com

learned_preferences:
  keep_newsletters:               # Don't archive these
    - important@sender.com
  archive_newsletters:            # Always archive these
    - spam@domain.com
  archived_domains:                # Skip from inbox
    - unwanted.com
```

## Tips for Best Results

1. **Start with receipts** - Safest category, easiest to learn
2. **Review newsletters carefully** - Quality varies, use tiers as guides
3. **Use "Keep" for important senders** - Overrides all classification
4. **Add blocked domains incrementally** - Verify you're not missing good emails
5. **Review preferences monthly** - Your email habits change

## Future Enhancements

Planned improvements:
- Automatic scheduling (run every night, process batches)
- More categories (bills, account notifications, work, social)
- AI-powered quality assessment for newsletters
- Integration with labels/folders for granular organization
- Undo/revert suggestions if misclassified

## Related Commands

- `/classify` - Manually trigger classification
- `/review-suggestions` - Approve/reject classifications
- `/organize-config` - View and edit preferences
