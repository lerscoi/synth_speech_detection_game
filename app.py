import argparse
import time
from pathlib import Path
import streamlit as st

from config import TEXTS, TEXTS_FI, DEFAULT_LIVES, EXPORT_DIR_DEFAULT, LOGO_PATH
from export import push_result
from logic import (
    GameState,
    load_database,
    get_next_pair,
    handle_answer,
    submit_leaderboard_entry,
    reset_game_state,
    load_leaderboard,
)

def get_text(key):
    """Returns the text for the current language."""
    lang = st.session_state.get("lang", "en")
    texts = TEXTS_FI if lang == "fi" else TEXTS
    return texts.get(key, key)

def _has_github_export():
    try:
        return "github" in st.secrets and bool(st.secrets["github"].get("token"))
    except Exception:
        return False

def _load_css():
    css_path = Path(__file__).parent / "styles.css"
    try:
        return css_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        st.error("CSS file 'styles.css' not found!")
        return ""

def render_landing_screen(game, export_dir):
    col_lang1, _ = st.columns([1, 5])
    with col_lang1:
        if st.button("🇬🇧 ENG", key="btn_lang_en"):
            st.session_state.lang = "en"
            st.rerun()
        if st.button("🇫🇮 FI", key="btn_lang_fi"):
            st.session_state.lang = "fi"
            st.rerun()
            
    _, instr_col, _, user_col = st.columns([1, 3, 0.5, 1])
    with instr_col:
        logo_col, title_col = st.columns([1, 3])
        with logo_col:
            if Path(LOGO_PATH).exists():
                st.markdown('<div class="logo-row">', unsafe_allow_html=True)
                st.image(LOGO_PATH, width=180)
                st.markdown('</div>', unsafe_allow_html=True)
        with title_col:
            st.write(" ")
            st.markdown(f'<div class="badge">{get_text("how_to_play_label")}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="hero-title">{get_text("hero_title")}</div>', unsafe_allow_html=True)

        st.markdown(f'<div class="hero-sub">{get_text("hero_sub")}</div>', unsafe_allow_html=True)
        rules_html = "".join(f"<li>{r}</li>" for r in get_text("rules"))
        st.markdown(f'<div class="instructions-box"><ul>{rules_html}</ul></div>', unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    with user_col:
        st.write(" ")
        username = st.text_input(
            "Your name:",
            placeholder="Enter a username:",
            key="name_input",
            label_visibility="collapsed",
        )
        db_ok, _, _ = load_database(export_dir)
        game.db_loaded = db_ok
        if not db_ok:
            st.warning(get_text("error_no_db").format(export_dir))

        if st.button(get_text("btn_start"), disabled=not (username.strip() and db_ok)):
            game.username = username.strip()
            reset_game_state(game)
            game.screen = "game"
            st.rerun()

        if game.leaderboard:
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            st.markdown(f'<div class="trial-label">{get_text("leaderboard_label")}</div>', unsafe_allow_html=True)
            render_leaderboard(game)

def render_game_screen(game):
    _, game_col, _ = st.columns([1, 4, 1])
    with game_col:
        lives_str = '♥' * game.lives + '♡' * (DEFAULT_LIVES - game.lives)
        col1, col2, col3 = st.columns(3)
        col1.markdown(f'<div class="stat-box"><div class="stat-val">{game.score}</div><div class="stat-lbl">Score</div></div>', unsafe_allow_html=True)
        col2.markdown(f'<div class="stat-box"><div class="stat-val">{game.trials}</div><div class="stat-lbl">Rounds</div></div>', unsafe_allow_html=True)
        color = '#dd4444' if game.lives == 1 else '#a0a0ff'
        col3.markdown(f'<div class="stat-box"><div class="stat-val" style="color:{color};letter-spacing:4px;">{lives_str}</div><div class="stat-lbl">Lives</div></div>', unsafe_allow_html=True)

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        if game.current_pair is None:
            pair = get_next_pair(game)
            if pair is None:
                #st.error(get_text("error_load_audio"])
                if st.button(get_text("btn_quit"), key="quit_btn"):
                    submit_leaderboard_entry(game)
                    game.screen = "consent"
                    st.rerun()
                return
            game.current_pair = pair
            game.round_start = time.time()
            game.clip_plays = {}

        pair = game.current_pair
        st.markdown(f'<div class="trial-label">{get_text("round_label").format(game.trials + 1)}</div>', unsafe_allow_html=True)
        if pair.get('catch_type') == 'instruction':
            letter = pair['instruction_letter']
            st.markdown(
                f'<div class="feedback-correct"><b>ATTENTION CHECK</b>: For this round, please select <b>Clip {letter}</b>.</div>',
                unsafe_allow_html=True
            )
    
        col_a, col_b = st.columns(2)
        for col, letter in zip((col_a, col_b), ('A', 'B')):
            with col:
                st.markdown(f'<div class="clip-card"><div class="clip-letter">Clip {letter}</div>', unsafe_allow_html=True)
                st.audio(pair[letter][1], format='audio/wav')
                st.markdown('</div>', unsafe_allow_html=True)
                if not game.answered:
                    if st.button(get_text(f"btn_clip_{letter.lower()}"), key=f"btn_{letter}"):
                        handle_answer(game, letter)
                        st.rerun()

        if game.answered:
            fake_letter = 'B' if pair['real'] == 'A' else 'A'
            fake_lbl = pair[fake_letter][0]
            if game.answer_correct:
                st.markdown(f'<div class="feedback-correct">{get_text("feedback_correct").format(fake_letter, fake_lbl)}</div>', unsafe_allow_html=True)
            else:
                life_text = max(game.lives, 0)
                note = (
                    get_text("lives_lost_note").format(life_text, "life" if life_text == 1 else "lives")
                    if game.lives > 0 else get_text("game_over_note")
                )
                st.markdown(f'<div class="feedback-wrong">{get_text("feedback_wrong").format(fake_letter, fake_lbl, note)}</div>', unsafe_allow_html=True)

            if game.lives <= 0:
                if st.button("SEE RESULTS ->"):
                    submit_leaderboard_entry(game)
                    game.screen = "consent"
                    st.rerun()
            elif st.button(get_text("btn_next")):
                game.current_pair = None
                game.answered = False
                st.rerun()

        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        if st.button(get_text("btn_quit"), key="quit_btn"):
            submit_leaderboard_entry(game)
            game.screen = "consent"
            st.rerun()

def render_consent_screen(game):
    st.markdown(f'<div class="badge">{get_text("consent_badge")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hero-title" style="font-size:clamp(1.5rem,6vw,2.2rem);">{get_text("consent_title")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hero-sub">{get_text("consent_intro")}</div>', unsafe_allow_html=True)
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(f'<div class="trial-label">{get_text("consent_data_label")}</div>', unsafe_allow_html=True)
    for item in get_text("consent_data_items"):
        st.markdown(f'<div class="consent-item">{item}</div>', unsafe_allow_html=True)
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    for line in (get_text("consent_no_pii"), get_text("consent_purpose"), get_text("consent_withdraw")):
        st.markdown(f'<div class="consent-legal">{line}</div>', unsafe_allow_html=True)
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button(get_text("btn_consent_yes")):
            with st.spinner("Submitting..."):
                game.export_success = push_result(game, st.secrets)
                st.session_state.consent_message = "success" if game.export_success else "fail"
        
            game.screen = "results"
            st.rerun()
    with col2:
        if st.button(get_text("btn_consent_no")):
            st.session_state.consent_message = "declined"
            game.screen = "results"
            st.rerun()

def render_results_screen(game):
    acc = round(game.correct / game.trials * 100) if game.trials else 0
    st.markdown('<div class="badge">GAME OVER</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hero-title">{game.score}<br><span style="font-size:1rem;color:#666688;">points</span></div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    col1.markdown(f'<div class="stat-box"><div class="stat-val">{game.trials}</div><div class="stat-lbl">Rounds</div></div>', unsafe_allow_html=True)
    col2.markdown(f'<div class="stat-box"><div class="stat-val">{acc}%</div><div class="stat-lbl">Accuracy</div></div>', unsafe_allow_html=True)
    col3.markdown(f'<div class="stat-box"><div class="stat-val">{game.lives}</div><div class="stat-lbl">Lives left</div></div>', unsafe_allow_html=True)
    
    msg = st.session_state.get("consent_message")
    if msg == "success":
        st.markdown(f'<div class="feedback-correct">{get_text("consent_success")}</div>', unsafe_allow_html=True)
    elif msg == "fail":
        st.markdown(f'<div class="feedback-wrong">{get_text("consent_fail")}</div>', unsafe_allow_html=True)
    elif msg == "declined":
        st.markdown(f'<div class="feedback-correct">No results saved. Thank you for participating!</div>', unsafe_allow_html=True)
    
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(f'<div class="trial-label">{get_text("leaderboard_label")}</div>', unsafe_allow_html=True)
    render_leaderboard(game, my_ts=game.leaderboard[-1]['ts'] if game.leaderboard else None)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    if st.button(get_text("btn_play_again")):
        reset_game_state(game)
        game.screen = "landing"
        st.rerun()

def render_leaderboard(game, my_ts=None):
    for i, entry in enumerate(game.leaderboard[:20]):
        is_me = my_ts is not None and entry['ts'] == my_ts
        medal = ['🥇', '🥈', '🥉'][i] if i < 3 else f'#{i+1}'
        cls = 'leaderboard-row me' if is_me else 'leaderboard-row'
        st.markdown(
            f'<div class="{cls}"><span class="rank-num">{medal}</span>'
            f'<span class="lb-name">{entry["name"]}</span>'
            f'<span class="lb-score">{entry["score"]}pts</span>'
            f'<span class="lb-acc">{entry["acc"]}%</span></div>',
            unsafe_allow_html=True,
        )

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--export_dir", default=EXPORT_DIR_DEFAULT)
    args, _ = parser.parse_known_args()
    export_dir = Path(args.export_dir)

    st.set_page_config(
        page_title=get_text("page_title"),
        page_icon=get_text("page_icon"),
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(f"<style>{_load_css()}</style>", unsafe_allow_html=True)

    if "game" not in st.session_state:
        st.session_state.game = GameState()
        if "lang" not in st.session_state:
            st.session_state.lang = "en"
        st.session_state.game.leaderboard = load_leaderboard()
    game = st.session_state.game

    if not game.db_loaded:
        ok, bf, sp = load_database(export_dir)
        if ok:
            game.bonafide_entries = bf
            game.spoof_entries = sp
            game.db_loaded = True

    screens = {
        'landing': lambda: render_landing_screen(game, export_dir),
        'game': lambda: render_game_screen(game),
        'consent': lambda: render_consent_screen(game),
        'results': lambda: render_results_screen(game),
    }

    screen_fn = screens.get(game.screen)
    if screen_fn:
        screen_fn()
    else:
        st.error(f"Unknown screen: {game.screen}")

if __name__ == "__main__":
    main()