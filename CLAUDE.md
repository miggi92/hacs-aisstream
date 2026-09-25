# hacs-aisstream

Home Assistant Custom-Integration für [aisstream.io](https://aisstream.io) (Live-AIS-Schiffsdaten per WebSocket).

**Diese Datei muss aktuell bleiben.** Ändert sich eine hier dokumentierte
Konvention (Release-Ablauf, Commit-Stil, Tests), aktualisiere sie im selben PR.

## Tests

```sh
pip install -r requirements_test.txt
pytest
```

Läuft auch per GitHub Action (`.github/workflows/tests.yaml`), zusammen mit
`hassfest` und der HACS-Validierung.

## Commit-Konventionen

Commit-Messages folgen [Conventional Commits](https://www.conventionalcommits.org/):
`<type>(<scope>): <description>`, Scope optional.

`CHANGELOG.md` wird per [changelogen](https://github.com/unjs/changelogen) aus
genau diesen Commit-Messages generiert. Nur folgende Typen landen im Changelog
(siehe `changelog`-Feld in `package.json`):

| Typ        | Abschnitt im Changelog |
| ---------- | ---------------------- |
| `feat`     | ✨ Features            |
| `fix`      | 🐛 Bugfixes            |
| `docs`     | 📚 Dokumentation       |
| `refactor` | 🚜 Refactoring         |
| `perf`     | ⚡ Performance         |
| `test`     | 🧪 Tests               |
| `ci`       | ⚙️ CI                  |
| `chore`    | 🔧 Sonstiges           |
| `revert`   | ◀️ Revert              |

Alles andere (unkonventionelle Messages, Merge-Commits) wird übersprungen.
`chore(deps): ...` (Renovate) blendet changelogen automatisch aus.

## Release-Prozess

Komplett automatisiert, nichts davon von Hand anfassen:

1. Ein GitHub-Milestone mit einem Versionsnamen (`0.7.0` oder `v0.7.0`) wird
   geschlossen → `.github/workflows/milestone_release.yaml` erstellt daraus
   einen Git-Tag + GitHub-Release (`v<version>`). Benötigt das Repo-Secret
   `RELEASE_TOKEN` (PAT mit "Contents: Read and write"), weil ein mit dem
   `GITHUB_TOKEN` erstellter Release keine Folge-Workflows auslöst.
   Alternativ kann ein Release auch manuell in der GitHub-UI veröffentlicht
   werden.
2. Das veröffentlichte Release triggert `.github/workflows/publish.yaml`:
   - `version` in `custom_components/aisstream/manifest.json` wird auf die
     Tag-Version gesetzt,
   - die Integration wird als `aisstream.zip` ans Release gehängt (HACS
     installiert dieses Zip, siehe `zip_release` in `hacs.json`),
   - `changelogen` schreibt den neuen Abschnitt in `CHANGELOG.md` und
     committet ihn auf `main`,
   - die Release-Beschreibung wird aus diesem Changelog-Abschnitt befüllt.

**Wichtig für PRs:**

- `version` in `manifest.json` NICHT manuell hochzählen – das passiert beim
  Release aus dem Tag.
- `CHANGELOG.md` NICHT manuell editieren – wird nur vom Publish-Workflow
  geschrieben.
