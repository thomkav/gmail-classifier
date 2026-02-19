#!/usr/bin/env python3
"""
Email Classification Logic

Core classification engine for categorizing emails into:
- Receipts: Orders, confirmations, invoices
- Newsletters: Subscriptions, digests, updates
- Promotions: Sales, offers, discounts

Supports:
- Pattern matching (keywords, domains)
- Confidence scoring
- Learned preference application
- Quality tier assessment for newsletters
"""

import json
import re
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from enum import Enum


class Category(Enum):
    """Email categories"""
    RECEIPT = "receipt"
    NEWSLETTER = "newsletter"
    PROMOTION = "promotion"
    NOTIFICATION = "notification"
    UNKNOWN = "unknown"


class NewsletterTier(Enum):
    """Newsletter quality tiers"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ClassificationResult:
    """Result of email classification"""
    category: Category
    confidence: float  # 0-100
    tier: Optional[NewsletterTier] = None
    reasoning: str = ""
    suggested_action: str = "review"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "category": self.category.value,
            "confidence": self.confidence,
            "tier": self.tier.value if self.tier else None,
            "reasoning": self.reasoning,
            "suggested_action": self.suggested_action,
        }


class EmailClassifier:
    """Classify emails into categories with confidence scoring"""

    def __init__(self, config: dict):
        """
        Initialize classifier with configuration

        Args:
            config: Configuration dict with categories, patterns, learned preferences
        """
        self.config = config
        self.categories_config = config.get("categories", {})
        self.learned_prefs = config.get("learned_preferences", {})

    def classify(self, email: dict) -> ClassificationResult:
        """
        Classify an email

        Args:
            email: Email data with sender, subject, preview

        Returns:
            ClassificationResult with category, confidence, suggested action
        """
        sender = email.get("sender", "").lower()
        subject = email.get("subject", "").lower()
        preview = email.get("preview", "").lower()
        # Include sender in body for pattern matching (catches newsletter@, marketing@, etc.)
        email_body = f"{sender} {subject} {preview}"

        # Check learned preferences first
        learned_result = self._check_learned_preferences(sender, email_body)
        if learned_result:
            return learned_result

        # Check if this looks like a personal/conversational email (skip classification)
        personal_result = self._classify_personal(sender, subject, preview)
        if personal_result:
            return personal_result

        # Check notification (security alerts, TOS, account notices)
        notification_result = self._classify_notification(sender, email_body)
        if notification_result:
            return notification_result

        # Try each category in order of confidence
        results = []

        # Check receipt
        receipt_result = self._classify_receipt(sender, email_body)
        if receipt_result:
            results.append(receipt_result)

        # Check newsletter
        newsletter_result = self._classify_newsletter(sender, email_body)
        if newsletter_result:
            results.append(newsletter_result)

        # Check promotion
        promotion_result = self._classify_promotion(sender, email_body)
        if promotion_result:
            results.append(promotion_result)

        # Return highest confidence
        if results:
            return max(results, key=lambda r: r.confidence)

        # Unknown category
        return ClassificationResult(
            category=Category.UNKNOWN,
            confidence=0,
            reasoning="No patterns matched",
            suggested_action="review",
        )

    def _check_learned_preferences(self, sender: str, email_body: str) -> Optional[ClassificationResult]:
        """Check learned preferences before pattern matching"""

        # Check keep_senders (always keep in inbox)
        keep_senders = self.learned_prefs.get("keep_senders", [])
        for keep_sender in keep_senders:
            if keep_sender.lower() in sender or sender.endswith(keep_sender.lower()):
                return ClassificationResult(
                    category=Category.UNKNOWN,
                    confidence=100,
                    reasoning=f"Sender '{keep_sender}' in trusted list",
                    suggested_action="keep",
                )

        # Check keep_newsletters
        keep_newsletters = self.learned_prefs.get("keep_newsletters", [])
        for newsletter_sender in keep_newsletters:
            if newsletter_sender.lower() in sender or sender.endswith(newsletter_sender.lower()):
                return ClassificationResult(
                    category=Category.NEWSLETTER,
                    confidence=100,
                    tier=NewsletterTier.HIGH,
                    reasoning=f"Newsletter sender '{newsletter_sender}' in keep list",
                    suggested_action="keep",
                )

        # Check archive_newsletters
        archive_newsletters = self.learned_prefs.get("archive_newsletters", [])
        for newsletter_sender in archive_newsletters:
            if newsletter_sender.lower() in sender or sender.endswith(newsletter_sender.lower()):
                return ClassificationResult(
                    category=Category.NEWSLETTER,
                    confidence=100,
                    tier=NewsletterTier.LOW,
                    reasoning=f"Newsletter sender '{newsletter_sender}' in archive list",
                    suggested_action="archive",
                )

        # Check blocked_domains
        blocked_domains = self.learned_prefs.get("blocked_domains", [])
        for domain in blocked_domains:
            if domain.lower() in sender:
                return ClassificationResult(
                    category=Category.PROMOTION,
                    confidence=100,
                    reasoning=f"Domain '{domain}' in blocked list",
                    suggested_action="archive",
                )

        return None

    def _classify_personal(self, sender: str, subject: str, preview: str) -> Optional[ClassificationResult]:
        """Detect personal/conversational emails that should stay in inbox"""
        score = 0
        matches = []

        # Reply threads are personal conversations
        if subject.startswith("re:"):
            score += 50
            matches.append("Reply thread")

        # Forward threads
        if subject.startswith("fwd:") or subject.startswith("fw:"):
            score += 30
            matches.append("Forwarded message")

        # Personal name-style sender (not from noreply, marketing, newsletter, etc.)
        automated_prefixes = [
            "noreply@", "no-reply@", "newsletter@", "marketing@",
            "notifications@", "alerts@", "info@", "support@",
            "updates@", "digest@", "mailer@", "bounce@",
            "campaign@", "promo@", "deals@", "sales@",
        ]
        is_automated = any(prefix in sender for prefix in automated_prefixes)
        if not is_automated and "@" in sender:
            # Check for personal sender patterns (name-like local parts)
            local = sender.split("<")[-1].split("@")[0] if "<" in sender else sender.split("@")[0]
            if local and not any(c.isdigit() for c in local[:3]) and len(local) > 2:
                score += 15
                matches.append("Personal sender")

        # Short, conversational preview
        if preview and len(preview) < 100 and not any(x in preview for x in ["unsubscribe", "click here", "view in browser"]):
            score += 10
            matches.append("Conversational content")

        if score >= 50:
            return ClassificationResult(
                category=Category.UNKNOWN,
                confidence=score,
                reasoning="; ".join(matches),
                suggested_action="keep",
            )

        return None

    def _classify_notification(self, sender: str, email_body: str) -> Optional[ClassificationResult]:
        """Classify as notification (security alerts, TOS updates, account notices)"""
        score = 0
        matches = []

        # Known notification sender domains
        notification_domains = [
            "accounts.google.com", "apple.com", "github.com", "microsoft.com",
            "id.apple.com", "appleid.apple.com", "linkedin.com",
        ]
        for domain in notification_domains:
            if domain in sender:
                score += 30
                matches.append(f"Notification domain: {domain}")
                break

        # Notification sender prefixes
        notification_prefixes = [
            "alerts@", "security@", "notifications@", "no-reply@accounts.",
            "account-security@", "noreply@github.com",
        ]
        for prefix in notification_prefixes:
            if prefix in sender:
                score += 25
                matches.append(f"Notification sender: {prefix}")
                break

        # Subject patterns
        notification_subjects = [
            "security alert", "action required", "terms and conditions",
            "verify", "sign-in", "sign in", "login attempt",
            "password", "two-factor", "2fa", "unusual activity",
            "account update", "privacy policy", "terms of service",
            "terms of use", "tos update", "policy update",
        ]
        for pattern in notification_subjects:
            if pattern in email_body:
                score += 20
                matches.append(f"Notification subject: {pattern}")
                break

        if score >= 50:
            return ClassificationResult(
                category=Category.NOTIFICATION,
                confidence=min(score, 100),
                reasoning="; ".join(matches) if matches else "Notification patterns detected",
                suggested_action="keep",
            )

        return None

    def _classify_receipt(self, sender: str, email_body: str) -> Optional[ClassificationResult]:
        """Classify as receipt"""
        config = self.categories_config.get("receipts", {})
        patterns = config.get("patterns", [])
        common_domains = config.get("common_domains", [])

        score = 0
        matches = []

        # Domain check
        for domain in common_domains:
            if domain.lower() in sender:
                score += 40
                matches.append(f"Known receipt domain: {domain}")
                break

        # Pattern check
        for pattern in patterns:
            if re.search(rf"\b{pattern}\b", email_body):
                score += 15
                matches.append(f"Pattern matched: {pattern}")

        # Content clues
        if any(x in email_body for x in ["order #", "tracking", "receipt #", "invoice #"]):
            score += 20
            matches.append("Receipt indicators found")

        if score >= 50:
            return ClassificationResult(
                category=Category.RECEIPT,
                confidence=min(score, 100),
                reasoning="; ".join(matches) if matches else "Receipt patterns detected",
                suggested_action="archive",
            )

        return None

    def _classify_newsletter(self, sender: str, email_body: str) -> Optional[ClassificationResult]:
        """Classify as newsletter"""
        config = self.categories_config.get("newsletters", {})
        patterns = config.get("patterns", [])

        score = 0
        matches = []

        # Pattern check (keyword in subject/body/sender)
        for pattern in patterns:
            if re.search(rf"\b{pattern}\b", email_body):
                score += 20
                matches.append(f"Pattern matched: {pattern}")

        # Sender address patterns (newsletter@, noreply@ with bulk content, etc.)
        newsletter_sender_patterns = ["newsletter@", "digest@", "updates@", "news@"]
        for pat in newsletter_sender_patterns:
            if pat in sender:
                score += 25
                matches.append(f"Newsletter sender: {pat}")
                break

        # Sender domain contains "newsletter" or "update"
        if any(x in sender for x in ["newsletter.", "update.", "campaign.", "email."]):
            score += 20
            matches.append("Newsletter-style sender domain")

        # Bulk sender indicators (noreply with non-personal content)
        if "noreply@" in sender or "no-reply@" in sender:
            score += 10
            matches.append("Automated sender (noreply)")

        # Known newsletter/content platforms
        newsletter_platforms = ["substack.com", "patreon.com", "mailchimp.com", "constantcontact.com",
                                "campaignmonitor.com", "buttondown.email", "revue.email", "beehiiv.com"]
        for platform in newsletter_platforms:
            if platform in sender:
                score += 25
                matches.append(f"Newsletter platform: {platform}")
                break

        # Newsletter content patterns
        content_patterns = [
            "icymi", "roundup", "recap", "top stories", "this week",
            "curated", "in case you missed", "weekly picks", "editor's picks",
        ]
        for pattern in content_patterns:
            if pattern in email_body:
                score += 20
                matches.append(f"Newsletter content: {pattern}")
                break

        # Unsubscribe links
        if "unsubscribe" in email_body:
            score += 15
            matches.append("Unsubscribe link present")

        # Assess quality tier
        tier = None
        if score >= 50:
            tier = self._assess_newsletter_quality(sender, email_body)

        if score >= 50:
            action = "review"
            if tier == NewsletterTier.HIGH:
                action = "keep"
            elif tier == NewsletterTier.LOW:
                action = "archive"

            return ClassificationResult(
                category=Category.NEWSLETTER,
                confidence=min(score, 100),
                tier=tier,
                reasoning="; ".join(matches) if matches else "Newsletter patterns detected",
                suggested_action=action,
            )

        return None

    def _classify_promotion(self, sender: str, email_body: str) -> Optional[ClassificationResult]:
        """Classify as promotion"""
        config = self.categories_config.get("promotions", {})
        patterns = config.get("patterns", [])

        score = 0
        matches = []

        # Pattern check
        for pattern in patterns:
            if re.search(rf"\b{pattern}\b", email_body):
                score += 15
                matches.append(f"Pattern matched: {pattern}")

        # Promotional clues
        urgency_words = [
            "limited time", "today only", "while supplies last", "hurry", "exclusive",
            "last call", "final call", "ending soon", "closing soon", "don't miss",
            "act now", "expires", "deadline",
        ]
        for word in urgency_words:
            if word in email_body:
                score += 10
                matches.append(f"Urgency word: {word}")
                break

        # Event/marketing patterns (multiple matches stack — strong promotional signal)
        event_patterns = [
            "workshop", "webinar", "training", "class", "session",
            "register", "sign up", "attend", "rsvp", "join us",
            "live event", "virtual event", "masterclass", "summit",
        ]
        for pattern in event_patterns:
            if pattern in email_body:
                score += 15
                matches.append(f"Event/marketing: {pattern}")

        # Sender patterns
        if any(x in sender for x in ["marketing@", "sales@", "deals@", "promo@"]):
            score += 20
            matches.append("Promotional sender format")

        # Event/ticket platforms
        event_platforms = ["eventbrite.com", "ticketmaster.com", "cascadetickets.com",
                          "stubhub.com", "axs.com", "dice.fm", "seetickets.com"]
        for platform in event_platforms:
            if platform in sender:
                score += 20
                matches.append(f"Event/ticket platform: {platform}")
                break

        # Campaign senders
        if "campaign." in sender or "m." in sender.split("@")[-1][:2]:
            score += 10
            matches.append("Campaign-style sender")

        # ALL CAPS or multiple exclamation marks
        subject_words = email_body.split()
        caps_count = sum(1 for word in subject_words if word.isupper() and len(word) > 2)
        if caps_count > 0:
            score += 5
            matches.append(f"Capitalized words: {caps_count}")

        if score >= 40:
            return ClassificationResult(
                category=Category.PROMOTION,
                confidence=min(score, 100),
                reasoning="; ".join(matches) if matches else "Promotional patterns detected",
                suggested_action="archive",
            )

        return None

    def _assess_newsletter_quality(self, sender: str, email_body: str) -> NewsletterTier:
        """Assess newsletter quality tier"""

        quality_score = 0

        # Credibility indicators
        if "@" in sender and not any(x in sender for x in ["noreply", "bounce"]):
            quality_score += 10

        # Content depth
        preview_length = len(email_body)
        if preview_length > 500:
            quality_score += 15
            tier_signal = "Medium"
        elif preview_length > 200:
            quality_score += 10
            tier_signal = "Medium"
        else:
            quality_score -= 5

        # Personalization clues
        if "curated" in email_body or "for you" in email_body:
            quality_score += 10

        # Frequency indicators (inferred from language)
        if "weekly" in email_body or "monthly" in email_body:
            quality_score += 5
        elif "daily" in email_body or "every day" in email_body:
            quality_score -= 5

        if quality_score >= 15:
            return NewsletterTier.HIGH
        elif quality_score >= 5:
            return NewsletterTier.MEDIUM
        else:
            return NewsletterTier.LOW


def classify_email(email: dict, config: dict) -> dict:
    """
    Classify a single email

    Args:
        email: Email data {sender, subject, preview}
        config: Configuration with categories and preferences

    Returns:
        Classification result dict
    """
    classifier = EmailClassifier(config)
    result = classifier.classify(email)
    return result.to_dict()


def classify_batch(emails: List[dict], config: dict) -> List[dict]:
    """
    Classify multiple emails

    Args:
        emails: List of email data
        config: Configuration with categories and preferences

    Returns:
        List of classification results
    """
    classifier = EmailClassifier(config)
    return [classifier.classify(email).to_dict() for email in emails]


if __name__ == "__main__":
    # Example usage
    example_config = {
        "categories": {
            "receipts": {
                "patterns": ["order", "receipt", "invoice", "confirmation"],
                "common_domains": ["amazon.com", "ebay.com", "stripe.com"],
            },
            "newsletters": {
                "patterns": ["newsletter", "digest", "subscription"],
            },
            "promotions": {
                "patterns": ["sale", "discount", "offer", "limited time"],
            },
        },
        "learned_preferences": {
            "keep_newsletters": [],
            "archive_newsletters": [],
            "keep_senders": [],
            "blocked_domains": [],
        },
    }

    example_email = {
        "sender": "order@amazon.com",
        "subject": "Order Confirmation - Your purchase #123456",
        "preview": "Thank you for your order. Order number: 123456. Total: $49.99",
    }

    result = classify_email(example_email, example_config)
    print(json.dumps(result, indent=2))
