import pytest

from jass_chibre.engine import DealState, GameOptions, GameState, deal_cards
from jass_chibre.model import AnnouncementKind, Card, Rank, Suit, Team, TrumpChoice
from jass_chibre.rules import card_points, detect_announcements, determine_trick_winner, legal_cards


def c(suit, rank):
    return Card(suit, rank)


def test_deck_deal_and_initial_starter_holder_of_seven_diamonds():
    hands = deal_cards(seed=12)
    game = GameState()
    deal = game.start_deal(hands)

    holder = next(player for player, hand in hands.items() if c(Suit.DIAMONDS, Rank.SEVEN) in hand)
    assert deal.dealer_starter == holder
    assert deal.chooser == holder
    assert all(len(hand) == 9 for hand in hands.values())


def test_chibre_transfers_choice_to_partner_without_changing_first_leader():
    deal = DealState(
        hands={0: [], 1: [], 2: [], 3: []},
        dealer_starter=1,
        chooser=1,
    )

    deal.choose_trump(1, TrumpChoice.pass_to_partner())
    assert deal.chooser == 3
    assert deal.current_leader is None

    with pytest.raises(ValueError, match="re-chibrer"):
        deal.choose_trump(3, TrumpChoice.pass_to_partner())

    deal.choose_trump(3, TrumpChoice.direct(Suit.CLUBS))
    assert deal.trump == Suit.CLUBS
    assert deal.current_leader == 1


def test_trump_order_points_and_winner():
    trump = Suit.HEARTS
    assert card_points(c(Suit.HEARTS, Rank.JACK), trump) == 20
    assert card_points(c(Suit.HEARTS, Rank.NINE), trump) == 14
    assert card_points(c(Suit.CLUBS, Rank.JACK), trump) == 2

    winner = determine_trick_winner(
        0,
        [
            c(Suit.CLUBS, Rank.ACE),
            c(Suit.CLUBS, Rank.KING),
            c(Suit.HEARTS, Rank.NINE),
            c(Suit.HEARTS, Rank.JACK),
        ],
        trump,
    )
    assert winner == 3


def test_follow_suit_is_required_but_bour_is_never_forced():
    hand = [c(Suit.CLUBS, Rank.SIX), c(Suit.SPADES, Rank.ACE), c(Suit.HEARTS, Rank.JACK)]
    trick = [c(Suit.CLUBS, Rank.ACE)]
    assert legal_cards(hand, trick, Suit.HEARTS) == (c(Suit.CLUBS, Rank.SIX),)

    hand_with_only_bour_as_trump = [c(Suit.HEARTS, Rank.JACK), c(Suit.SPADES, Rank.ACE)]
    trump_led = [c(Suit.HEARTS, Rank.ACE)]
    assert set(legal_cards(hand_with_only_bour_as_trump, trump_led, Suit.HEARTS)) == set(hand_with_only_bour_as_trump)


def test_undercut_is_forbidden_unless_only_possible_choice():
    trump = Suit.HEARTS
    trick = [c(Suit.CLUBS, Rank.ACE), c(Suit.HEARTS, Rank.KING)]
    hand = [c(Suit.HEARTS, Rank.SIX), c(Suit.SPADES, Rank.ACE)]
    assert legal_cards(hand, trick, trump) == (c(Suit.SPADES, Rank.ACE),)

    only_undertrumps = [c(Suit.HEARTS, Rank.SIX), c(Suit.HEARTS, Rank.SEVEN)]
    assert set(legal_cards(only_undertrumps, trick, trump)) == set(only_undertrumps)


def test_detects_reusable_sequences_and_four_of_a_kind():
    hand = [
        c(Suit.CLUBS, Rank.SIX),
        c(Suit.CLUBS, Rank.SEVEN),
        c(Suit.CLUBS, Rank.EIGHT),
        c(Suit.CLUBS, Rank.NINE),
        c(Suit.CLUBS, Rank.TEN),
        c(Suit.HEARTS, Rank.NINE),
        c(Suit.DIAMONDS, Rank.NINE),
        c(Suit.SPADES, Rank.NINE),
        c(Suit.HEARTS, Rank.ACE),
    ]

    announcements = detect_announcements(hand, player=0, reveal_order=1)
    sequence_points = sorted(a.points for a in announcements if a.kind == AnnouncementKind.SEQUENCE)
    square = [a for a in announcements if a.kind == AnnouncementKind.FOUR_OF_A_KIND]

    assert sequence_points == [20, 20, 20, 50, 50, 100]
    assert len(square) == 1
    assert square[0].points == 150


def test_announcements_are_revealed_on_first_play_and_only_winning_team_scores():
    deal = DealState(
        hands={
            0: [c(Suit.CLUBS, Rank.SIX), c(Suit.CLUBS, Rank.SEVEN), c(Suit.CLUBS, Rank.EIGHT)],
            1: [c(Suit.DIAMONDS, Rank.ACE)],
            2: [c(Suit.HEARTS, Rank.SIX)],
            3: [c(Suit.SPADES, Rank.SIX), c(Suit.SPADES, Rank.SEVEN), c(Suit.SPADES, Rank.EIGHT), c(Suit.SPADES, Rank.NINE)],
        },
        dealer_starter=0,
        chooser=0,
    )
    deal.choose_trump(0, TrumpChoice.direct(Suit.HEARTS))

    deal.play_card(0, c(Suit.CLUBS, Rank.SIX))
    assert len(deal.revealed_announcements) == 1
    assert deal.ordinary_announcement_points_by_team[Team.TEAM_0_2] == 0

    deal.play_card(1, c(Suit.DIAMONDS, Rank.ACE))
    deal.play_card(2, c(Suit.HEARTS, Rank.SIX))
    deal.play_card(3, c(Suit.SPADES, Rank.SIX))

    assert deal.announcement_winning_team == Team.TEAM_1_3
    assert deal.ordinary_announcement_points_by_team[Team.TEAM_1_3] == 90
    assert deal.ordinary_announcement_points_by_team[Team.TEAM_0_2] == 0


def test_stoeck_scores_independently_when_second_card_is_played():
    deal = DealState(
        hands={
            0: [c(Suit.HEARTS, Rank.KING), c(Suit.HEARTS, Rank.QUEEN), c(Suit.CLUBS, Rank.SIX)],
            1: [c(Suit.CLUBS, Rank.SEVEN)],
            2: [c(Suit.CLUBS, Rank.EIGHT)],
            3: [c(Suit.CLUBS, Rank.NINE)],
        },
        dealer_starter=0,
        chooser=0,
    )
    deal.choose_trump(0, TrumpChoice.direct(Suit.HEARTS))

    deal.play_card(0, c(Suit.HEARTS, Rank.KING))
    assert deal.stoeck_points_by_team[Team.TEAM_0_2] == 0
    deal.play_card(1, c(Suit.CLUBS, Rank.SEVEN))
    deal.play_card(2, c(Suit.CLUBS, Rank.EIGHT))
    deal.play_card(3, c(Suit.CLUBS, Rank.NINE))
    deal.play_card(0, c(Suit.HEARTS, Rank.QUEEN))

    assert deal.revealed_stoeck == {0}
    assert deal.stoeck_points_by_team[Team.TEAM_0_2] == 20


def test_player_view_hides_other_hands_and_old_tricks_except_last():
    deal = DealState(
        hands={0: [c(Suit.CLUBS, Rank.SIX)], 1: [], 2: [], 3: []},
        dealer_starter=0,
        chooser=0,
        trump=Suit.CLUBS,
    )
    view = deal.view_for(0, score=(10, 20))

    assert view.hand == (c(Suit.CLUBS, Rank.SIX),)
    assert view.score == (10, 20)
    assert not hasattr(view, "all_completed_tricks")
