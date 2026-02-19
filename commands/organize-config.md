---
name: organize-config
aliases: [config, preferences, settings]
description: View and configure email classification rules and learned preferences
usage: /organize-config [action]
examples:
  - /organize-config
  - /organize-config view
  - /organize-config edit
help_text: |
  View and edit your email classification configuration.

  Actions:
  - view  - Show current configuration and learned preferences
  - edit  - Edit categories, rules, and trusted senders
  - reset - Reset a preference or category (use with caution)

  Usage: /organize-config [view|edit|reset]
---

# Configure Email Classification

Manage your email classification rules and learned preferences.

```bash
# View current configuration
/organize-config view

# Edit configuration (open editor)
/organize-config edit

# Reset preferences
/organize-config reset
```

## Configuration Structure

Your settings are stored in `.local.md` with these sections:

### Categories

Define classification rules for each email type:

```yaml
categories:
  receipts:
    confidence: high
    label: "receipts"
    action: archive
    patterns: [order, receipt, invoice, confirmation]
    common_domains: [amazon.com, ebay.com, stripe.com, paypal.com]

  newsletters:
    confidence: medium
    label: "newsletters"
    action: review
    quality_tiers: [high, medium, low]
    patterns: [newsletter, digest, subscription]

  promotions:
    confidence: medium
    label: "promotions"
    action: archive
    patterns: [sale, discount, offer, promo]
```

### Learned Preferences

Track your decisions over time:

```yaml
learned_preferences:
  keep_newsletters:
    - newsletter@techcrunch.com
    - digest@morning.news

  archive_newsletters:
    - spam@promotional.com

  keep_senders:
    - boss@company.com
    - friend@personal.com

  blocked_domains:
    - unwanted-spam.com
```

## Common Configuration Tasks

### Add a Newsletter to "Keep"

```yaml
learned_preferences:
  keep_newsletters:
    - existing-newsletter@example.com
    - new-newsletter@techsite.com  # Add this
```

After editing, the classifier will automatically keep emails from `new-newsletter@techsite.com` in your inbox.

### Add a Blocked Domain

```yaml
learned_preferences:
  blocked_domains:
    - unwanted-spam.com
    - promotional-blasts.net  # Add this
```

Emails from blocked domains won't appear in inbox classification suggestions.

### Adjust Receipt Pattern Keywords

```yaml
categories:
  receipts:
    patterns:
      - order
      - receipt
      - invoice
      - confirmation
      - shipment        # Add this
      - tracking        # Add this
      - delivery        # Add this
```

### Change Promotion Action

```yaml
categories:
  promotions:
    action: archive  # or: review, keep
    confidence: medium
```

## View Current Configuration

```bash
/organize-config view
```

Shows:

```
📋 Email Classification Configuration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏷️ Categories

📦 Receipts
  Confidence: high
  Action: archive
  Patterns: order, receipt, invoice, confirmation
  Domains: amazon.com, ebay.com, stripe.com, paypal.com

📰 Newsletters
  Confidence: medium
  Action: review
  Quality Tiers: high, medium, low
  Patterns: newsletter, digest, subscription

🎉 Promotions
  Confidence: medium
  Action: archive
  Patterns: sale, discount, offer, promo

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 Learned Preferences

✅ Keep Newsletters (2):
  - newsletter@techcrunch.com
  - digest@morning.news

🗑️ Archive Newsletters (1):
  - spam@promotional.com

👤 Keep Senders (2):
  - boss@company.com
  - friend@personal.com

🚫 Blocked Domains (1):
  - unwanted-spam.com
```

## Edit Configuration

```bash
/organize-config edit
```

Opens your `.local.md` file for editing. You can:

1. Add/remove newsletter senders to keep or archive
2. Add blocked domains
3. Adjust confidence thresholds
4. Modify category patterns
5. Change default actions

After editing, the classifier uses your updated preferences immediately.

## Reset Preferences

```bash
/organize-config reset [category]
```

Reset specific preferences:

```bash
# Clear all learned newsletters
/organize-config reset newsletters

# Clear blocked domains
/organize-config reset blocked_domains

# Reset everything (use with caution!)
/organize-config reset all
```

## Tips

1. **Start with defaults** - The initial configuration covers most cases
2. **Add learned preferences incrementally** - Use `/review-suggestions` to identify patterns
3. **Verify blocked domains** - Make sure you're not blocking important senders
4. **Review periodically** - Update your preferences as your email habits change
5. **Use patterns carefully** - Overly broad patterns might catch unintended emails

## Example: Customizing for Your Workflow

```yaml
# Add specific newsletter senders you love
learned_preferences:
  keep_newsletters:
    - daily@morning-briefing.com
    - weekly@substack-writer.com

# Add common promotional domains you don't want
learned_preferences:
  blocked_domains:
    - flash-sale-spam.com
    - daily-deal-blast.net

# Adjust confidence for your risk tolerance
categories:
  newsletters:
    confidence: high  # Be more aggressive with archiving
```

## See Also

- `/classify` - Analyze and classify new emails
- `/review-suggestions` - Approve/reject classifications
- Email Organization Strategy skill - Learn classification patterns
