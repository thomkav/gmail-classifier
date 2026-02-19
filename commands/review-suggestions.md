---
name: review-suggestions
aliases: [review, approve-suggestions]
description: Review and approve/reject classification suggestions before applying actions
usage: /review-suggestions
examples:
  - /review-suggestions
help_text: |
  Review the emails classified by /classify and decide what to do with each one.

  For each suggestion you can:
  - ✅ Approve - Apply the suggested action (archive, keep, etc.)
  - ❌ Reject - Keep the email in inbox, don't apply action
  - 📌 Add to preferences - Remember this decision for future emails from this sender

  This helps the classifier learn your preferences over time.
---

# Review Classification Suggestions

Review each classified email and decide whether to approve or reject the suggested action.

```bash
/review-suggestions
```

## Review Workflow

For each email, you'll see:

```
From: sender@example.com
Subject: Order Confirmation - Your Purchase #123456
Preview: Thank you for your order...

Category: 📦 Receipt
Confidence: 95%
Suggested Action: Archive
━━━━━━━━━━━━━━━━━━━━━━━━

Choose: [✅ Approve] [❌ Reject] [📌 Learn] [Skip]
```

### Options

**✅ Approve**
- Applies the suggested action (archive, keep, etc.)
- Email is moved accordingly
- Continues to next email

**❌ Reject**
- Keeps email in inbox
- Don't apply the suggested action
- Continues to next email

**📌 Learn**
- Approves the action
- Adds this sender to preferences:
  - "Always archive from this sender"
  - "Always keep from this sender"
  - Add to blocked domains (if spam)
- Future emails from this sender bypass classification

**Skip**
- Leave for later review
- Don't apply action yet
- Continues to next email

## Learning Example

```
From: newsletter@techcrunch.com
Subject: TechCrunch Daily - Feb 18, 2026
Category: 📰 Newsletter (High Quality)
Suggested Action: Keep in inbox

[📌 Learn]
→ Adds "newsletter@techcrunch.com" to keep_newsletters
→ Future emails from this sender stay in inbox automatically
```

## Quality Tiers for Newsletters

The classifier assesses newsletter quality:

- **🌟 High Quality**: Keep in inbox
  - Professional, well-researched content
  - Regular author/publication
  - You've engaged recently

- **⭐ Medium Quality**: Review periodically
  - Decent content, decent depth
  - Established source
  - You've read but don't prioritize

- **Low Quality**: Archive
  - Generic, template-like
  - Daily/frequent sends
  - You haven't engaged

## Tips

1. **Start with receipts first** - They're high confidence and safe to archive
2. **Review newsletters carefully** - Quality varies, use the tiers as guides
3. **Use "Learn" for frequent senders** - Speeds up future processing
4. **Check previews** - Make sure classification makes sense
5. **You can always undo** - Adjust preferences with `/organize-config`

## After Review

Once you've reviewed all suggestions:

```
Complete! ✅
- 6 emails archived
- 4 emails kept
- 2 senders added to preferences

Run /classify again to process more emails or configure with /organize-config
```

## See Also

- `/classify` - Analyze and classify new emails
- `/organize-config` - View and edit your preferences
