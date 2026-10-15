# Reading the Room with AI: FOMC Deliberation and Growth at Risk — explorer

Interactive companion to Ortiz and Rodrigo, *Reading the Room with AI* (working paper draft v4.25).

- `index.html` — the whole page, self-contained (no build step, no external scripts except Google Fonts).
- `data.json` — optional update file read by the page when it is served from a web server (GitHub Pages). Same schema as the page's *Data & updates* tab: any subset of `meta`, `series.hd_meetings` (`[["YYYY-MM-DD", value], …]`), `series.quarterly` (`[{"q":"2025Q4","hd":…,"ff":…,"g":…,"nfci":…,"spf":…}]`), `signals`, `ladder`, `robustness`, `rt`, `alternatives`. Series are merged by date, so the file can carry only the new readings.

## Publish with GitHub Pages
1. Create a repository (public, or private with GitHub Pro) and upload these three files to its root.
2. Settings → Pages → Build and deployment → Source: *Deploy from a branch* → Branch: `main`, folder `/ (root)` → Save.
3. After a minute the page is at `https://<user>.github.io/<repository>/`.

## Update the page
Edit or replace `data.json` and commit; the page reads it on every load. To change the results or the text, replace `index.html`.

Hidden Dissent index: Tsang and Yang (2025), *Journal of Economic Dynamics and Control* 180, 105197; data at https://www.digitecon.org/hidden-dissent-index.
