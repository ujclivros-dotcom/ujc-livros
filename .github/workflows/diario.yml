name: Radar diario
on:
  schedule:
    - cron: "0 10 * * *"
  workflow_dispatch:
permissions:
  contents: write
jobs:
  rodar:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install requests
      - run: python radar.py
        env:
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASS: ${{ secrets.SMTP_PASS }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
      - run: |
          git config user.name "radar"
          git config user.email "radar@users.noreply.github.com"
          git add seen.json && git commit -m "vistos" || true
          git push
