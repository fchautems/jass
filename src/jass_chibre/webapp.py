from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .bots import choose_first_trump, play_bot_turn
from .engine import CompletedTrick, DealState, GameState
from .model import Card, Rank, Suit, Team, TrumpChoice

HUMAN_PLAYER = 0

SUIT_SYMBOLS = {
    Suit.HEARTS: "♥",
    Suit.DIAMONDS: "♦",
    Suit.SPADES: "♠",
    Suit.CLUBS: "♣",
}
SUIT_LABELS = {
    Suit.HEARTS: "Cœur",
    Suit.DIAMONDS: "Carreau",
    Suit.SPADES: "Pique",
    Suit.CLUBS: "Trèfle",
}
RANK_LABELS = {
    Rank.SIX: "6",
    Rank.SEVEN: "7",
    Rank.EIGHT: "8",
    Rank.NINE: "9",
    Rank.TEN: "10",
    Rank.JACK: "V",
    Rank.QUEEN: "D",
    Rank.KING: "R",
    Rank.ACE: "A",
}


@dataclass
class WebSession:
    game: GameState = field(default_factory=GameState)
    deal: DealState | None = None
    messages: list[str] = field(default_factory=list)
    last_deal_summary: str | None = None
    table_trick: CompletedTrick | None = None

    def new_deal(self) -> None:
        self.deal = self.game.start_deal()
        self.messages = [f"Nouvelle donne. Le joueur {self.deal.chooser} choisit l'atout."]
        self.last_deal_summary = None
        self.table_trick = None
        self._auto_choose_trump_if_needed()

    def choose_trump_for_human(self, suit: Suit | None, chibre: bool = False) -> None:
        if self.deal is None:
            self.new_deal()
            return
        if self.deal.chooser != HUMAN_PLAYER:
            self.messages.append("Ce n'est pas au joueur humain de choisir l'atout.")
            return
        if chibre:
            self.deal.choose_trump(HUMAN_PLAYER, TrumpChoice.pass_to_partner())
            self.messages.append("Vous avez chibré: votre partenaire choisit l'atout.")
        elif suit is not None:
            self.deal.choose_trump(HUMAN_PLAYER, TrumpChoice.direct(suit))
            self.messages.append(f"Vous choisissez {SUIT_LABELS[suit]} comme atout.")
        self._auto_choose_trump_if_needed()

    def play_human_card(self, card: Card) -> None:
        if self.deal is None or self.deal.trump is None:
            self.messages.append("Choisissez d'abord l'atout.")
            return
        if _current_player(self.deal) != HUMAN_PLAYER:
            self.messages.append("Ce n'est pas encore à vous de jouer.")
            return
        trick_count = len(self.deal.completed_tricks)
        try:
            self.deal.play_card(HUMAN_PLAYER, card)
            self.messages.append(f"Vous jouez {format_card_plain(card)}.")
        except ValueError as exc:
            self.messages.append(str(exc))
            return
        self._hold_new_completed_trick(trick_count)

    def _auto_choose_trump_if_needed(self) -> None:
        if self.deal is None:
            return
        while self.deal.trump is None and self.deal.chooser != HUMAN_PLAYER:
            chooser = self.deal.chooser
            choice = choose_first_trump(self.deal)
            assert choice.suit is not None
            self.deal.choose_trump(chooser, choice)
            self.messages.append(f"Bot {chooser} choisit {SUIT_LABELS[choice.suit]} comme atout.")

    def step(self) -> None:
        """Avance d'une seule étape visible: un bot, ou transfert du pli terminé."""
        if self.deal is None:
            self.new_deal()
            return
        if self.table_trick is not None:
            self.table_trick = None
            if self.deal.finished:
                self._finish_deal_once()
            return
        self._auto_choose_trump_if_needed()
        if self.deal.trump is None or self.deal.finished:
            if self.deal.finished:
                self._finish_deal_once()
            return
        if _current_player(self.deal) == HUMAN_PLAYER:
            return
        trick_count = len(self.deal.completed_tricks)
        player, card = play_bot_turn(self.deal)
        self.messages.append(f"Bot {player} joue {format_card_plain(card)}.")
        self._hold_new_completed_trick(trick_count)

    def should_auto_advance(self) -> bool:
        if self.deal is None:
            return False
        if self.table_trick is not None:
            return True
        if self.deal.trump is None:
            return self.deal.chooser != HUMAN_PLAYER
        return not self.deal.finished and _current_player(self.deal) != HUMAN_PLAYER

    def _hold_new_completed_trick(self, previous_count: int) -> None:
        if self.deal is None or len(self.deal.completed_tricks) == previous_count:
            return
        self.table_trick = self.deal.completed_tricks[-1]
        trick = self.table_trick
        self.messages.append(f"Joueur {trick.winner} gagne le pli ({trick.points} points).")

    def _finish_deal_once(self) -> None:
        if self.deal is None or not self.deal.finished or self.last_deal_summary is not None:
            return
        points_02 = self.deal.deal_points_by_team[Team.TEAM_0_2]
        points_13 = self.deal.deal_points_by_team[Team.TEAM_1_3]
        self.last_deal_summary = f"Donne terminée: équipe 0/2 {points_02} points, équipe 1/3 {points_13} points."
        self.messages.append(self.last_deal_summary)
        self.game.finish_deal_if_done()


SESSION = WebSession()


class JassRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - API http.server
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/new":
            SESSION.new_deal()
            self._redirect("/")
            return
        if SESSION.deal is None:
            SESSION.new_deal()
        if parsed.path == "/choose":
            self._handle_choose(query)
            return
        if parsed.path == "/play":
            self._handle_play(query)
            return
        if parsed.path == "/step":
            SESSION.step()
            self._redirect("/")
            return
        self._send_html(render_page(SESSION))

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_choose(self, query: dict[str, list[str]]) -> None:
        if "chibre" in query:
            SESSION.choose_trump_for_human(None, chibre=True)
        else:
            suit = _parse_suit(query.get("suit", [""])[0])
            SESSION.choose_trump_for_human(suit)
        self._redirect("/")

    def _handle_play(self, query: dict[str, list[str]]) -> None:
        card = _parse_card(query.get("card", [""])[0])
        if card is None:
            SESSION.messages.append("Carte inconnue.")
        else:
            SESSION.play_human_card(card)
        self._redirect("/")

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def render_page(session: WebSession) -> str:
    deal = session.deal
    if deal is None:
        content = """
        <header class="topbar"><h1>Jass Chibre romand</h1><a class="button secondary" href="/new">Nouvelle donne</a></header>
        <div class="panel"><p>Aucune donne.</p></div>
        """
        return _layout(content)

    body = [
        '<header class="topbar"><h1>Jass Chibre romand</h1><a class="button secondary" href="/new">Nouvelle donne</a></header>',
        _scoreboard_html(session),
        _table_layout_html(session),
    ]
    if deal.trump is None and deal.chooser == HUMAN_PLAYER:
        body.append(_trump_choice_html(deal))
    elif deal.finished and session.table_trick is None:
        body.append('<div class="panel"><p>La donne est terminée. Lancez une nouvelle donne pour continuer.</p></div>')
    elif session.should_auto_advance():
        body.append('<div class="panel small-note">Le jeu avance automatiquement pour montrer chaque carte jouée.</div>')
    body.append(_hand_html(deal))
    return _layout("".join(body), auto_advance=session.should_auto_advance())


def _layout(content: str, auto_advance: bool = False) -> str:
    auto_script = '<script>setTimeout(() => { window.location.href = "/step"; }, 1200);</script>' if auto_advance else ""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Jass Chibre romand</title>
<style>
:root {{ --felt: #247344; --felt-dark: #185632; --wood: #ead2aa; --ink: #1f2933; }}
body {{ font-family: system-ui, sans-serif; max-width: 1180px; margin: 20px auto; background: var(--wood); color: var(--ink); }}
.topbar {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 12px; }}
h1 {{ margin: 0; }}
.panel {{ background: #fffaf0; border: 1px solid #d3bd96; border-radius: 14px; padding: 16px; margin: 14px 0; box-shadow: 0 2px 4px #0002; }}
.scoreboard {{ display: grid; grid-template-columns: repeat(5, minmax(130px, 1fr)); gap: 10px; }}
.scorebox {{ background: #263238; color: white; border-radius: 10px; padding: 12px; }}
.scorebox strong {{ display: block; font-size: 0.85rem; opacity: .8; margin-bottom: 4px; }}
.table-grid {{ display: grid; grid-template-columns: 170px 1fr 170px; grid-template-rows: 130px minmax(250px, auto) auto auto; gap: 12px; align-items: center; }}
.player-seat {{ text-align: center; font-weight: 700; }}
.player-seat.partner {{ grid-column: 2; grid-row: 1; }}
.player-seat.left {{ grid-column: 1; grid-row: 2; writing-mode: vertical-rl; justify-self: center; }}
.player-seat.right {{ grid-column: 3; grid-row: 2; writing-mode: vertical-rl; justify-self: center; }}
.player-seat.you {{ grid-column: 2; grid-row: 3; }}
.table-center {{ grid-column: 2; grid-row: 2; background: radial-gradient(circle at center, #2d8a51, var(--felt)); border: 6px solid var(--felt-dark); border-radius: 34px; min-height: 250px; padding: 18px; box-shadow: inset 0 0 18px #0004; }}
.current-trick {{ display: grid; grid-template-columns: 1fr 1fr 1fr; grid-template-rows: auto auto auto; min-height: 220px; align-items: center; justify-items: center; }}
.play-slot {{ min-width: 86px; min-height: 118px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; color: white; font-weight: 700; text-shadow: 0 1px 1px #0008; }}
.play-slot.p0 {{ grid-column: 2; grid-row: 3; }}
.play-slot.p1 {{ grid-column: 1; grid-row: 2; }}
.play-slot.p2 {{ grid-column: 2; grid-row: 1; }}
.play-slot.p3 {{ grid-column: 3; grid-row: 2; }}
.last-trick {{ grid-column: 1 / 4; grid-row: 4; align-self: stretch; }}
.last-trick-cards {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
.card, .button {{ display: inline-flex; align-items: center; justify-content: center; border: 1px solid #8d7b68; border-radius: 10px; padding: 10px 12px; margin: 5px; background: #fff; text-decoration: none; color: #1f2933; min-width: 44px; min-height: 62px; font-size: 1.25rem; font-weight: 800; box-shadow: 0 2px 3px #0002; }}
.card.small {{ min-width: 34px; min-height: 48px; font-size: 1rem; padding: 7px 9px; margin: 2px; }}
.card.back {{ color: #f8fafc; background: repeating-linear-gradient(45deg, #194a8d 0 5px, #f8fafc 5px 7px, #b42318 7px 10px); border-color: white; }}
.card.empty {{ background: #ffffff22; border: 1px dashed #ffffff99; box-shadow: none; color: #fff; font-size: .85rem; }}
.card.legal {{ border-width: 3px; border-color: #16a34a; transform: translateY(-4px); }}
.card.disabled {{ opacity: .45; }}
.hand {{ display: flex; flex-wrap: wrap; justify-content: center; }}
.red {{ color: #b42318; }}
.black {{ color: #111827; }}
.button {{ background: #244c8f; color: white; min-height: auto; font-size: 1rem; }}
.button.secondary {{ background: #6b7280; }}
.small-note {{ color: #46515f; }}
@media (max-width: 760px) {{
  .scoreboard {{ grid-template-columns: 1fr 1fr; }}
  .table-grid {{ grid-template-columns: 1fr; grid-template-rows: auto; }}
  .player-seat, .player-seat.partner, .player-seat.left, .player-seat.right, .player-seat.you, .table-center, .last-trick {{ grid-column: 1; grid-row: auto; writing-mode: horizontal-tb; }}
}}
</style>
</head>
<body>{content}</body>
{auto_script}</html>"""


def _scoreboard_html(session: WebSession) -> str:
    deal = session.deal
    game_score = session.game.score_tuple()
    if deal is None:
        trick_02 = trick_13 = 0
        bonus_02 = bonus_13 = 0
        trump = "—"
        current = "—"
    else:
        trick_02 = _visible_trick_total(deal, Team.TEAM_0_2)
        trick_13 = _visible_trick_total(deal, Team.TEAM_1_3)
        bonus_02 = _visible_bonus_total(deal, Team.TEAM_0_2)
        bonus_13 = _visible_bonus_total(deal, Team.TEAM_1_3)
        trump = "pas choisi" if deal.trump is None else f"{SUIT_SYMBOLS[deal.trump]} {SUIT_LABELS[deal.trump]}"
        current = "choix atout" if deal.trump is None else f"joueur {_current_player(deal)}"
    return f"""<section class="scoreboard panel">
<div class="scorebox"><strong>Total partie</strong>Vous {game_score[0]} · Eux {game_score[1]}</div>
<div class="scorebox"><strong>Plis donne</strong>Vous {trick_02} · Eux {trick_13} / 157</div>
<div class="scorebox"><strong>Annonces + stöck</strong>Vous {bonus_02} · Eux {bonus_13}</div>
<div class="scorebox"><strong>Atout</strong>{trump}</div>
<div class="scorebox"><strong>À jouer</strong>{current}</div>
</section>"""


def _visible_trick_total(deal: DealState, team: Team) -> int:
    return deal.trick_points_by_team[team]


def _visible_bonus_total(deal: DealState, team: Team) -> int:
    return deal.ordinary_announcement_points_by_team[team] + deal.stoeck_points_by_team[team]


def _table_layout_html(session: WebSession) -> str:
    assert session.deal is not None
    deal = session.deal
    return f"""<section class="table-grid panel" aria-label="Table de jeu">
{_player_seat_html(deal, 2, 'partner', 'Partenaire')}
{_player_seat_html(deal, 1, 'left', 'Adversaire 1')}
<div class="table-center">{_current_trick_html(session)}</div>
{_player_seat_html(deal, 3, 'right', 'Adversaire 3')}
{_player_seat_html(deal, 0, 'you', 'Vous')}
{_last_trick_html(session)}
</section>"""


def _player_seat_html(deal: DealState, player: int, css_class: str, label: str) -> str:
    count = len(deal.hands[player])
    marker = " ♦" if player == HUMAN_PLAYER else ""
    backs = "".join('<span class="card small back" aria-hidden="true"></span>' for _ in range(min(count, 9)))
    return f'<div class="player-seat {css_class}">{escape(label)}{marker}<div>{backs}</div><small>{count} cartes</small></div>'


def _current_trick_html(session: WebSession) -> str:
    assert session.deal is not None
    trick_on_table = session.table_trick
    plays = dict(trick_on_table.plays if trick_on_table is not None else session.deal.current_trick)
    slots = []
    for player in (2, 1, 3, 0):
        card = plays.get(player)
        card_html = format_card(card) if card is not None else '<span class="card empty">—</span>'
        slots.append(f'<div class="play-slot p{player}"><span>J{player}</span>{card_html}</div>')
    return '<div class="current-trick">' + "".join(slots) + "</div>"


def _last_trick_html(session: WebSession) -> str:
    assert session.deal is not None
    visible_tricks = list(session.deal.completed_tricks)
    if session.table_trick is not None and visible_tricks and visible_tricks[-1] == session.table_trick:
        visible_tricks = visible_tricks[:-1]
    if not visible_tricks:
        content = '<p><em>Aucun pli terminé.</em></p>'
    else:
        trick = visible_tricks[-1]
        cards = "".join(f'<span>J{player} {format_card(card)}</span>' for player, card in trick.plays)
        content = f'<div class="last-trick-cards">{cards}</div><p>Gagnant: joueur {trick.winner} · {trick.points} points</p>'
    return f'<aside class="last-trick panel"><h2>Dernier pli</h2>{content}</aside>'


def _trump_choice_html(deal: DealState) -> str:
    buttons = "".join(
        f'<a class="button" href="/choose?suit={suit.name}">{SUIT_SYMBOLS[suit]} {SUIT_LABELS[suit]}</a>' for suit in Suit
    )
    chibre_button = '' if deal.chibred_by is not None else '<a class="button secondary" href="/choose?chibre=1">Chibrer</a>'
    return f'<div class="panel"><h2>Choisir l\'atout</h2>{buttons}{chibre_button}</div>'


def _hand_html(deal: DealState) -> str:
    legal = set(deal.legal_cards_for(HUMAN_PLAYER)) if deal.trump is not None and _current_player(deal) == HUMAN_PLAYER else set()
    cards = []
    for card in deal.hands[HUMAN_PLAYER]:
        css = "card legal" if card in legal else "card disabled"
        label = format_card_label(card)
        if card in legal:
            cards.append(f'<a class="{css}" href="/play?card={card.suit.name}|{card.rank.name}">{label}</a>')
        else:
            cards.append(f'<span class="{css}">{label}</span>')
    return '<div class="panel"><h2>Votre main</h2><p>Les cartes avec bord vert sont jouables.</p><div class="hand">' + "".join(cards) + "</div></div>"


def format_card(card: Card) -> str:
    color = "red" if card.suit in (Suit.HEARTS, Suit.DIAMONDS) else "black"
    return f"<span class='card {color}'>{RANK_LABELS[card.rank]}{SUIT_SYMBOLS[card.suit]}</span>"


def format_card_label(card: Card) -> str:
    color = "red" if card.suit in (Suit.HEARTS, Suit.DIAMONDS) else "black"
    return f"<span class='{color}'>{RANK_LABELS[card.rank]}{SUIT_SYMBOLS[card.suit]}</span>"


def format_card_plain(card: Card) -> str:
    return f"{RANK_LABELS[card.rank]}{SUIT_SYMBOLS[card.suit]}"


def _current_player(deal: DealState) -> int | None:
    if deal.trump is None or deal.current_leader is None or deal.finished:
        return None
    return deal.current_leader if not deal.current_trick else (deal.current_leader - len(deal.current_trick)) % 4


def _parse_suit(value: str) -> Suit | None:
    try:
        return Suit[value]
    except KeyError:
        return None


def _parse_card(value: str) -> Card | None:
    try:
        suit_name, rank_name = value.split("|", 1)
        return Card(Suit[suit_name], Rank[rank_name])
    except (KeyError, ValueError):
        return None


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    SESSION.new_deal()
    server = ThreadingHTTPServer((host, port), JassRequestHandler)
    print(f"Interface Jass disponible sur http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    run()


if __name__ == "__main__":
    main()
