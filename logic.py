"""Game logic: data loading, state management, scoring, audio processing."""

import csv
import io
import random
import time
import json

from pathlib import Path
from uuid import uuid4
from typing import Optional

import soundfile as sf

from config import DEFAULT_LIVES, CSV_LABEL_FILE, CSV_FALLBACK_FILE, AUDIO_SUBDIR

LEADERBOARD_PATH = Path("game_database/leaderboard.json")

def load_leaderboard():
    try:
        return json.loads(LEADERBOARD_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_leaderboard(entries):
    LEADERBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEADERBOARD_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")

LOCAL_RESULTS_PATH = Path("game_database/results_local.json")

def save_local_result(state):
    try:
        existing = json.loads(LOCAL_RESULTS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        existing = []

    existing.append({
        "session_id": state.session_id,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "score": state.score,
        "trials": state.trials,
        "correct": state.correct,
        "accuracy_pct": round(state.correct / state.trials * 100) if state.trials else 0,
        "lives_left": state.lives,
        "rounds": state.rounds,
    })

    LOCAL_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_RESULTS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    
class GameState:
    def __init__(self):
        self.screen: str = "landing"
        self.username: str = ""
        self.lives: int = DEFAULT_LIVES
        self.score: int = 0
        self.trials: int = 0
        self.correct: int = 0
        self.current_pair: Optional[dict] = None
        self.answered: bool = False
        self.answer_correct: Optional[bool] = None
        self.answer_which: Optional[str] = None
        self.leaderboard: list = []
        self.db_loaded: bool = False
        self.session_id: str = str(uuid4())
        self.rounds: list = []
        self.export_success: Optional[bool] = None
        self.bonafide_entries: list = []
        self.spoof_entries: list = []
        self.round_start: float = 0.0
        self.shown_pairs: list = []
        self.next_catch: int = 5
        self.next_instruction: int = 10

def parse_id_mapping(csv_path):
    bonafide, spoof = [], []
    spoof_labels = {'synthetic', 'partial synthetic', 'spoof'}
    with open(csv_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            entry = {k.strip(): v.strip() for k, v in row.items()}
            lbl = entry.get('effective_label', '').lower()
            if lbl == 'bonafide':
                bonafide.append(entry)
            elif lbl in spoof_labels:
                spoof.append(entry)
    return bonafide, spoof

def find_audio_file(export_dir, audio_name):
    for ext in ('.wav', '.WAV', '.flac', '.mp3'):
        p = export_dir / AUDIO_SUBDIR / (audio_name + ext)
        if p.exists():
            return p
    return None

def load_audio_bytes(path):
    try:
        audio, sr = sf.read(str(path), dtype='float32', always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        buf = io.BytesIO()
        sf.write(buf, audio, sr, format='WAV')
        return buf.getvalue()
    except Exception:
        return None

def load_database(export_dir):
    csv_path = next(
        (p for p in (export_dir / CSV_LABEL_FILE, export_dir / CSV_FALLBACK_FILE) if p.exists()),
        None
    )
    if not csv_path:
        return False, [], []
    try:
        bonafide_raw, spoof_raw = parse_id_mapping(csv_path)
    except Exception:
        return False, [], []

    def with_audio(entries):
        result = []
        for e in entries:
            p = find_audio_file(export_dir, e.get('audio_name', ''))
            if p:
                result.append({**e, 'path': p})
        return result

    bonafide = with_audio(bonafide_raw)
    spoof = with_audio(spoof_raw)
    return bool(bonafide and spoof), bonafide, spoof

def get_next_pair(state):
    trial = state.trials + 1
    is_instruction = trial == state.next_instruction and len(state.shown_pairs) >= 1
    is_catch = trial == state.next_catch and len(state.shown_pairs) >= 1

    if is_instruction:
        pair = random.choice(state.shown_pairs).copy()
        pair['is_catch'] = True
        pair['catch_type'] = 'instruction'
        pair['instruction_letter'] = pair['real']
        state.next_instruction += 10
        state.next_catch += 5
        return pair

    if is_catch:
        pair = random.choice(state.shown_pairs).copy()
        pair['is_catch'] = True
        pair['catch_type'] = 'repeat'
        pair['instruction_letter'] = None
        state.next_catch += 5
        return pair

    pair = generate_trial_pair(state.bonafide_entries, state.spoof_entries)
    if pair is None:
        return None
    pair['is_catch'] = False
    pair['catch_type'] = None
    pair['instruction_letter'] = None
    state.shown_pairs.append(pair)
    return pair

def generate_trial_pair(bonafide_list, spoof_list):
    if not bonafide_list or not spoof_list:
        return None

    b = random.choice(bonafide_list)
    s = random.choice(spoof_list)
    b_audio = load_audio_bytes(b['path'])
    s_audio = load_audio_bytes(s['path'])
    if b_audio is None or s_audio is None:
        return None

    real_letter = 'A' if random.random() < 0.5 else 'B'
    base = {
        'real': real_letter,
        'bonafide_id': b.get('audio_name', ''),
        'bonafide_pipeline': b.get('pipeline', ''),
        'spoof_id': s.get('audio_name', ''),
        'spoof_model': s.get('tts_model', ''),
        'spoof_pipeline': s.get('pipeline', ''),
    }
    b_clip = ('bonafide', b_audio)
    s_clip = (s.get('effective_label', 'synthetic'), s_audio)
    if real_letter == 'A':
        return {**base, 'A': b_clip, 'B': s_clip}
    return {**base, 'A': s_clip, 'B': b_clip}

def handle_answer(state, chosen):
    if not state.current_pair:
        return
    pair = state.current_pair
    correct = chosen == pair['real']
    fake_letter = 'B' if pair['real'] == 'A' else 'A'

    state.answered = True
    state.answer_correct = correct
    state.answer_which = chosen
    state.trials += 1
    state.rounds.append({
        'round': state.trials,
        'real_letter': pair['real'],
        'user_choice': chosen,
        'correct': correct,
        'fake_label': pair[fake_letter][0],
        'fake_pipeline': pair.get('spoof_pipeline', ''),
        'fake_model': pair.get('spoof_model', ''),
        'bonafide_id': pair.get('bonafide_id', ''),
        'spoof_id': pair.get('spoof_id', ''),
        'time_spent_s': round(time.time() - state.round_start, 2),
        'is_catch': pair.get('is_catch', False),
        'catch_type': pair.get('catch_type'),
        'catch_consistent': chosen == pair['real'] if pair.get('is_catch') else None,
    })

    if correct:
        state.score += 10
        state.correct += 1
    elif not pair.get('is_catch'):
        state.lives -= 1

def submit_leaderboard_entry(state):
    acc = round(state.correct / state.trials * 100) if state.trials else 0
    state.leaderboard.append({
        'name': state.username,
        'score': state.score,
        'trials': state.trials,
        'correct': state.correct,
        'acc': acc,
        'ts': time.time(),
    })
    state.leaderboard.sort(key=lambda x: (-x['score'], -x['acc']))
    save_leaderboard(state.leaderboard)

def reset_game_state(state):
    state.lives = DEFAULT_LIVES
    state.score = 0
    state.trials = 0
    state.correct = 0
    state.current_pair = None
    state.answered = False
    state.answer_correct = None
    state.answer_which = None
    state.rounds = []
    state.session_id = str(uuid4())
    state.export_success = None
    state.clip_plays = {}
    state.round_start = 0.0