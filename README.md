# Scene

Interactive UX prototype for an AI movie recommendation app.

## Flows

- **Solo:** prompt → AI match → five short-form recommendations → taste recap → two refined picks → watch.
- **Group:** room lobby → shared prompt → private picks → combined shortlist → blind vote → result → watch.

## Run locally

```sh
python3 -m http.server 4173
```

Open `http://localhost:4173`.

The prototype is dependency-free and uses mocked data throughout.
