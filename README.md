# Reading the Room with AI — Explorer / Simulator

Interactive companion to Ortiz and Rodrigo, *Reading the Room with AI: FOMC Deliberation and Growth-at-Risk* (BBVA Research, paper v4.29n). Site: https://ortiz-bbvaresearch.github.io/Artefacto-Reading-The-Roon/

## Files

| File | Purpose |
|---|---|
| `index.html` | The whole explorer in one self-contained page (data embedded). Works online and as an offline file. |
| `data.json` | Same data in the update format the page reads on load (`meta`, `series`, `signals`, `ladder`, `robustness`, `rt`, `families`, `declared`, `alternatives`, `recessions`, `dist` [75 origins incl. live 2025Q2–2026Q2], `coef`, `alt`, `fam`, `sig`, `groups`). Replace it to update the site without touching `index.html`. |
| `.nojekyll` | Tells GitHub Pages to serve the files as they are. |

## Updating

1. Edit or regenerate `data.json` (keep `meta.bank = "FOMC"`; the page ignores any file without the expected keys).
2. Commit and push to the branch that GitHub Pages serves. The page re-reads `data.json` on load, on **Push here to update data**, and every 15 minutes.

The previous `data.json` published at this address belonged to another monitor (Spanish macro series, 75 series) and was not in this format; this copy replaces it with the simulator's own data.

## Data

All figures are aggregates taken from the paper's sealed forecast banks (Tables 2, 7, 8 and 9 and the Hidden Dissent series by meeting). The Hidden Dissent index follows Tsang and Yang (2025, *Journal of Economic Dynamics and Control*). No speaker-level or private data is included.
