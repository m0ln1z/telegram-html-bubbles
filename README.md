# Telegram HTML Bubbles: a practical guide

**English** · [Русский](README.ru.md)

HTML Bubbles are interactive HTML widgets that a bot sends **inside a chat message** (Telegram 13.2+, Bot API 10.4). This repo explains the technical side: the API, the runtime limits and the mistakes that silently break a widget. It also ships runnable examples.

> Status (Nov 2026): Bot API 10.4 is in **beta**. The methods work only on the beta base URL, and details may still change. The source of truth is Telegram's [widget-sandbox](https://github.com/TelegramMessenger/widget-sandbox) repo (`docs/widget-runtime-profile.md`, `docs/profile-v1.md`, `docs/sdk-v1.md`, `docs/tgw-format.md`).

## Contents

1. [Quick start](#quick-start)
2. [Bot side: API](#bot-side-api)
3. [Size limits](#size-limits)
4. [The bubble: layout rules](#the-bubble-layout-rules)
5. [The paint limit (the #1 reason a widget goes blank)](#the-paint-limit)
6. [What HTML/CSS/JS is allowed](#what-is-allowed)
7. [Input](#input)
8. [JS SDK: `TelegramWidget`](#js-sdk-telegramwidget)
9. [State and requests to the bot](#state-and-requests-to-the-bot)
10. [Runtime limits](#runtime-limits)
11. [Testing](#testing)
12. [Troubleshooting](#troubleshooting)
13. [Checklist before sending](#checklist-before-sending)

## Repo layout

```
examples/widgets/01-hello.html              static, theme-aware, edge to edge
examples/widgets/02-tap-counter.html        click + localStorage + haptics
examples/widgets/03-animation-paint-safe.html  40 animated elements, 0 heavy boxes
examples/widgets/04-poll.html               request() -> widget_query -> answer + state edit
examples/bot/bot.py                         stdlib-only bot that sends all of the above
tools/probe.py                              is sendWidget available for my token? where?
tools/check_widget.py                       size (as the server counts) + common-mistake lint
run.sh                                      venv + .env + start the bot
```

## Quick start

```sh
git clone <this repo> && cd telegram-html-bubbles
cp .env.example .env            # put BOT_TOKEN from @BotFather
python3 tools/probe.py          # (with BOT_TOKEN exported) shows where sendWidget exists
./run.sh                        # creates .venv, starts the bot
```

Then send the bot `/hello`, `/counter`, `/anim` or `/poll`. The bot uses only the Python standard library, so the venv has nothing to install.

The recipient needs **Telegram 13.2+** to see the widget.

## Bot side: API

### Base URL

On the regular base URL, `sendWidget` returns **`Not Found`**. It is available on the beta base URL:

```
https://api.telegram.org/beta/bot<TOKEN>/<method>
```

A normal production bot token works there; `getMe`, `getUpdates` and everything else work too, so you can point the whole bot at it. `tools/probe.py` checks both URLs. When 10.4 is released, switch `API_BASE` back to `https://api.telegram.org`.

### Methods

| Method | Purpose |
|---|---|
| `sendWidget` | Send a widget. Fields: `chat_id`, **`html`** (required), `width`, `height`, `chat_data`, `public_data`, `caption`, `allow_queries`, `is_shared`, `reply_markup` |
| `sendSharedWidget` | Post an existing shared widget again: `chat_id`, `widget_id`, `chat_data` |
| `answerWidgetQuery` | Answer a request from the widget: `widget_query_id`, `data` (≤ 1024 bytes, arrives as `result`) |
| `editMessageWidgetData` | Change the state of one message: `chat_id` + `message_id` (or `inline_message_id`), `chat_data`, `public_data` |
| `editSharedWidgetData` | Change the state of a shared widget everywhere: `widget_id`, `public_data`, `cache_time` (5–3600 s) |

Inline mode: an article with `InputWidgetMessageContent` (same fields) or `InputSharedWidgetMessageContent` (`widget_id`). `copyMessage` of a widget is refused; forward it instead.

### Updates

Add them to `allowed_updates`, otherwise you will never receive them:

```json
{"allowed_updates": ["message", "widget_query", "shared_widget_query"]}
```

- `widget_query`: a request from the original message. Fields: `id`, `from`, `chat` + `message_id` (or `inline_message_id`), `data`, and `widget_id` for shared widgets.
- `shared_widget_query`: a request from a copy of a shared widget. Fields: `id`, `from`, `data`, `widget_id`.

**Answer every query** with `answerWidgetQuery`, including on errors. An unanswered query ends in the widget as `TIMEOUT`.

### Rules for edits

- An edit that changes nothing fails with `message is not modified`. Treat it as success.
- Apply the user's action to your own state **only after** the edit succeeds. Otherwise a failed edit loses a vote or a move.
- Keep a revision number in the state (`"r": 41`) and increase it on every edit, so the widget can drop stale states (see `04-poll.html`).

### Minimal send

```python
api("sendWidget", {"chat_id": chat_id, "html": open("widget.html").read()})
# width/height omitted (= 0): bubble width, content height
```

## Size limits

- **32 768 bytes** of HTML, and **4096 bytes** after zlib level 9 (PHP `gzcompress($html, 9)`). If it is larger, the server returns `INPUT_MEDIA_WIDGET_TOO_LARGE`.
- Measure it the way the server does:
  ```sh
  python3 -c 'import sys,zlib; print(len(zlib.compress(sys.stdin.buffer.read(), 9)))' < widget.html
  ```
  `gzip -9` reports about 12 bytes more. Near the limit, trust the Python number.
- Repetitive markup compresses very well. `data:` images barely compress. Generating repeated elements with a small JS loop (see `03`) is cheaper than writing them out by hand.

## The bubble: layout rules

- **Width:** 200–600 px; phones lay out at about **320–430 px**. `width: 0` (or omitted) means the bubble's width, and `W` means a fixed width clamped to the client maximum. **Do not assume your width:** a 320 px design inside a 420 px bubble leaves an empty strip on the right. Use `width: 100%` for backgrounds and centre fixed-size scenes (`left: 50%; margin-left: -W/2`).
- **Height:** `height: 0` means the content height, clamped to [50, 600]. `H` means a fixed height of clamp(H, 50, 600). Anything taller is clipped, and nothing scrolls inside a widget.
- **Keep the root in normal flow.** The content height is measured from the document flow. If the root element is `position: absolute`, the client measures roughly **50 px** and your widget is cut off. Use `position: relative` with an explicit height on the root, and put absolute children inside it.
- **`body` has a default margin**, the client's text padding (`--tg-text-padding`, about `8px 12px`). Without `body { margin: 0 }`, everything is shifted, and you get a strip of bubble colour on the left and top while the right and bottom edges are cut off.
- `html` has no background, so the bubble colour shows through. A background on `html`/`body` paints the whole bubble.
- **The message time** is drawn over the bottom corner. Keep `env(safe-area-inset-bottom)` free: `padding-bottom: max(12px, env(safe-area-inset-bottom))`.
- **Theme:** use `--tg-theme-bg-color`, `--tg-theme-text-color`, `--tg-theme-hint-color`, `--tg-theme-button-color`, `--tg-theme-button-text-color`, `--tg-theme-secondary-bg-color` and so on. `prefers-color-scheme` follows the **chat** theme.
- No `vh` units. Use px, %, flex or grid.

## The paint limit

**At most 16 "heavy" boxes at once**, of which at most 2 may use `backdrop-filter`. If the widget goes over, the renderer **stops** it (`Paint limit exceeded: N boxes with shadows, filters or transparency (max 16)`). On the device it looks like a blank or black bubble, or a frozen frame with a "Widget stopped" badge.

A box is heavy if it has any of these:

1. `opacity` **below 1, including 0**;
2. any `filter` other than `none` (including `drop-shadow`);
3. any `backdrop-filter`;
4. a `box-shadow` with blur radius > 0;
5. a **running animation** of `opacity`, `filter`, `backdrop-filter` or a blurred `box-shadow`. It counts for the whole animation, and an `infinite` animation counts forever.

Boxes that are **not** heavy: `transform` animations, `visibility`, elements under `display: none`, shadows without blur, and the opacity of a disabled or pressed `<button>`.

The typical trap: 12 twinkling stars with `@keyframes { opacity: 0 → 1 }`, plus a few semi-transparent decorations, plus letters that fade in, add up to more than 16, and the widget dies at the first frame.

How to stay under the limit:

| Instead of | Use |
|---|---|
| `opacity: .5` | `rgba()` / `hsla()` colours; `fill-opacity`, `stroke-opacity` in SVG |
| fade-in (`opacity 0 → 1`) | `transform: scale(0) → scale(1)` or a slide (`translate`) |
| fade-out | slide out of the clipped area, or `scale(0)` |
| glow via `filter: drop-shadow` / blurred `box-shadow` | a `radial-gradient` that fades to transparent |
| animated shadow | animate `transform` on a static gradient element |

Hidden content (`display: none`) costs nothing until it is shown. When it is shown, its boxes count.

## What is allowed

The full list is in `docs/profile-v1.md` of widget-sandbox. If something is outside the profile, the client **silently removes it** and runs the rest, so the widget looks broken without any error.

**Works:** text, lists, tables, `<details>/<summary>`, `<a>`, `<button>`, `<canvas>` (2D), `<img>` with `data:` PNG/JPEG/GIF/WebP (≤ 1024×1024), inline SVG (shapes, paths, text, `<use>`, gradients). CSS: flex, grid, positioning, radii, gradients, 2D transforms, transitions, `@keyframes`, custom properties, `calc/min/max/clamp`, `:active`, `::before/::after`, `@media` (width, `prefers-color-scheme`, `prefers-reduced-motion`), `@supports`. Fonts: `system-ui`, `sans-serif`, `serif`, `monospace`, `ui-*` only. JS: ES2023, timers, `requestAnimationFrame`, DOM, layout reads, canvas 2D, Web Animations, `Intl`, `localStorage`/`sessionStorage`.

**Removed:** form controls (`input`, `select`, `textarea`…), `audio`/`video`, `iframe`, external `<script src>`/CSS/fonts/images, `@font-face`, `@import`, `text-shadow`, `clip-path`, `mask`, `background-clip: text`, 3D transforms, `position: sticky`, `overflow: auto/scroll` (it becomes hidden), `vh` units, SVG `clipPath`/`mask`/`filter`/SMIL/`foreignObject`, `:focus`/`:checked`/`:has()`/`:target`, CSS nesting, `@container`, `@layer`.

**Throws:** `fetch`, `XMLHttpRequest`, `WebSocket` (`NetworkDisabledError`). `alert`/`confirm`/`prompt`, `window.open`, clipboard and fullscreen are not available.

Element ids are **not** global variables. Use `document.getElementById('x')`.

## Input

- `click` and pointer events are delivered. **Taps and double taps always go to the widget.**
- **Vertical drags always scroll the chat.** You cannot claim them.
- Holds and horizontal drags are claimed per element with `touch-action`. `auto` (the default) leaves the hold to the message menu and horizontal swipes to reply. `pan-y` gives horizontal drags to the widget. `none` gives holds and horizontal drags to the widget.
- When the chat takes a press, the widget gets `pointercancel` and no `click`.
- There is no keyboard, no focus, no touch events (use pointer events), and no wheel or scroll events.
- Keep controls at least 20 px from the leading edge, where the system back gesture lives.

## JS SDK: `TelegramWidget`

`window.TelegramWidget` exists only inside Telegram. **Always guard it** (`if (window.TelegramWidget) …`), because it is undefined in a browser.

```js
TelegramWidget.colorScheme;                 // 'light' | 'dark' (the chat's)
TelegramWidget.themeParams.bg_color;        // palette
TelegramWidget.onEvent('themeChanged', fn); // also 'activated' / 'deactivated'
TelegramWidget.ready();                     // optional: first state drawn
TelegramWidget.openLink('https://…');       // only inside a real tap handler; user confirms
TelegramWidget.openTelegramLink('https://t.me/…');
TelegramWidget.copyText('PROMO');           // tap handler only
TelegramWidget.HapticFeedback.impactOccurred('light');
TelegramWidget.chatData; TelegramWidget.publicData;   // state strings (≤ 1024 B) or null
TelegramWidget.onEvent('chatDataChanged', fn);        // and 'publicDataChanged'
TelegramWidget.request('vote:1');           // ask the bot (see below)
TelegramWidget.setResizeAnchor('bottom');   // grow upward; default 'top'
TelegramWidget.viewer; TelegramWidget.isForward; TelegramWidget.chatType; TelegramWidget.isPreview;
```

`TelegramWidget.sendMessage` does **not** exist. A widget never posts to the chat; it can only ask the bot.

Privileged calls (`openLink`, `copyText`, `request`, wallet) work **once per real tap** and only inside the tap's handler (`click`/`pointerup`). They do not work from timers, promises or `pointerdown`.

## State and requests to the bot

The HTML **never changes** after sending. Only the **state** changes, and only the bot writes it.

- `chat_data`: this message in this chat. Everyone in a group sees the same value, and a forward does not get it. Use it for a game in progress.
- `public_data`: shown everywhere the widget is shown. A forward gets a snapshot; a shared widget (`is_shared`) gets one live state. Use it for poll results or a price.
- Both are UTF-8 strings of up to 1024 bytes. JSON is the usual format.
- For a live shared state, the widget calls `TelegramWidget.watchPublicData()` and the client polls while the widget is on screen.
- `localStorage`: per message, per device, 4 KB per area. Use it for the user's own choices. A forwarded copy starts empty.

**Request flow** (`04-poll.html` + `bot.py`):

```
widget (tap)  request('vote:2')                         data: 1–64 bytes
   └─> bot    update.widget_query {id, from, chat, message_id, data}
        ├─ editMessageWidgetData(public_data=…)        -> widget gets publicDataChanged
        └─ answerWidgetQuery(widget_query_id=id, data=JSON) -> promise resolves {result}
```

The promise rejects with `err.code` set to one of: `NOT_ALLOWED` (no tap, sent without `allow_queries`, or a forward that may not ask), `BUSY` (one request at a time), `RATE_LIMITED`, `TIMEOUT` (the bot did not answer), `FAILED`, `INVALID_ANSWER`. Handle every code in the UI.

In the private chat with the bot, `request` can also run without a tap: once when the widget appears, then at most once every 5 s while it is visible. In groups, via inline mode and in forwards, it runs only on a tap.

## Runtime limits

| Resource | Limit |
|---|---|
| CPU | 300 ms per second; one task ≤ 500 ms, otherwise the widget is stopped |
| Main-thread cost (layout reads + ~25 µs per DOM change) | 100 ms per second |
| Memory | 8 MB |
| DOM nodes | 2000 |
| CSS | 400 rules, 32 `@keyframes` |
| Timers | 64 live |
| Layout reads per task | 128 |
| Canvas | 2048×2048 px total; 4000 commands per canvas per task |
| Heavy boxes | 16 (2 with `backdrop-filter`) |

Off screen there are no animation frames, and timers fire at most once per second. The widget can be destroyed and re-created at any time; only Web Storage and the widget state survive.

## Testing

1. **Size and lint** (instant, no dependencies):
   ```sh
   python3 tools/check_widget.py my-widget.html
   ```
2. **Official sandbox** (the real validator and renderer). This catches the paint limit, removed features and layout height:
   ```sh
   git clone https://github.com/TelegramMessenger/widget-sandbox && cd widget-sandbox
   npx pnpm@12 install
   cd packages/core && npx pnpm@12 tsx scripts/sandbox-node.ts /path/to/widget.html
   #   --width 360 also lays it out and prints a `paint:` line (needs `npx playwright install chromium`)
   #   --tap x,y / --hold x,y / --swipe x,y,dx,dy test gestures
   ```
   The dev app (`cd apps/web && npx pnpm@12 exec vite`, then `http://127.0.0.1:5173/?file=<corpus path>`) shows the bubble, its status (`loaded` or `sandbox terminated: …`), the bubble height, diagnostics and a mock bot panel. Files must be inside `corpus/` to be listed.
   If `corepack pnpm` fails with `Cannot find module …/pnpm.cjs`, use `npx pnpm@12` as shown.
3. **A real device.** Send the widget to yourself, to a group, via inline mode, and forward it. Each place gives the widget different rights. A desktop browser preview is **not** enough: Chrome happily renders things that the Telegram renderer stops or removes.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `sendWidget` → `Not Found` | Regular base URL | Use `https://api.telegram.org/beta` |
| `parameter "html" is required` on an empty call | That is expected | The method exists, so send a real payload |
| `INPUT_MEDIA_WIDGET_TOO_LARGE` | > 32 KB raw or > 4 KB zlib-9 | Generate repeats in JS, shorten class names, drop `data:` images |
| Blank or black bubble, or frozen frame / "Widget stopped" | Paint limit (> 16 heavy boxes), CPU/memory limit, or a crash | Run the sandbox; replace `opacity`/`filter`/blurred shadows; see [The paint limit](#the-paint-limit) |
| Strip on the left/top, right/bottom cut off | Default `body` margin | `body { margin: 0 }` |
| Empty strip on the right | Fixed 320 px design in a wider bubble | `width: 100%` + centred scene |
| Widget cut to ~50 px high | Absolutely positioned root; flow height is 0 | Root in normal flow (`position: relative` + height) |
| Animation never plays / element missing | Feature outside the profile, removed silently | Check `profile-v1.md`; look at sandbox `diag` lines |
| `request()` → `NOT_ALLOWED` | Sent without `allow_queries`, no tap, or a forward | `allow_queries: true`; call it inside `click` |
| `request()` → `TIMEOUT` | Bot did not call `answerWidgetQuery`, or `widget_query` is missing from `allowed_updates` | Always answer; subscribe to the update |
| Edit fails with `message is not modified` | State unchanged | Treat as success |
| Works in Chrome, broken in Telegram | Chrome is not the renderer | Test in the sandbox and on a device |

## Checklist before sending

- [ ] `body { margin: 0 }`, root in normal flow, `width: 100%`, no `vh`
- [ ] ≤ 16 heavy boxes **at any moment**: no `opacity` < 1, `filter` or blurred shadows on many elements; animations use `transform` only
- [ ] ≤ 32 KB raw / ≤ 4 KB zlib-9
- [ ] only system font families; no external resources; no network calls
- [ ] `TelegramWidget` guarded; privileged calls only in `click` handlers
- [ ] bottom corner kept free for the time (`env(safe-area-inset-bottom)`)
- [ ] theme variables used and checked in dark and light chat themes
- [ ] bot: beta base URL, `widget_query` in `allowed_updates`, every query answered, `not modified` treated as success
- [ ] passed the official sandbox with status `loaded` and no `diag` lines; checked on a real device
