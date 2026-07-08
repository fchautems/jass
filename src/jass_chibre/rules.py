from __future__ import annotations

from collections import defaultdict

from .model import Announcement, AnnouncementKind, Card, Rank, Suit

JACK_OF_TRUMP_BONUS_NAME = "bour"
NELL_BONUS_NAME = "nell"

RANKS: tuple[Rank, ...] = (
    Rank.SIX,
    Rank.SEVEN,
    Rank.EIGHT,
    Rank.NINE,
    Rank.TEN,
    Rank.JACK,
    Rank.QUEEN,
    Rank.KING,
    Rank.ACE,
)
SUITS: tuple[Suit, ...] = (Suit.HEARTS, Suit.DIAMONDS, Suit.SPADES, Suit.CLUBS)

TRUMP_STRENGTH: dict[Rank, int] = {
    Rank.SIX: 0,
    Rank.SEVEN: 1,
    Rank.EIGHT: 2,
    Rank.TEN: 3,
    Rank.QUEEN: 4,
    Rank.KING: 5,
    Rank.ACE: 6,
    Rank.NINE: 7,
    Rank.JACK: 8,
}
PLAIN_STRENGTH: dict[Rank, int] = {
    Rank.SIX: 0,
    Rank.SEVEN: 1,
    Rank.EIGHT: 2,
    Rank.NINE: 3,
    Rank.TEN: 4,
    Rank.JACK: 5,
    Rank.QUEEN: 6,
    Rank.KING: 7,
    Rank.ACE: 8,
}
ANNOUNCEMENT_HEIGHT: dict[Rank, int] = PLAIN_STRENGTH.copy()

TRUMP_POINTS: dict[Rank, int] = {
    Rank.JACK: 20,
    Rank.NINE: 14,
    Rank.ACE: 11,
    Rank.KING: 4,
    Rank.QUEEN: 3,
    Rank.TEN: 10,
    Rank.EIGHT: 0,
    Rank.SEVEN: 0,
    Rank.SIX: 0,
}
PLAIN_POINTS: dict[Rank, int] = {
    Rank.ACE: 11,
    Rank.TEN: 10,
    Rank.KING: 4,
    Rank.QUEEN: 3,
    Rank.JACK: 2,
    Rank.NINE: 0,
    Rank.EIGHT: 0,
    Rank.SEVEN: 0,
    Rank.SIX: 0,
}
FOUR_OF_A_KIND_POINTS: dict[Rank, int] = {
    Rank.TEN: 100,
    Rank.QUEEN: 100,
    Rank.KING: 100,
    Rank.ACE: 100,
    Rank.NINE: 150,
    Rank.JACK: 200,
}


def build_deck() -> tuple[Card, ...]:
    return tuple(Card(suit, rank) for suit in SUITS for rank in RANKS)


def card_points(card: Card, trump: Suit) -> int:
    return (TRUMP_POINTS if card.suit == trump else PLAIN_POINTS)[card.rank]


def card_strength(card: Card, trump: Suit) -> int:
    return (TRUMP_STRENGTH if card.suit == trump else PLAIN_STRENGTH)[card.rank]


def is_bour(card: Card, trump: Suit) -> bool:
    return card.suit == trump and card.rank == Rank.JACK


def trick_points(cards: list[Card] | tuple[Card, ...], trump: Suit, is_last_trick: bool = False) -> int:
    return sum(card_points(card, trump) for card in cards) + (5 if is_last_trick else 0)


def determine_trick_winner(lead_player: int, cards_in_order: list[Card] | tuple[Card, ...], trump: Suit) -> int:
    if not cards_in_order:
        raise ValueError("cannot determine a winner for an empty trick")
    lead_suit = cards_in_order[0].suit
    winning_offset = 0
    winning_card = cards_in_order[0]
    for offset, card in enumerate(cards_in_order[1:], start=1):
        if _beats(card, winning_card, lead_suit, trump):
            winning_offset = offset
            winning_card = card
    return (lead_player + winning_offset) % 4


def _beats(candidate: Card, current: Card, lead_suit: Suit, trump: Suit) -> bool:
    if candidate.suit == trump and current.suit != trump:
        return True
    if candidate.suit != trump and current.suit == trump:
        return False
    if candidate.suit == current.suit:
        return card_strength(candidate, trump) > card_strength(current, trump)
    if current.suit == lead_suit:
        return False
    return candidate.suit == lead_suit


def legal_cards(hand: list[Card] | tuple[Card, ...], current_trick: list[Card] | tuple[Card, ...], trump: Suit) -> tuple[Card, ...]:
    """Retourne les cartes légalement jouables.

    Interprétation explicite du bour: le valet d'atout n'est jamais imposé pour
    fournir/couper. Si c'est la seule carte de la couleur demandée, le joueur
    peut le garder et jouer une autre carte.
    """
    hand_tuple = tuple(hand)
    if not current_trick:
        return hand_tuple

    lead_suit = current_trick[0].suit
    non_bour_follow_cards = tuple(card for card in hand_tuple if card.suit == lead_suit and not is_bour(card, trump))
    if non_bour_follow_cards:
        return non_bour_follow_cards

    # Si la couleur demandée est l'atout, le bour seul ne force pas à fournir.
    if lead_suit == trump:
        return hand_tuple

    # Sans carte de la couleur demandée (hors bour), on peut se défausser ou couper,
    # sauf sous-coupe interdite.
    strongest_trump_in_trick = _strongest_trump(current_trick, trump)
    if strongest_trump_in_trick is None:
        return hand_tuple

    undertrumps = tuple(
        card
        for card in hand_tuple
        if card.suit == trump and card_strength(card, trump) < card_strength(strongest_trump_in_trick, trump)
    )
    if not undertrumps:
        return hand_tuple

    not_undertrumps = tuple(card for card in hand_tuple if card not in undertrumps)
    return undertrumps if not not_undertrumps else not_undertrumps


def _strongest_trump(cards: list[Card] | tuple[Card, ...], trump: Suit) -> Card | None:
    trumps = [card for card in cards if card.suit == trump]
    return max(trumps, key=lambda card: card_strength(card, trump), default=None)


def detect_announcements(hand: list[Card] | tuple[Card, ...], player: int, reveal_order: int = 0) -> tuple[Announcement, ...]:
    """Détecte toutes les annonces ordinaires valides d'une main.

    Les suites sont toutes les sous-suites contiguës de longueur >= 3 dans une
    même couleur; cela respecte la règle de réutilisation des cartes.
    """
    cards = tuple(hand)
    announcements: list[Announcement] = []
    by_suit: dict[Suit, list[Card]] = defaultdict(list)
    by_rank: dict[Rank, list[Card]] = defaultdict(list)
    for card in cards:
        by_suit[card.suit].append(card)
        by_rank[card.rank].append(card)

    for suit, suited_cards in by_suit.items():
        ranks_present = {card.rank: card for card in suited_cards}
        ordered = [rank for rank in RANKS if rank in ranks_present]
        start = 0
        while start < len(ordered):
            end = start
            while end + 1 < len(ordered) and RANKS.index(ordered[end + 1]) == RANKS.index(ordered[end]) + 1:
                end += 1
            run = ordered[start : end + 1]
            if len(run) >= 3:
                for i in range(len(run)):
                    for j in range(i + 2, len(run)):
                        seq_ranks = run[i : j + 1]
                        seq_cards = tuple(ranks_present[rank] for rank in seq_ranks)
                        points = 100 if len(seq_cards) >= 5 else 50 if len(seq_cards) == 4 else 20
                        announcements.append(
                            Announcement(
                                kind=AnnouncementKind.SEQUENCE,
                                player=player,
                                cards=seq_cards,
                                points=points,
                                highest_rank=seq_ranks[-1],
                                suit=suit,
                                reveal_order=reveal_order,
                            )
                        )
            start = end + 1

    for rank, rank_cards in by_rank.items():
        if len(rank_cards) == 4 and rank in FOUR_OF_A_KIND_POINTS:
            announcements.append(
                Announcement(
                    kind=AnnouncementKind.FOUR_OF_A_KIND,
                    player=player,
                    cards=tuple(sorted(rank_cards)),
                    points=FOUR_OF_A_KIND_POINTS[rank],
                    highest_rank=rank,
                    reveal_order=reveal_order,
                )
            )
    return tuple(announcements)


def compare_announcements(left: Announcement, right: Announcement, trump: Suit) -> int:
    """Compare deux annonces. Retourne 1 si left gagne, -1 si right gagne, 0 si strictement égales."""
    left_key = _announcement_key(left, trump)
    right_key = _announcement_key(right, trump)
    return (left_key > right_key) - (left_key < right_key)


def _announcement_key(announcement: Announcement, trump: Suit) -> tuple[int, int, int, int, int]:
    return (
        announcement.points,
        announcement.length,
        ANNOUNCEMENT_HEIGHT[announcement.highest_rank],
        1 if announcement.suit == trump else 0,
        -announcement.reveal_order,
    )
