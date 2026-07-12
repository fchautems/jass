from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Suit(str, Enum):
    HEARTS = "coeur"
    DIAMONDS = "carreau"
    SPADES = "pique"
    CLUBS = "trefle"


class Rank(str, Enum):
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "valet"
    QUEEN = "dame"
    KING = "roi"
    ACE = "as"


@dataclass(frozen=True, order=True)
class Card:
    suit: Suit
    rank: Rank

    def __str__(self) -> str:
        return f"{self.rank.value} de {self.suit.value}"


class Team(int, Enum):
    TEAM_0_2 = 0
    TEAM_1_3 = 1

    @staticmethod
    def of_player(player: int) -> "Team":
        if player not in range(4):
            raise ValueError(f"player must be 0..3, got {player}")
        return Team.TEAM_0_2 if player % 2 == 0 else Team.TEAM_1_3


@dataclass(frozen=True)
class TrumpChoice:
    """Choix d'atout: couleur directe ou chibre vers le partenaire."""

    suit: Suit | None = None
    chibre: bool = False

    @staticmethod
    def direct(suit: Suit) -> "TrumpChoice":
        return TrumpChoice(suit=suit, chibre=False)

    @staticmethod
    def pass_to_partner() -> "TrumpChoice":
        return TrumpChoice(suit=None, chibre=True)


class AnnouncementKind(str, Enum):
    SEQUENCE = "suite"
    FOUR_OF_A_KIND = "carre"


@dataclass(frozen=True)
class Announcement:
    kind: AnnouncementKind
    player: int
    cards: tuple[Card, ...]
    points: int
    highest_rank: Rank
    suit: Suit | None = None
    reveal_order: int = 0

    @property
    def length(self) -> int:
        return len(self.cards)
