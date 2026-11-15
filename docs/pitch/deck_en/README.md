# Rotacast pitch deck (English, static)

English version of the Team Apollon pitch deck for NASA Space Apps Challenge 2026 (Field Shift, Konya).
This copy has no animations and no video slide, so it reads well as a PDF.

- `project/deck.json`: slide order and fonts (Fraunces, Inter).
- `project/deck.css`: shared styles.
- `project/slides/*.html`: one file per slide (13 slides), with speaker notes in `<aside>`.
- `img/`: app screenshots (English UI, Çumra sample field). In the slide files they are referenced by their
  hosted asset ids:
  - `/_blob/c3b5276e2bba2fe08c2c4946cac11b5d` = `img/app_input_en.jpg` (slide `rotacast`)
  - `/_blob/953b2188f719e0a16571f3e76a970d12` = `img/beginner_cards_en.png` (slide `uygulama`)
  - `/_blob/9a9ed450a60d05f39b99f87205f5a52d` = `img/advanced_lowrisk_en.png` (slide `uygulama`)

All numbers come from the offline demo reports in `data/demo/`. Income figures are estimated gross income
(costs not deducted). AI use is declared in our submission.
