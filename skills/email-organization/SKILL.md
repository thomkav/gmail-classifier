# Email Organization Strategy

Learn how to classify and organize emails intelligently using patterns, confidence levels, and learned preferences.

## Core Classification Approach

### Pattern Recognition

Email classification starts with identifying **domain and keyword patterns**:

**Receipts** - Look for:
- Transaction indicators: "order", "receipt", "invoice", "confirmation", "purchase"
- Sender domains: Amazon, eBay, Stripe, PayPal, Square, etc.
- Content clues: order numbers, tracking info, totals
- Confidence: **Very High** - These are straightforward to identify

Example receipt email:
```
From: order-confirmation@amazon.com
Subject: Order Confirmation - Your purchase of [item]
Body: Thank you for your order #123-456-789
```

**Newsletters** - Look for:
- Subscription language: "newsletter", "digest", "weekly update", "monthly summary"
- Sender characteristics: bulk mailer templates, unsubscribe links
- Content: curated content, regular schedule indicators
- Quality assessment: depth of content, personalization, author credibility
- Confidence: **Medium** - Need user input to assess value

Example newsletter email:
```
From: editor@techsite.com
Subject: Weekly Tech Digest #47
Body: This week's top stories: [curated links]
[Unsubscribe]
```

**Promotions** - Look for:
- Marketing language: "limited time", "exclusive", "sale", "discount", "offer"
- Time urgency: "ends today", "24 hours only", "flash sale"
- Visual/formatting clues: CAPS LOCK, multiple exclamation marks
- Sender types: retail brands, product companies, flash sale services
- Confidence: **Medium-High** - Usually obvious but can be deceptive

Example promotional email:
```
From: marketing@store.com
Subject: LIMITED TIME: 50% OFF Everything! ⏰
Body: Hurry! Sale ends tonight!
```

---

## Learning Loop: Confidence → Feedback → Preferences

### Step 1: Initial Classification
1. Analyze sender domain and email content
2. Assign category (receipts, newsletters, promotions)
3. Calculate confidence score (0-100%)
4. Suggest action (archive, review, keep)

### Step 2: User Review
Present classified emails with:
- Category and confidence level
- Suggested action
- Sender and subject preview
- Pattern reasoning (why this category?)

User decides:
- ✅ Approve action
- ❌ Reject (wrong category)
- 📌 Add to preferences (always archive this sender, always keep, etc.)

### Step 3: Preference Updates
Store user decisions:
- **keep_newsletters**: Senders to preserve in inbox
- **archive_newsletters**: Senders to auto-archive
- **keep_senders**: High-trust senders that bypass classification
- **archived_domains**: Spam/unwanted domains

### Step 4: Continuous Improvement
Next time the classifier encounters:
- Learned senders → Apply stored preference immediately
- New senders in blocked domains → Skip inbox
- Trusted senders → Always keep (even if looks promotional)

---

## Quality Tier Assessment for Newsletters

Not all newsletters are equal. Assess quality based on:

**High Quality** (Keep in inbox):
- Professional content, well-researched
- Personalization or customization
- Clear author/publication credibility
- Infrequent, valuable-per-email (weekly or less)
- User has engaged recently

**Medium Quality** (Review periodically):
- Decent content, some value
- Standard template, some personalization
- Established publication
- Moderate frequency (2-3x per week)
- User has engaged but may not prioritize

**Low Quality** (Archive):
- Generic content, minimal effort
- No personalization, template-heavy
- Frequent sends (daily or multiple daily)
- User hasn't engaged or marked as read without opening
- Looks/feels like spam but not quite

---

## Building Effective Filters

### Domain-Based Rules
Most receipts come from known e-commerce domains:
```
amazon.com, ebay.com, stripe.com, paypal.com,
etsy.com, shopify.com, square.com, checkout.com
```

Store these in `archived_domains` for known spam:
```
discount-spam.com, promotional-blast.net, unsolicited-offers.org
```

### Sender Pattern Rules
- **Newsletters**: Often from `newsletter@`, `digest@`, `noreply@` addresses
- **Receipts**: Often from `order@`, `confirmation@`, `billing@` addresses
- **Promotions**: Often from `marketing@`, `sales@`, `deals@` addresses

### Keyword Rules
Build patterns incrementally as you review emails:
- Add new receipt keywords: "shipment", "tracking", "delivery"
- Add new promotion keywords: "hurry", "while supplies last", "exclusive access"
- Refine newsletter patterns: "curated for you", "top picks", "trending"

---

## Safety-First Confirm-Before-Archive Strategy

Always start conservative:

1. **Classify with confidence scoring**
   - High confidence (>90%): Can auto-archive with user opt-in
   - Medium confidence (70-90%): Require review before archiving
   - Low confidence (<70%): Highlight for user decision

2. **Queue all actions for review**
   - Show user summary: "Found 12 receipts, 8 newsletters, 5 promotions"
   - Per-email confirmation for first few of each type
   - After learning, user can opt into auto-archive for high-confidence

3. **User override always available**
   - "Keep in inbox" - adds sender to keep_senders
   - "This isn't a receipt" - removes from suggested action
   - "Always archive from this sender" - adds to archive list

---

## Real-World Example: Newsletter Triage

**Scenario**: User has 47 unread newsletters

1. **Classify all 47**
   - 15 high-quality tech newsletters → tier: high
   - 20 medium-quality product updates → tier: medium
   - 12 low-quality promotional newsletters → tier: low

2. **Show user results**
   ```
   Found 47 newsletters:
   - 15 High Quality (suggest: keep in inbox)
   - 20 Medium Quality (suggest: archive, review 1x/week)
   - 12 Low Quality (suggest: archive)
   ```

3. **User makes decisions**
   - Approves archiving low-quality
   - Keeps 3 high-quality tech newsletters as important
   - Rejects 2 ("Those aren't newsletters!")
   - Adds "techblog@news.com" to keep_newsletters

4. **System learns**
   - Archives 12 low-quality immediately
   - Marks 3 high-quality as priority
   - Removes 2 rejected from consideration
   - Remembers "techblog@news.com" for future

5. **Next run**
   - Finds "techblog@news.com" in keep_newsletters → automatically keeps
   - Classifies new newsletters with updated patterns
   - Shows fewer options (because many are already learned)

---

## Tips & Best Practices

✅ **Do:**
- Start with high-confidence categories (receipts)
- Review user's learned preferences regularly
- Use sender reputation (established senders get trust)
- Explain your reasoning to the user
- Let user incrementally tune filters

❌ **Don't:**
- Archive important emails without confirmation
- Ignore user feedback (it's the learning signal!)
- Over-generalize from single examples
- Use only subject lines (check body content too)
- Forget about sender domain reputation

---

## Expanding Beyond Three Categories

In future phases, add:
- **Bills/Utilities**: Automatic archive, low-confidence review
- **Account Notifications**: Keep in inbox (security-sensitive)
- **Social Media**: Archive or quality-tier like newsletters
- **Work**: Complex rules based on project/sender
- **Personal**: Keep inbox, but can organize into labels

Each new category follows the same pattern:
1. Define clear patterns and confidence rules
2. Show to user for review and feedback
3. Learn preferences over time
4. Adjust confidence thresholds based on accuracy
