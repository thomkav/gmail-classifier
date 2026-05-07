#!/usr/bin/env python3
"""
Preference Learner

Tracks user decisions and updates learned preferences over time.
Learns which senders to keep/archive and which domains to block.

Updates stored in:
- keep_newsletters: Newsletter senders to preserve in inbox
- archive_newsletters: Newsletter senders to auto-archive
- keep_senders: Trusted senders that bypass classification
- archived_domains: Spam/unwanted domains
"""

import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from enum import Enum


class UserDecision(Enum):
    """User's decision on a classification"""
    APPROVE = "approve"  # Accept the suggested action
    REJECT = "reject"  # Don't apply the suggested action
    KEEP = "keep"  # Keep in inbox, don't archive
    ARCHIVE = "archive"  # Move to archive
    BLOCK = "block"  # Block from inbox
    LEARN = "learn"  # Remember this decision for future


@dataclass
class UserFeedback:
    """Feedback on an email classification"""
    sender: str
    category: str
    decision: UserDecision
    note: Optional[str] = None


class PreferenceLearner:
    """Learn from user feedback and update preferences"""

    def __init__(self, preferences: dict):
        """
        Initialize with current preferences

        Args:
            preferences: Current learned_preferences dict
        """
        self.preferences = preferences
        self._ensure_keys()

    def _ensure_keys(self):
        """Ensure all required keys exist"""
        defaults = {
            "keep_newsletters": [],
            "archive_newsletters": [],
            "keep_senders": [],
            "archived_domains": [],
        }
        for key, default_value in defaults.items():
            if key not in self.preferences:
                self.preferences[key] = default_value

    def process_feedback(self, feedback: UserFeedback) -> bool:
        """
        Process user feedback and update preferences

        Args:
            feedback: UserFeedback object

        Returns:
            True if preferences were updated
        """
        updated = False

        if feedback.decision == UserDecision.LEARN:
            # User approves and wants to learn
            if feedback.category == "newsletter":
                if feedback.sender not in self.preferences["keep_newsletters"]:
                    self.preferences["keep_newsletters"].append(feedback.sender)
                    updated = True
            elif feedback.category == "promotion":
                if feedback.sender not in self.preferences["archived_domains"]:
                    # Extract domain from email
                    domain = self._extract_domain(feedback.sender)
                    if domain and domain not in self.preferences["archived_domains"]:
                        self.preferences["archived_domains"].append(domain)
                        updated = True

        elif feedback.decision == UserDecision.KEEP:
            # User wants to keep emails from this sender
            if feedback.sender not in self.preferences["keep_senders"]:
                self.preferences["keep_senders"].append(feedback.sender)
                updated = True

        elif feedback.decision == UserDecision.ARCHIVE:
            # User wants to archive from this sender
            if feedback.category == "newsletter":
                if feedback.sender not in self.preferences["archive_newsletters"]:
                    self.preferences["archive_newsletters"].append(feedback.sender)
                    updated = True
            elif feedback.category == "promotion":
                domain = self._extract_domain(feedback.sender)
                if domain and domain not in self.preferences["archived_domains"]:
                    self.preferences["archived_domains"].append(domain)
                    updated = True

        elif feedback.decision == UserDecision.BLOCK:
            # User wants to block domain
            domain = self._extract_domain(feedback.sender)
            if domain and domain not in self.preferences["archived_domains"]:
                self.preferences["archived_domains"].append(domain)
                updated = True

        return updated

    def process_batch_feedback(self, feedbacks: List[UserFeedback]) -> Dict[str, int]:
        """
        Process multiple feedbacks

        Args:
            feedbacks: List of UserFeedback objects

        Returns:
            Summary of updates made
        """
        summary = {
            "total_processed": len(feedbacks),
            "keep_newsletters_added": 0,
            "archive_newsletters_added": 0,
            "keep_senders_added": 0,
            "archived_domains_added": 0,
        }

        for feedback in feedbacks:
            initial_keep_newsletters = len(self.preferences["keep_newsletters"])
            initial_archive_newsletters = len(self.preferences["archive_newsletters"])
            initial_keep_senders = len(self.preferences["keep_senders"])
            initial_archived_domains = len(self.preferences["archived_domains"])

            self.process_feedback(feedback)

            # Count what changed
            if len(self.preferences["keep_newsletters"]) > initial_keep_newsletters:
                summary["keep_newsletters_added"] += 1
            if len(self.preferences["archive_newsletters"]) > initial_archive_newsletters:
                summary["archive_newsletters_added"] += 1
            if len(self.preferences["keep_senders"]) > initial_keep_senders:
                summary["keep_senders_added"] += 1
            if len(self.preferences["archived_domains"]) > initial_archived_domains:
                summary["archived_domains_added"] += 1

        return summary

    @staticmethod
    def _extract_domain(email_or_sender: str) -> Optional[str]:
        """
        Extract domain from email address

        Args:
            email_or_sender: Email address or sender string

        Returns:
            Domain name or None
        """
        if "@" in email_or_sender:
            return email_or_sender.split("@")[1].lower()
        # Assume it's already a domain
        return email_or_sender.lower() if email_or_sender else None

    def add_keep_newsletter(self, sender: str) -> bool:
        """Add newsletter sender to keep list"""
        if sender not in self.preferences["keep_newsletters"]:
            self.preferences["keep_newsletters"].append(sender)
            return True
        return False

    def add_archive_newsletter(self, sender: str) -> bool:
        """Add newsletter sender to archive list"""
        if sender not in self.preferences["archive_newsletters"]:
            self.preferences["archive_newsletters"].append(sender)
            return True
        return False

    def add_keep_sender(self, sender: str) -> bool:
        """Add trusted sender"""
        if sender not in self.preferences["keep_senders"]:
            self.preferences["keep_senders"].append(sender)
            return True
        return False

    def add_blocked_domain(self, domain: str) -> bool:
        """Add blocked domain"""
        domain = domain.lower()
        if domain not in self.preferences["archived_domains"]:
            self.preferences["archived_domains"].append(domain)
            return True
        return False

    def remove_keep_newsletter(self, sender: str) -> bool:
        """Remove from keep list"""
        if sender in self.preferences["keep_newsletters"]:
            self.preferences["keep_newsletters"].remove(sender)
            return True
        return False

    def remove_archive_newsletter(self, sender: str) -> bool:
        """Remove from archive list"""
        if sender in self.preferences["archive_newsletters"]:
            self.preferences["archive_newsletters"].remove(sender)
            return True
        return False

    def remove_keep_sender(self, sender: str) -> bool:
        """Remove trusted sender"""
        if sender in self.preferences["keep_senders"]:
            self.preferences["keep_senders"].remove(sender)
            return True
        return False

    def remove_blocked_domain(self, domain: str) -> bool:
        """Remove blocked domain"""
        domain = domain.lower()
        if domain in self.preferences["archived_domains"]:
            self.preferences["archived_domains"].remove(domain)
            return True
        return False

    def get_preferences(self) -> dict:
        """Get current preferences"""
        return self.preferences

    def reset_category(self, category: str) -> bool:
        """
        Reset all preferences for a category

        Args:
            category: "newsletters", "senders", or "domains"

        Returns:
            True if reset was performed
        """
        if category == "newsletters":
            self.preferences["keep_newsletters"] = []
            self.preferences["archive_newsletters"] = []
            return True
        elif category == "senders":
            self.preferences["keep_senders"] = []
            return True
        elif category == "domains":
            self.preferences["archived_domains"] = []
            return True
        elif category == "all":
            self.preferences = {
                "keep_newsletters": [],
                "archive_newsletters": [],
                "keep_senders": [],
                "archived_domains": [],
            }
            return True
        return False

    def get_summary(self) -> dict:
        """Get summary of learned preferences"""
        return {
            "keep_newsletters": len(self.preferences["keep_newsletters"]),
            "archive_newsletters": len(self.preferences["archive_newsletters"]),
            "keep_senders": len(self.preferences["keep_senders"]),
            "archived_domains": len(self.preferences["archived_domains"]),
            "total_learned": sum(
                len(v) for v in self.preferences.values()
            ),
        }


def process_user_decision(
    sender: str,
    category: str,
    decision: str,
    preferences: dict
) -> Dict:
    """
    Process a single user decision

    Args:
        sender: Email sender address
        category: Email category (receipt, newsletter, promotion)
        decision: User's decision (approve, reject, keep, archive, block, learn)
        preferences: Current preferences dict

    Returns:
        Updated preferences and summary
    """
    learner = PreferenceLearner(preferences)

    try:
        user_decision = UserDecision(decision)
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid decision: {decision}",
            "preferences": preferences,
        }

    feedback = UserFeedback(
        sender=sender,
        category=category,
        decision=user_decision,
    )

    learner.process_feedback(feedback)

    return {
        "success": True,
        "preferences": learner.get_preferences(),
        "summary": learner.get_summary(),
    }


if __name__ == "__main__":
    # Example usage
    initial_prefs = {
        "keep_newsletters": [],
        "archive_newsletters": [],
        "keep_senders": [],
        "archived_domains": [],
    }

    learner = PreferenceLearner(initial_prefs)

    # Process some feedback
    feedbacks = [
        UserFeedback(
            sender="newsletter@techcrunch.com",
            category="newsletter",
            decision=UserDecision.LEARN,
        ),
        UserFeedback(
            sender="spam@promotional.com",
            category="newsletter",
            decision=UserDecision.ARCHIVE,
        ),
        UserFeedback(
            sender="deals@store.com",
            category="promotion",
            decision=UserDecision.BLOCK,
        ),
    ]

    summary = learner.process_batch_feedback(feedbacks)
    print("Summary:", json.dumps(summary, indent=2))
    print("Preferences:", json.dumps(learner.get_preferences(), indent=2))
