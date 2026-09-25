# Fake One Out

Synthetic speech is increasingly realistic, driven by advances in generative AI that are rapidly closing the perceptual gap between human and machine-generated voices. Attackers can further conceal synthetic speech by applying cheap audio processing that degrades quality and removes authenticity cues.

This is a game that tests your ability to detect synthetic speech. Each round presents two clips: one real human voice, one AI-generated. Pick the real one. The goal is to raise awareness of how convincing synthetic voices have become.


## Project Structure

```
├── game_database/
│   ├── labels/              # id_mapping.csv 
│   ├── audio/               #  utterances 
│   ├── leaderboard.json     # persistent 
│   └── results_local.json   # anonymous results (local)
├── app.py                   # Streamlit UI 
├── config.py                # constants and text strings
├── logic.py                 # game state
├── export.py                # GitHub results
├── manipulations.py         # audio manipulation pipeline
├── build_database.py        # builds utt. database
└── pyproject.toml
```

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv sync
```

## Building the Database

Samples 50 bonafide and 50 synthetic utterances (≥5 s, stratified by speaker and TTS model), applies one randomly assigned audio manipulation per utterance with balanced distribution across manipulation types, and writes audio and a CSV label file.

## Running

```bash
uv run streamlit run app.py
```

## GitHub Export (Optional)

To enable anonymous result upload, add a `.streamlit/secrets.toml`:

```toml
[github]
token  = "ghp_..."
repo   = "username/repo"
branch = "main"
folder = "results"
```

Results are always saved locally to `game_database/results_local.json` regardless of whether GitHub is configured.

## Assets

**LLAMAPARTIALSPOOF**  
Luong, H.-T., Li, H., Zhang, L., Lee, K. A., & Chng, E. S. (2024, November 26).  
LlamaPartialSpoof (1.0.b). Zenodo. https://doi.org/10.5281/zenodo.14214149

**SAFE CHALLENGE**
Kirill, T., Cummer, P., Pherwani, P., Aslam, J., Davinroy, M., Bautista, P., ... & Stamm, M. (2025, June). SAFE: Synthetic audio forensics evaluation challenge. In Proceedings of the 2025 ACM Workshop on Information Hiding and Multimedia Security (pp. 174-180).

**THE INTERNATIONAL SOUNDSCAPE DATABASE**  
Mitchell, A., Oberman, T., Aletta, F., Erfanian, M., Kachlicka, M., Lionello, M., Fang, X., & Kang, J. (2024).  
The International Soundscape Database (1.0.1-alpha.1). Zenodo. https://doi.org/10.5281/zenodo.10672568