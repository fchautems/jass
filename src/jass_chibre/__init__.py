"""Moteur de règles pour le Jass suisse, variante Chibre romand."""

from .bots import choose_first_legal_card, choose_first_trump, play_bot_turn
from .engine import DealState, GameOptions, GameState, PlayerView
from .model import Announcement, AnnouncementKind, Card, Rank, Suit, Team, TrumpChoice
from .rules import (
    JACK_OF_TRUMP_BONUS_NAME,
    NELL_BONUS_NAME,
    build_deck,
    card_points,
    compare_announcements,
    detect_announcements,
    determine_trick_winner,
    legal_cards,
)

__all__ = [
    "Announcement",
    "AnnouncementKind",
    "choose_first_legal_card",
    "choose_first_trump",
    "Card",
    "DealState",
    "GameOptions",
    "GameState",
    "JACK_OF_TRUMP_BONUS_NAME",
    "NELL_BONUS_NAME",
    "PlayerView",
    "play_bot_turn",
    "Rank",
    "Suit",
    "Team",
    "TrumpChoice",
    "build_deck",
    "card_points",
    "compare_announcements",
    "detect_announcements",
    "determine_trick_winner",
    "legal_cards",
]
