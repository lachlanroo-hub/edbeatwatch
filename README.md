# EdBeat Watch

A Massachusetts education reporting dashboard and school-committee meeting archive.

## Live meeting tracker goal

The tracker is being built to maintain a reporter-friendly list of Massachusetts school committee and school board meetings happening **this week**. As districts announce meetings or add agendas, packets, amendments, livestreams or other materials, the repository should capture those changes before the meeting and retain them afterward.

## Repository layout

- `index.html` — education reporting dashboard
- `school-committee.html` — school committee tracker page
- `data/sources.json` — official district/board meeting-source registry
- `data/meetings.json` — normalized meeting data consumed by the site
- `data/source_state.json` — generated hashes/status for monitored sources
- `archive/source-snapshots/` — preserved changed versions of official source pages
- `scripts/update_meetings.py` — scheduled collector
- `.github/workflows/update-meetings.yml` — runs the collector every three hours

## Build plan

1. Register official meeting sources statewide.
2. Snapshot registered sources and detect changes automatically.
3. Add source-specific parsers (CivicEngage, BoardOnTrack, BoardDocs/Simbli and district pages) that normalize meetings into `data/meetings.json`.
4. Render `school-committee.html` from that data with **This Week**, **New / Changed**, topic flags and an archive.
5. Preserve agendas, packets and revisions where practical, with source URLs and hashes for provenance.

The existing public site is preserved while the automated pipeline is built out incrementally.
