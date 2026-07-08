from __future__ import annotations

import random
from dataclasses import dataclass, field

from .model import Announcement, Card, Rank, Suit, Team, TrumpChoice
from .rules import build_deck, card_points, compare_announcements, detect_announcements, determine_trick_winner, legal_cards, trick_points


@dataclass(frozen=True)
class GameOptions:
    target_score: int = 1000
    pique_double: bool = False

    @staticmethod
    def normal() -> "GameOptions":
        return GameOptions(target_score=1000, pique_double=False)

    @staticmethod
    def with_pique_double() -> "GameOptions":
        return GameOptions(target_score=1500, pique_double=True)


@dataclass(frozen=True)
class CompletedTrick:
    lead_player: int
    plays: tuple[tuple[int, Card], ...]
    winner: int
    points: int


@dataclass(frozen=True)
class PlayerView:
    player: int
    hand: tuple[Card, ...]
    current_trick: tuple[tuple[int, Card], ...]
    last_trick: CompletedTrick | None
    trump: Suit | None
    revealed_announcements: tuple[Announcement, ...]
    revealed_stoeck: tuple[int, ...]
    score: tuple[int, int]
    dealer_starter: int | None
    chooser: int | None


@dataclass
class DealState:
    hands: dict[int, list[Card]]
    dealer_starter: int
    trump: Suit | None = None
    chooser: int | None = None
    chibred_by: int | None = None
    current_leader: int | None = None
    current_trick: list[tuple[int, Card]] = field(default_factory=list)
    completed_tricks: list[CompletedTrick] = field(default_factory=list)
    trick_points_by_team: dict[Team, int] = field(default_factory=lambda: {Team.TEAM_0_2: 0, Team.TEAM_1_3: 0})
    trick_wins_by_team: dict[Team, int] = field(default_factory=lambda: {Team.TEAM_0_2: 0, Team.TEAM_1_3: 0})
    revealed_players: set[int] = field(default_factory=set)
    revealed_announcements: list[Announcement] = field(default_factory=list)
    ordinary_announcement_points_by_team: dict[Team, int] = field(default_factory=lambda: {Team.TEAM_0_2: 0, Team.TEAM_1_3: 0})
    announcement_winning_team: Team | None = None
    stoeck_holders: set[int] = field(default_factory=set)
    revealed_stoeck: set[int] = field(default_factory=set)
    stoeck_points_by_team: dict[Team, int] = field(default_factory=lambda: {Team.TEAM_0_2: 0, Team.TEAM_1_3: 0})
    reveal_counter: int = 0
    finished: bool = False
    deal_points_by_team: dict[Team, int] = field(default_factory=lambda: {Team.TEAM_0_2: 0, Team.TEAM_1_3: 0})

    def choose_trump(self, player: int, choice: TrumpChoice) -> None:
        if self.trump is not None:
            raise ValueError("trump is already chosen")
        if self.chooser is None:
            self.chooser = self.dealer_starter
        if player != self.chooser:
            raise ValueError(f"player {player} cannot choose now; expected {self.chooser}")
        if choice.chibre:
            if self.chibred_by is not None:
                raise ValueError("re-chibrer is forbidden")
            self.chibred_by = player
            self.chooser = (player + 2) % 4
            return
        if choice.suit is None:
            raise ValueError("a non-chibre choice must include a trump suit")
        self.trump = choice.suit
        self.current_leader = self.dealer_starter
        self._index_stoeck_holders()

    def play_card(self, player: int, card: Card) -> None:
        if self.trump is None or self.current_leader is None:
            raise ValueError("trump must be chosen before playing")
        if self.finished:
            raise ValueError("deal is already finished")
        if not self.current_trick:
            expected = self.current_leader
        else:
            expected = (self.current_leader + len(self.current_trick)) % 4
        if player != expected:
            raise ValueError(f"player {player} cannot play now; expected {expected}")
        if card not in self.hands[player]:
            raise ValueError(f"player {player} does not hold {card}")
        current_cards = [played_card for _, played_card in self.current_trick]
        if card not in legal_cards(self.hands[player], current_cards, self.trump):
            raise ValueError(f"illegal card {card} for player {player}")

        if player not in self.revealed_players:
            self.revealed_players.add(player)
            self.reveal_counter += 1
            self.revealed_announcements.extend(detect_announcements(self.hands[player], player, self.reveal_counter))
            if len(self.revealed_players) == 4:
                self._score_ordinary_announcements()

        self.hands[player].remove(card)
        self.current_trick.append((player, card))
        self._reveal_stoeck_if_complete(player, card)
        if len(self.current_trick) == 4:
            self._finish_current_trick()

    def legal_cards_for(self, player: int) -> tuple[Card, ...]:
        if self.trump is None:
            raise ValueError("trump must be chosen before legal cards are available")
        return legal_cards(self.hands[player], [card for _, card in self.current_trick], self.trump)

    def view_for(self, player: int, score: tuple[int, int]) -> PlayerView:
        if player not in range(4):
            raise ValueError(f"player must be 0..3, got {player}")
        return PlayerView(
            player=player,
            hand=tuple(self.hands[player]),
            current_trick=tuple(self.current_trick),
            last_trick=self.completed_tricks[-1] if self.completed_tricks else None,
            trump=self.trump,
            revealed_announcements=tuple(self.revealed_announcements),
            revealed_stoeck=tuple(sorted(self.revealed_stoeck)),
            score=score,
            dealer_starter=self.dealer_starter,
            chooser=self.chooser,
        )

    def _finish_current_trick(self) -> None:
        assert self.trump is not None
        assert self.current_leader is not None
        cards = [card for _, card in self.current_trick]
        winner = determine_trick_winner(self.current_leader, cards, self.trump)
        is_last_trick = len(self.completed_tricks) == 8
        points = trick_points(cards, self.trump, is_last_trick=is_last_trick)
        team = Team.of_player(winner)
        self.trick_points_by_team[team] += points
        self.trick_wins_by_team[team] += 1
        self.completed_tricks.append(CompletedTrick(self.current_leader, tuple(self.current_trick), winner, points))
        self.current_trick = []
        self.current_leader = winner
        if is_last_trick:
            self._finish_deal()

    def _finish_deal(self) -> None:
        multiplier = 2 if self.trump == Suit.SPADES and self._pique_double_enabled else 1
        for team in Team:
            base = self.trick_points_by_team[team]
            if self.trick_wins_by_team[team] == 9:
                base += 100
            self.deal_points_by_team[team] = (
                base + self.ordinary_announcement_points_by_team[team] + self.stoeck_points_by_team[team]
            ) * multiplier
        self.finished = True

    @property
    def _pique_double_enabled(self) -> bool:
        # Injecté par GameState au calcul final; False pour les DealState créés directement.
        return getattr(self, "pique_double", False)

    def _score_ordinary_announcements(self) -> None:
        if not self.revealed_announcements:
            return
        assert self.trump is not None
        best = self.revealed_announcements[0]
        for announcement in self.revealed_announcements[1:]:
            if compare_announcements(announcement, best, self.trump) > 0:
                best = announcement
        winning_team = Team.of_player(best.player)
        self.announcement_winning_team = winning_team
        for announcement in self.revealed_announcements:
            if Team.of_player(announcement.player) == winning_team:
                self.ordinary_announcement_points_by_team[winning_team] += announcement.points

    def _index_stoeck_holders(self) -> None:
        assert self.trump is not None
        king = Card(self.trump, Rank.KING)
        queen = Card(self.trump, Rank.QUEEN)
        for player, hand in self.hands.items():
            if king in hand and queen in hand:
                self.stoeck_holders.add(player)

    def _reveal_stoeck_if_complete(self, player: int, card: Card) -> None:
        assert self.trump is not None
        if player not in self.stoeck_holders or player in self.revealed_stoeck:
            return
        if card not in (Card(self.trump, Rank.KING), Card(self.trump, Rank.QUEEN)):
            return
        remaining_other = Card(self.trump, Rank.QUEEN if card.rank == Rank.KING else Rank.KING)
        if remaining_other not in self.hands[player]:
            self.revealed_stoeck.add(player)
            self.stoeck_points_by_team[Team.of_player(player)] += 20


@dataclass
class GameState:
    options: GameOptions = field(default_factory=GameOptions.normal)
    score: dict[Team, int] = field(default_factory=lambda: {Team.TEAM_0_2: 0, Team.TEAM_1_3: 0})
    current_deal: DealState | None = None
    next_dealer_starter: int | None = None

    def start_deal(self, hands: dict[int, list[Card]] | None = None, seed: int | None = None) -> DealState:
        if hands is None:
            hands = deal_cards(seed)
        _validate_hands(hands)
        dealer = self.next_dealer_starter
        if dealer is None:
            dealer = holder_of(Card(Suit.DIAMONDS, Rank.SEVEN), hands)
        deal = DealState(hands={player: list(cards) for player, cards in hands.items()}, dealer_starter=dealer, chooser=dealer)
        setattr(deal, "pique_double", self.options.pique_double)
        self.current_deal = deal
        return deal

    def finish_deal_if_done(self) -> None:
        if self.current_deal is None or not self.current_deal.finished:
            return
        for team in Team:
            self.score[team] += self.current_deal.deal_points_by_team[team]
        self.next_dealer_starter = (self.current_deal.dealer_starter - 1) % 4
        self.current_deal = None

    def is_game_over(self) -> bool:
        return any(points >= self.options.target_score for points in self.score.values())

    def score_tuple(self) -> tuple[int, int]:
        return (self.score[Team.TEAM_0_2], self.score[Team.TEAM_1_3])


def deal_cards(seed: int | None = None) -> dict[int, list[Card]]:
    deck = list(build_deck())
    random.Random(seed).shuffle(deck)
    return {player: deck[player * 9 : (player + 1) * 9] for player in range(4)}


def holder_of(card: Card, hands: dict[int, list[Card]]) -> int:
    for player, hand in hands.items():
        if card in hand:
            return player
    raise ValueError(f"no player holds {card}")


def _validate_hands(hands: dict[int, list[Card]]) -> None:
    if set(hands) != {0, 1, 2, 3}:
        raise ValueError("hands must be provided for players 0, 1, 2 and 3")
    all_cards = [card for hand in hands.values() for card in hand]
    if len(all_cards) != 36 or any(len(hand) != 9 for hand in hands.values()):
        raise ValueError("each of the 4 players must have exactly 9 cards")
    if set(all_cards) != set(build_deck()):
        raise ValueError("hands must contain the 36 unique cards of the deck")
