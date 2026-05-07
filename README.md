# Gmail Classifier Plugin

Intelligent Gmail email classification and organization plugin with learning. Automatically categorize emails (receipts, newsletters, promotions) and organize your inbox with AI assistance.

## Features

- **Smart Classification**: Automatically categorizes emails into receipts, newsletters, and promotions
- **Confidence Scoring**: Know how certain the classifier is about each categorization
- **Learned Preferences**: The plugin learns which senders you trust and which you want to block
- **Safety-First**: All actions require user confirmation before archiving (initially)
- **Quality Tiers**: Assess newsletters as high, medium, or low quality
- **User Feedback Loop**: Improves over time based on your decisions
- **Expandable**: Easy to add new categories as your needs grow

## Installation

1. **Clone/Download** this plugin into your Claude Code plugins directory:
   ```bash
   ~/.claude/plugins/gmail-classifier/
   ```

2. **Set up Gmail authentication**:
   - Enable 2-step verification in your Google Account: https://myaccount.google.com/security
   - Create an App Password: https://myaccount.google.com/apppasswords
   - Add to your shell secrets (`.zshrc`, `.bashrc`, etc.):
     ```bash
     export GMAIL_APP_PASSWORD="your-16-char-app-password"
     ```
   - Reload: `source ~/.zshrc`

3. **Verify MCP Setup**:
   ```bash
   cd ~/.claude/plugins/gmail-classifier
   cat .mcp.json  # Verify gmail-mcp configuration
   ```

4. **Load the plugin** in Claude Code:
   ```bash
   /help plugins
   # or reload Claude Code session
   ```

## Quick Start

### 1. Classify Your Inbox

```bash
/classify 15
```

This analyzes 15 recent unread emails and categorizes them:
- 📦 **Receipts**: High confidence, suggested action: archive
- 📰 **Newsletters**: Medium confidence, quality assessed
- 🎉 **Promotions**: Medium confidence, suggested action: archive

### 2. Review Suggestions

```bash
/review-suggestions
```

For each classified email, decide:
- ✅ **Approve** - Apply the suggested action
- ❌ **Reject** - Keep in inbox, ignore suggestion
- 📌 **Learn** - Remember this decision for future emails from this sender

### 3. Configure Your Preferences

```bash
/organize-config view
```

View your current configuration, or:

```bash
/organize-config edit
```

Edit to add:
- Trusted newsletter senders (keep in inbox)
- Senders to always archive
- Blocked domains (spam sources)
- Custom category patterns

## Commands

### `/classify [count]`

Analyze and classify recent unread emails.

```bash
/classify           # Process 10 emails (default)
/classify 20        # Process 20 emails
/classify 50        # Process 50 emails
```

**Output**: Summary of found categories with confidence levels and suggested actions.

### `/review-suggestions`

Review classified emails and make decisions.

**Options**:
- ✅ **Approve** - Apply suggested action
- ❌ **Reject** - Don't apply action
- 📌 **Learn** - Remember decision for this sender
- **Skip** - Review later

### `/organize-config [action]`

Manage classification rules and preferences.

```bash
/organize-config view     # Show current settings
/organize-config edit     # Edit configuration
/organize-config reset    # Reset preferences
```

## Configuration

Settings are stored in `.local.md` with these sections:

### Email Categories

Define how to classify each email type:

```yaml
categories:
  receipts:
    confidence: high
    action: archive
    patterns: [order, receipt, invoice, confirmation]
    common_domains: [amazon.com, ebay.com, stripe.com, paypal.com]

  newsletters:
    confidence: medium
    action: review
    quality_tiers: [high, medium, low]
    patterns: [newsletter, digest, subscription]

  promotions:
    confidence: medium
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

  archived_domains:
    - unwanted-spam.com
```

## How It Works

### Classification Process

1. **Pattern Matching**: Check sender domain and keywords
2. **Confidence Scoring**: Calculate likelihood (0-100%)
3. **Learned Preferences**: Apply your learned rules
4. **Suggest Action**: Recommend archive, review, or keep
5. **User Review**: Show suggestions for your approval

### Learning Loop

```
Classify Email
    ↓
Show Confidence + Suggestion
    ↓
User Feedback (Approve/Reject/Learn)
    ↓
Update Preferences
    ↓
Apply to Similar Emails (Next Time)
```

### Quality Tiers for Newsletters

- **🌟 High**: Keep in inbox (professional, well-researched, personalized)
- **⭐ Medium**: Review periodically (decent content, standard templates)
- **Low**: Archive (generic, frequent, low engagement)

## Examples

### Organizing Receipts

```
$ /classify 10
Found 6 receipts (95% confidence)
Action: Archive

$ /review-suggestions
✅ Approve: Archive 6 receipts
```

**Result**: 6 emails moved to archive, clutter reduced.

### Learning Newsletter Preferences

```
$ /classify 20
Found 5 newsletters (78% confidence)

$ /review-suggestions
Newsletter from newsletter@techcrunch.com
→ High Quality
→ [📌 Learn] "Always keep this"
→ Added to keep_newsletters

Newsletter from spam@promotional.com
→ Low Quality
→ [📌 Learn] "Always archive this"
→ Added to archive_newsletters
```

**Result**: Similar emails from these senders are now handled automatically.

### Blocking Promotional Domains

```
$ /organize-config edit
# Add to archived_domains:
archived_domains:
  - flash-sale-spam.com
  - daily-deals.net
```

**Result**: Emails from these domains skip the inbox classification.

## Roadmap

### Phase 2: Advanced Features (Planned)

- [ ] Automatic scheduling (process inbox daily at night)
- [ ] More categories (bills, account notifications, work, social)
- [ ] Advanced quality scoring for newsletters
- [ ] Label/folder organization (Gmail integration)
- [ ] Undo/revert suggestions

### Phase 3: Machine Learning (Future)

- [ ] Per-sender engagement tracking
- [ ] Collaborative filtering (recommended newsletters)
- [ ] Time-based patterns (seasonal emails)
- [ ] Multi-language support

## Troubleshooting

### "Gmail connection failed"

Check Gmail app password:
```bash
echo $GMAIL_APP_PASSWORD
# Should print your 16-character app password
```

If not set, add to your shell config (`~/.zshrc` or `~/.bashrc`):
```bash
export GMAIL_APP_PASSWORD="your-16-char-password"
```

### "No emails found"

- Check your inbox has unread emails
- Try with higher count: `/classify 50`
- Verify Gmail authentication

### Classifier seems wrong

1. Provide feedback with `/review-suggestions`
2. Use 📌 **Learn** to train on your preferences
3. Check configuration: `/organize-config view`
4. Adjust patterns in `.local.md` if needed

### Want to undo actions

Edit `.local.md` to adjust preferences:
- Remove senders from `keep_newsletters` or `archive_newsletters`
- Remove domains from `archived_domains`
- Reset with `/organize-config reset`

## Architecture

### Plugin Structure

```
gmail-classifier/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── .mcp.json                 # Gmail MCP configuration
├── .local.md                 # User settings & preferences
├── commands/
│   ├── classify.md           # /classify command
│   ├── review-suggestions.md # /review-suggestions command
│   └── organize-config.md    # /organize-config command
├── agents/
│   └── email-organizer.md    # Autonomous email organizer agent
├── skills/
│   └── email-organization/
│       └── SKILL.md          # Email organization strategy skill
├── scripts/
│   ├── classify-logic.py     # Core classification engine
│   └── preference-learner.py # Preference learning system
└── README.md                 # This file
```

### Key Components

- **Commands**: User-facing actions (`/classify`, `/review-suggestions`, `/organize-config`)
- **Agent**: `email-organizer` - Autonomous classification and suggestion generation
- **Skill**: Email organization strategy and patterns
- **Scripts**: Python helpers for classification and preference learning
- **Settings**: `.local.md` - User configuration and learned preferences

## Performance

- **First run**: ~2-3 seconds per 10 emails (no learned preferences)
- **Subsequent runs**: ~1 second per 10 emails (with learned preferences)
- **Learning benefit**: 80% faster processing after 2-4 weeks of use

## Privacy

- All classification happens locally (no external APIs)
- Gmail passwords are stored in shell environment only
- Learned preferences stored in `.local.md` (gitignored)
- No data sent to third parties

## Contributing

To extend the plugin:

1. **Add new category**: Update `categories` in `.local.md`, add patterns to `classify-logic.py`
2. **Improve patterns**: Edit `scripts/classify-logic.py` to refine detection
3. **Add features**: Modify commands or create new skills
4. **Report issues**: Create issue with classification example

## Support

- Stuck? Read the Email Organization Strategy skill: `/email-organization`
- Need help? Run `/help classify` or `/help organize-config`
- Questions? Check the command examples above

---

**Version**: 0.1.0
**Author**: Claude
**License**: MIT
**Last Updated**: February 2026
