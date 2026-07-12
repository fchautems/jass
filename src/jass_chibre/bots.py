from __future__ import annotations

from collections.abc import Sequence

from .engine import DealState
from .model import Card, Suit, TrumpChoice
from .rules import card_points, card_strength


def choose_first_trump(deal: DealState, preferred_order: Sequence[Suit] | None = None) -> TrumpChoice:
    """Choisit un atout simple pour un bot.

    Le bot additionne les points de sa main par couleur si cette couleur devenait
    atout, puis choisit la meilleure couleur. C'est volontairement naïf: le but
    est de tester le moteur, pas de produire une IA forte.
    """
    if deal.chooser is None:
        raise ValueError("deal has no active chooser")
    order = tuple(preferred_order or (Suit.HEARTS, Suit.DIAMONDS, Suit.SPADES, Suit.CLUBS))
    hand = deal.hands[deal.chooser]
    best_suit = max(order, key=lambda suit: (_trump_potential(hand, suit), -order.index(suit)))
    return TrumpChoice.direct(best_suit)


def choose_first_legal_card(deal: DealState, player: int) -> Card:
    """Retourne une carte légale déterministe pour un bot de test.

    Stratégie: jouer la plus petite carte légale en points, puis en force. Cela
    permet de faire avancer une partie de manière prévisible.
    """
    if deal.trump is None:
        raise ValueError("trump must be chosen before a bot can play")
    legal = deal.legal_cards_for(player)
    if not legal:
        raise ValueError(f"player {player} has no legal cards")
    return min(legal, key=lambda card: (card_points(card, deal.trump), card_strength(card, deal.trump), card.suit.value, card.rank.value))


def play_bot_turn(deal: DealState) -> tuple[int, Card]:
    """Joue le tour du joueur courant avec le bot naïf et retourne le coup joué."""
    if deal.current_leader is None:
        raise ValueError("trump must be chosen before playing")
    player = deal.current_leader if not deal.current_trick else (deal.current_leader - len(deal.current_trick)) % 4
    card = choose_first_legal_card(deal, player)
    deal.play_card(player, card)
    return player, card


def _trump_potential(hand: list[Card], trump: Suit) -> int:
    return sum(card_points(card, trump) for card in hand) + sum(3 for card in hand if card.suit == trump)
