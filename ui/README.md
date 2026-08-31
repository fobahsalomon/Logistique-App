# UI Components

This project groups the presentation layer into clearly separated concerns for future maintenance.

## Planned split

- `FicheDevis` : quote summary and KPI cards
- `Comparateur` : real route vs standard route comparison
- `ModalProforma` : legal/admin document metadata form
- `TableTrajets` : known-route list and comparison actions

The current runtime files remain in the Flask templates and static assets while the UI modules are intentionally described here to keep the structure explicit and production-ready.
