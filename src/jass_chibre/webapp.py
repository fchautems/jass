from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .bots import choose_first_trump, play_bot_turn
from .engine import DealState, GameState
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

    def new_deal(self) -> None:
        self.deal = self.game.start_deal()
        self.messages = [f"Nouvelle donne. Le joueur {self.deal.chooser} choisit l'atout."]
        self.last_deal_summary = None
        self._auto_choose_trump_if_needed()
        self._auto_play_bots_until_human()

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
        self._auto_play_bots_until_human()

    def play_human_card(self, card: Card) -> None:
        if self.deal is None or self.deal.trump is None:
            self.messages.append("Choisissez d'abord l'atout.")
            return
        if _current_player(self.deal) != HUMAN_PLAYER:
            self.messages.append("Ce n'est pas encore à vous de jouer.")
            return
        try:
            self.deal.play_card(HUMAN_PLAYER, card)
            self.messages.append(f"Vous jouez {format_card_plain(card)}.")
        except ValueError as exc:
            self.messages.append(str(exc))
            return
        self._auto_play_bots_until_human()

    def _auto_choose_trump_if_needed(self) -> None:
        if self.deal is None:
            return
        while self.deal.trump is None and self.deal.chooser != HUMAN_PLAYER:
            chooser = self.deal.chooser
            choice = choose_first_trump(self.deal)
            assert choice.suit is not None
            self.deal.choose_trump(chooser, choice)
            self.messages.append(f"Bot {chooser} choisit {SUIT_LABELS[choice.suit]} comme atout.")

    def _auto_play_bots_until_human(self) -> None:
        if self.deal is None or self.deal.trump is None:
            return
        while not self.deal.finished and _current_player(self.deal) != HUMAN_PLAYER:
            player, card = play_bot_turn(self.deal)
            self.messages.append(f"Bot {player} joue {format_card_plain(card)}.")
            if self.deal.completed_tricks and not self.deal.current_trick:
                trick = self.deal.completed_tricks[-1]
                self.messages.append(f"Joueur {trick.winner} gagne le pli ({trick.points} points).")
        if self.deal.finished:
            self._finish_deal_once()

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
    score = session.game.score_tuple()
    body = [
        "<h1>Jass Chibre romand</h1>",
        '<p><a class="button secondary" href="/new">Nouvelle donne</a></p>',
        f"<p><strong>Score partie:</strong> équipe 0/2 {score[0]} — équipe 1/3 {score[1]}</p>",
    ]
    if deal is None:
        body.append("<p>Aucune donne.</p>")
        return _layout("".join(body))

    body.append(_status_html(deal))
    body.append(_messages_html(session.messages[-12:]))
    if deal.trump is None and deal.chooser == HUMAN_PLAYER:
        body.append(_trump_choice_html())
    elif deal.finished:
        body.append("<p>La donne est terminée. Lancez une nouvelle donne pour continuer.</p>")
    else:
        body.append(_table_html(deal))
        if _current_player(deal) == HUMAN_PLAYER:
            body.append(_hand_html(deal))
        else:
            body.append("<p>Les bots jouent automatiquement; rechargez si besoin.</p>")
    return _layout("".join(body))


def _layout(content: str) -> str:
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Jass Chibre romand</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 24px auto; background: #f7f4ee; color: #1f2933; }}
.panel {{ background: white; border: 1px solid #ddd4c8; border-radius: 12px; padding: 16px; margin: 14px 0; box-shadow: 0 1px 2px #0001; }}
.card, .button {{ display: inline-block; border: 1px solid #8d7b68; border-radius: 10px; padding: 10px 12px; margin: 5px; background: #fff; text-decoration: none; color: #1f2933; }}
.card.legal {{ border-width: 2px; border-color: #157347; }}
.card.disabled {{ opacity: .45; }}
.red {{ color: #b42318; }}
.black {{ color: #111827; }}
.button {{ background: #244c8f; color: white; }}
.button.secondary {{ background: #6b7280; }}
ul {{ padding-left: 20px; }}
</style>
</head>
<body>{content}</body>
</html>"""


def _status_html(deal: DealState) -> str:
    trump = "pas encore choisi" if deal.trump is None else f"{SUIT_SYMBOLS[deal.trump]} {SUIT_LABELS[deal.trump]}"
    current = "choix de l'atout" if deal.trump is None else f"joueur {_current_player(deal)}"
    return f"""<div class="panel">
<p><strong>Atout:</strong> {trump}</p>
<p><strong>À jouer:</strong> {current}</p>
<p><strong>Points plis de la donne:</strong> équipe 0/2 {deal.trick_points_by_team[Team.TEAM_0_2]} — équipe 1/3 {deal.trick_points_by_team[Team.TEAM_1_3]}</p>
</div>"""


def _messages_html(messages: list[str]) -> str:
    items = "".join(f"<li>{escape(message)}</li>" for message in messages)
    return f'<div class="panel"><h2>Journal</h2><ul>{items}</ul></div>'


def _trump_choice_html() -> str:
    buttons = "".join(
        f'<a class="button" href="/choose?suit={suit.name}">{SUIT_SYMBOLS[suit]} {SUIT_LABELS[suit]}</a>' for suit in Suit
    )
    return f'<div class="panel"><h2>Choisir l\'atout</h2>{buttons}<a class="button secondary" href="/choose?chibre=1">Chibrer</a></div>'


def _table_html(deal: DealState) -> str:
    current = "".join(f"<span class='card'>{player}: {format_card(card)}</span>" for player, card in deal.current_trick)
    if not current:
        current = "<em>Aucune carte dans le pli en cours.</em>"
    last = "<em>Aucun pli terminé.</em>"
    if deal.completed_tricks:
        trick = deal.completed_tricks[-1]
        cards = " ".join(f"{player}: {format_card(card)}" for player, card in trick.plays)
        last = f"{cards}<br>Gagnant: joueur {trick.winner}, {trick.points} points"
    return f'<div class="panel"><h2>Pli en cours</h2>{current}<h2>Dernier pli</h2><p>{last}</p></div>'


def _hand_html(deal: DealState) -> str:
    legal = set(deal.legal_cards_for(HUMAN_PLAYER))
    cards = []
    for card in deal.hands[HUMAN_PLAYER]:
        css = "card legal" if card in legal else "card disabled"
        label = format_card(card)
        if card in legal:
            cards.append(f'<a class="{css}" href="/play?card={card.suit.name}|{card.rank.name}">{label}</a>')
        else:
            cards.append(f'<span class="{css}">{label}</span>')
    return '<div class="panel"><h2>Votre main</h2><p>Les cartes avec bord vert sont jouables.</p>' + "".join(cards) + "</div>"


def format_card(card: Card) -> str:
    color = "red" if card.suit in (Suit.HEARTS, Suit.DIAMONDS) else "black"
    return f"<span class='{color}'>{RANK_LABELS[card.rank]}{SUIT_SYMBOLS[card.suit]}</span>"


def format_card_plain(card: Card) -> str:
    return f"{RANK_LABELS[card.rank]}{SUIT_SYMBOLS[card.suit]}"


def _current_player(deal: DealState) -> int | None:
    if deal.trump is None or deal.current_leader is None or deal.finished:
        return None
    return deal.current_leader if not deal.current_trick else (deal.current_leader + len(deal.current_trick)) % 4


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
