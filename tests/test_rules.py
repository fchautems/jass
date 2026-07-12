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
    assert winner == 1


def test_card_points_total_152_and_last_trick_bonus_157():
    from jass_chibre.rules import build_deck, trick_points

    deck = build_deck()

    assert sum(card_points(card, Suit.HEARTS) for card in deck) == 152
    assert trick_points(deck, Suit.HEARTS, is_last_trick=True) == 157


def test_counterclockwise_play_order_is_enforced():
    deal = DealState(
        hands={
            0: [c(Suit.CLUBS, Rank.SIX)],
            1: [c(Suit.CLUBS, Rank.NINE)],
            2: [c(Suit.CLUBS, Rank.EIGHT)],
            3: [c(Suit.CLUBS, Rank.SEVEN)],
        },
        dealer_starter=0,
        chooser=0,
    )
    deal.choose_trump(0, TrumpChoice.direct(Suit.HEARTS))

    deal.play_card(0, c(Suit.CLUBS, Rank.SIX))

    with pytest.raises(ValueError, match="expected 3"):
        deal.play_card(1, c(Suit.CLUBS, Rank.NINE))

    deal.play_card(3, c(Suit.CLUBS, Rank.SEVEN))
    deal.play_card(2, c(Suit.CLUBS, Rank.EIGHT))
    deal.play_card(1, c(Suit.CLUBS, Rank.NINE))

    assert deal.completed_tricks[-1].winner == 1


def test_player_can_cut_even_with_led_suit_and_bour_is_never_forced():
    hand = [c(Suit.CLUBS, Rank.SIX), c(Suit.SPADES, Rank.ACE), c(Suit.HEARTS, Rank.JACK)]
    trick = [c(Suit.CLUBS, Rank.ACE)]
    assert set(legal_cards(hand, trick, Suit.HEARTS)) == {c(Suit.CLUBS, Rank.SIX), c(Suit.HEARTS, Rank.JACK)}

    screenshot_case_hand = [c(Suit.CLUBS, Rank.SEVEN), c(Suit.CLUBS, Rank.EIGHT), c(Suit.DIAMONDS, Rank.JACK)]
    diamond_trick = [c(Suit.DIAMONDS, Rank.ACE), c(Suit.DIAMONDS, Rank.QUEEN), c(Suit.DIAMONDS, Rank.NINE)]
    assert set(legal_cards(screenshot_case_hand, diamond_trick, Suit.CLUBS)) == set(screenshot_case_hand)

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

    deal.play_card(3, c(Suit.SPADES, Rank.SIX))
    deal.play_card(2, c(Suit.HEARTS, Rank.SIX))
    deal.play_card(1, c(Suit.DIAMONDS, Rank.ACE))

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
    deal.play_card(3, c(Suit.CLUBS, Rank.NINE))
    deal.play_card(2, c(Suit.CLUBS, Rank.EIGHT))
    deal.play_card(1, c(Suit.CLUBS, Rank.SEVEN))
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


def test_naive_bot_can_choose_trump_and_play_a_legal_card():
    from jass_chibre.bots import choose_first_legal_card, choose_first_trump

    deal = GameState().start_deal(seed=4)
    chooser = deal.chooser
    choice = choose_first_trump(deal)
    deal.choose_trump(chooser, choice)

    player = deal.current_leader
    card = choose_first_legal_card(deal, player)
    assert card in deal.legal_cards_for(player)

    deal.play_card(player, card)
    assert card not in deal.hands[player]


def test_web_page_renders_human_hand_and_new_deal_link():
    from jass_chibre.webapp import WebSession, render_page

    session = WebSession()
    session.new_deal()
    html = render_page(session)

    assert "Jass Chibre romand" in html
    assert "Nouvelle donne" in html
    assert "Total partie" in html
    assert "Plis donne" in html
    assert "Annonces + stöck" in html
    assert "table-grid" in html
    assert "Dernier pli" in html


def test_web_displays_trick_points_separately_from_announcements_and_stoeck():
    from jass_chibre.webapp import WebSession, render_page

    deal = DealState(
        hands={0: [], 1: [], 2: [], 3: []},
        dealer_starter=0,
        chooser=0,
        trump=Suit.HEARTS,
        current_leader=0,
    )
    deal.trick_points_by_team[Team.TEAM_0_2] = 80
    deal.trick_points_by_team[Team.TEAM_1_3] = 77
    deal.ordinary_announcement_points_by_team[Team.TEAM_0_2] = 50
    deal.stoeck_points_by_team[Team.TEAM_1_3] = 20

    html = render_page(WebSession(deal=deal))

    assert "Plis donne" in html
    assert "Vous 80 · Eux 77 / 157" in html
    assert "Annonces + stöck" in html
    assert "Vous 50 · Eux 20" in html


def test_web_marks_trumps_playable_when_human_can_cut():
    from jass_chibre.webapp import WebSession, render_page

    deal = DealState(
        hands={
            0: [c(Suit.CLUBS, Rank.SEVEN), c(Suit.CLUBS, Rank.EIGHT), c(Suit.DIAMONDS, Rank.JACK)],
            1: [],
            2: [],
            3: [],
        },
        dealer_starter=3,
        chooser=3,
        trump=Suit.CLUBS,
        current_leader=3,
        current_trick=[
            (3, c(Suit.DIAMONDS, Rank.ACE)),
            (2, c(Suit.DIAMONDS, Rank.QUEEN)),
            (1, c(Suit.DIAMONDS, Rank.NINE)),
        ],
    )

    html = render_page(WebSession(deal=deal))

    assert 'class="card legal" href="/play?card=CLUBS|SEVEN"' in html
    assert 'class="card legal" href="/play?card=CLUBS|EIGHT"' in html
    assert 'class="card legal" href="/play?card=DIAMONDS|JACK"' in html


def test_web_does_not_offer_second_chibre_after_partner_receives_choice():
    from jass_chibre.webapp import WebSession, render_page

    deal = DealState(
        hands={0: [], 1: [], 2: [], 3: []},
        dealer_starter=2,
        chooser=0,
        chibred_by=2,
    )

    html = render_page(WebSession(deal=deal))

    assert "Choisir l'atout" in html
    assert "Chibrer" not in html


def test_dealer_rotation_goes_counterclockwise_after_finished_deal():
    game = GameState()
    deal = DealState(hands={0: [], 1: [], 2: [], 3: []}, dealer_starter=0, finished=True)
    deal.deal_points_by_team[Team.TEAM_0_2] = 80
    deal.deal_points_by_team[Team.TEAM_1_3] = 77
    game.current_deal = deal

    game.finish_deal_if_done()

    assert game.next_dealer_starter == 3
    assert game.score_tuple() == (80, 77)


def test_web_hand_is_visible_before_trump_choice():
    from jass_chibre.webapp import WebSession, render_page

    deal = DealState(
        hands={
            0: [c(Suit.CLUBS, Rank.SIX), c(Suit.DIAMONDS, Rank.ACE)],
            1: [],
            2: [],
            3: [],
        },
        dealer_starter=0,
        chooser=0,
    )
    html = render_page(WebSession(deal=deal))

    assert "Votre main" in html
    assert "6♣" in html
    assert "A♦" in html
    assert "Choisir l'atout" in html


def test_web_bot_step_plays_only_one_card_at_a_time():
    from jass_chibre.webapp import WebSession

    deal = DealState(
        hands={
            0: [],
            1: [c(Suit.CLUBS, Rank.SIX), c(Suit.SPADES, Rank.ACE)],
            2: [],
            3: [],
        },
        dealer_starter=1,
        chooser=1,
        trump=Suit.HEARTS,
        current_leader=1,
    )
    session = WebSession(deal=deal)

    session.step()

    assert len(deal.current_trick) == 1
    assert deal.current_trick[0][0] == 1
    assert len(deal.hands[1]) == 1


def test_completed_trick_stays_on_table_until_next_step():
    from jass_chibre.webapp import WebSession, render_page

    deal = DealState(
        hands={
            0: [],
            1: [c(Suit.CLUBS, Rank.NINE)],
            2: [],
            3: [],
        },
        dealer_starter=0,
        chooser=0,
        trump=Suit.HEARTS,
        current_leader=0,
        current_trick=[
            (0, c(Suit.CLUBS, Rank.SIX)),
            (3, c(Suit.CLUBS, Rank.SEVEN)),
            (2, c(Suit.CLUBS, Rank.EIGHT)),
        ],
    )
    session = WebSession(deal=deal)

    session.step()
    html_while_paused = render_page(session)

    assert session.table_trick is not None
    assert "9♣" in html_while_paused
    assert "Aucun pli terminé" in html_while_paused

    session.step()
    html_after_pause = render_page(session)

    assert session.table_trick is None
    assert "Gagnant: joueur 1" in html_after_pause
