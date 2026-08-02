#!/usr/bin/env python3
"""
🪐 9 Planets — Flagship Edition v17.0
CHANGES v17: quest display active-only, plank quest checks inventory, first-night fix,
         grot spawn fix, coffee +30 energy, remove butchering, axe icon fix,
         grot name fix, filtered-water from dirty-water, fatigue=0 blocks actions,
         campfire temp cap, trap durability 4-5 uses, stat warnings, cancel hints,
         bandage command, typo suggestions, inventory pagination, XP/day=50,
         red flash on starvation/thirst damage, spider silk damage, herbal tea fix,
         no fibergrass/forest-animals in Arctic, ice vein gives ice_chunk,
         station display show all, tools durability in inventory.
"""

import time, random, math, json, os, sys, select, signal, unicodedata, threading, io
try:
    import tty, termios
    HAVE_TERMIOS = True
except ImportError:
    HAVE_TERMIOS = False
    import msvcrt

# === CROSS-PLATFORM AUDIO SETUP — set SDL env vars before importing pygame ===
import os, sys as _sys
_plat = _sys.platform
if _plat == "linux":
    # Linux: prefer PulseAudio (works on modern desktops & SSH), fall back to ALSA
    os.environ.setdefault("SDL_AUDIODRIVER", "pulseaudio")
# Windows (win32) and macOS (darwin): let SDL auto-select DirectSound / CoreAudio
# === END AUDIO SETUP ===

try:
    import pygame
    from array import array
    PYGAME_AVAILABLE = True
except BaseException:
    pygame = None
    array = None
    PYGAME_AVAILABLE = False

# ==================== VISUAL WIDTH HELPERS ====================
# Emoji and CJK chars take 2 terminal columns; Python len() counts them as 1.
# These helpers measure and manipulate strings by visual column width.

def _cw(c):
    """Visual column width of a single character in a raw terminal.
    Box-drawing (U+2500-257F), block elements (U+2580-259F), and
    geometric shapes (U+25A0-25FF) are always 1 column wide.
    Emoji/CJK symbols (U+2600+) and higher planes (U+1F000+) are 2.
    """
    cp = ord(c)
    cat = unicodedata.category(c)
    if cat in ('Mn', 'Cf', 'Cc'): return 0   # combining / zero-width
    if 0xFE00 <= cp <= 0xFE0F: return 0        # variation selectors
    if 0xE0100 <= cp <= 0xE01EF: return 0      # VS supplement
    if 0x2500 <= cp <= 0x25FF: return 1         # box-drawing, blocks, geometric shapes
    if cp >= 0x2400:
        ew = unicodedata.east_asian_width(c)
        if ew in ('W', 'F'): return 2
        if cp >= 0x2600: return 2               # misc symbols, dingbats, emoji symbols
        return 1
    return 1

def vlen(s):
    """Visual width of a string in terminal columns."""
    return sum(_cw(c) for c in str(s))

def vtrunc(s, width):
    """Truncate string so its visual width <= width columns."""
    s = str(s); w = 0; out = []
    for c in s:
        cw = _cw(c)
        if w + cw > width: break
        out.append(c); w += cw
    return ''.join(out)

def vfit(s, width):
    """Truncate + space-pad string to exactly width visual columns."""
    s = str(s); t = vtrunc(s, width); gap = width - vlen(t)
    return t + ' ' * gap

def vwrap(s, width):
    """Wrap a string into lines that fit the visual width."""
    s = str(s).strip()
    words = s.split()
    if not words:
        return [""]
    lines = []
    cur = words[0]
    for w in words[1:]:
        if vlen(cur + " " + w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines

def _cell2(icon):
    """Normalize a single map tile to exactly 2 terminal columns.

    Most game emoji are in the high plane (>= U+1F000) with east_asian_width
    'W' and always occupy 2 terminal columns.  A few high-plane emoji (e.g.
    U+1F5E1 DAGGER 🗡️, U+1F6E1 SHIELD 🛡️) have east_asian_width 'N'
    (Neutral) and render as 1 column in most terminals.  Legacy "Misc
    Symbols" below U+1F000 (e.g. ☘, ☠, ⚔) are similarly 1-wide.  This
    function adds a trailing space to 1-wide cells so every map row is
    consistently 2 columns wide, keeping vertical movement perfectly aligned.

    Cells that contain ANSI escape codes still need their visible glyph padded;
    otherwise a 1-wide blink marker can leave half of the previous emoji behind.
    """
    if not icon:
        return "  "
    if "\033" in icon:
        try:
            import re as _re
            visible = _re.sub(r"\033\[[0-9;?]*[ -/]*[@-~]", "", icon)
            w = vlen(visible)
            if w < 2:
                return icon + " " * (2 - w)
            return icon
        except Exception:
            return icon
    cp0 = ord(icon[0])
    if cp0 >= 0x1F000:
        # High-plane emoji are almost always 2-wide (eaw='W'), but a handful
        # have eaw='N' and render as 1-wide in terminals (e.g. 🗡️, 🛡️).
        if unicodedata.east_asian_width(icon[0]) in ("W", "F"):
            return icon                         # fast path: unambiguously 2-wide
        # eaw 'N' or 'A' in high plane → treat as 1-wide, pad with space
        return icon + " "
    # Below U+1F000: measure actual visual width and pad if needed
    w = vlen(icon)
    if w < 2:
        return icon + " " * (2 - w)
    return icon

def _world_tile(x, y):
    """Return the exact resource tile used by gather/inspect/build actions."""
    return int(x), int(y)

# ==================== COMMANDS SIDEBAR ====================
# A reference list shown on the right side of wide terminals so players
# always see the basic command vocabulary (mirrors Help page 1).
SIDEBAR_COMMANDS = [
    # ── Movement ──────────────────────────────────────────────────────────
    ("⬆️⬇️⬅️➡️",   "Move 1 tile (arrow keys)"),
    ("walk <name>",  "Auto-walk to resource/animal"),
    ("walk <x,y>",   "Walk to exact coordinates"),
    # ── Combat ────────────────────────────────────────────────────────────
    ("attack / a",   "Strike nearest animal"),
    ("throw / t",    "Throw spear at nearest"),
    ("hunt <animal>","Hunt: rabbit/deer/seal…"),
    ("hunt … grid",  "Open tactical grid combat"),
    # ── Resources ─────────────────────────────────────────────────────────
    ("gather",       "Collect at current tile (-2⚡)"),
    ("gather all",   "Collect whole cluster"),
    ("inspect <x>",  "Identify unknown cluster"),
    ("identify <x>", "Alias for inspect"),
    ("explain <x>",  "Explain item details"),
    # ── Inventory & Crafting ──────────────────────────────────────────────
    ("inv",          "View inventory"),
    ("eat <item>",   "Eat food from inventory"),
    ("drink <item>", "Drink water / liquid"),
    ("craft <item>", "Start crafting an item"),
    ("cancel",       "Cancel crafting task"),
    ("pause craft",  "Pause / resume crafting"),
    ("recipes",      "Browse all recipes"),
    # ── Equipment ─────────────────────────────────────────────────────────
    ("equip <item>", "Equip armor / weapon"),
    ("wear <item>",  "Alias for equip"),
    ("remove <item>","Unequip item"),
    ("bandage",      "Apply bandage (heal)"),
    ("apply <item>", "Apply a usable item"),
    # ── Survival ──────────────────────────────────────────────────────────
    ("rest",         "Toggle resting (restore stats)"),
    ("unrest",       "Alias: stop resting"),
    ("fire",         "Light / extinguish campfire"),
    ("status",       "Show detailed status screen"),
    ("filter",       "Use water filter on water"),
    # ── Traps ─────────────────────────────────────────────────────────────
    ("trap set",     "Place a trap at current tile"),
    ("trap check",   "Collect caught animals"),
    ("trap remove",  "Pick up a trap"),
    ("trap list",    "Show all active traps"),
    ("traps",        "Alias for trap list"),
    # ── Economy & Quests ──────────────────────────────────────────────────
    ("shop",         "Browse shop items & prices"),
    ("buy <item>",   "Buy item from shop"),
    ("sell <item>",  "Sell item to shop"),
    ("quests",       "Active quest log"),
    ("achievements", "Progress & rewards"),
    # ── Game Control ──────────────────────────────────────────────────────
    ("pause",        "Pause / resume game"),
    ("resume",       "Resume (unpause)"),
    ("help",         "Open help menu (paginated)"),
    ("tutorials",    "Re-read tutorials"),
    ("save",         "Save progress to file"),
    ("commands",     "Toggle this command panel"),
    ("quit / exit",  "Exit game"),
]

def _build_commands_sidebar(width, height):
    """Return up to `height` strings, each exactly `width` visual columns wide."""
    if width < 12 or height < 3:
        return [" " * width] * max(0, height)
    title = "📜 COMMANDS"
    lines = [vfit(title, width), vfit("─" * width, width)]
    # Two-column layout inside the sidebar: cmd | desc
    cmd_w = min(14, max(10, width // 2 - 1))
    desc_w = width - cmd_w - 1
    for cmd, desc in SIDEBAR_COMMANDS:
        line = vfit(cmd, cmd_w) + " " + vfit(desc, desc_w)
        lines.append(vfit(line, width))
        if len(lines) >= height:
            break
    while len(lines) < height:
        lines.append(" " * width)
    return lines[:height]


# When Dev Mode is enabled from the start menu, the right-side sidebar shows
# live world stats (animal/cluster counts and a rough performance/expense
# readout, including audio cost) instead of the command reference.
_DEV_MODE = False

# Fast Mode: enabled from the start menu alongside quest/explorer mode. It pulls
# the Arctic in to 1000 coordinates away and makes everything craft 3x faster.
_FAST_MODE = False
_CRAFT_TIME_MULT = 1.0          # set to 1/3 in Fast Mode
_FAST_FOREST_RADIUS = 1000      # Arctic distance under Fast Mode

def _build_dev_sidebar(width, height, world, player):
    """Return up to `height` strings of dev/debug stats, each `width` wide."""
    if width < 12 or height < 3:
        return [" " * width] * max(0, height)

    # --- Gather raw counts ---
    try:
        animals = list(getattr(world, "animals", []) or [])
    except Exception:
        animals = []
    try:
        clusters = len(getattr(world, "clusters", {}) or {})
    except Exception:
        clusters = 0
    n_animals = len(animals)

    # Count animals currently in "hunt" / aggressive style modes for context
    hunting = 0
    for a in animals:
        try:
            if (a.get("mode") or a.get("state")) in ("hunt", "hunting", "chase", "attack"):
                hunting += 1
        except Exception:
            pass

    # --- Rough "expense" estimate (relative CPU cost units) ---
    # Animals are the priciest because smooth 0.1-step movement updates them
    # very frequently when near the player; clusters are cheap to iterate.
    animal_cost = n_animals * 3.0
    cluster_cost = clusters * 0.1
    sim_cost = animal_cost + cluster_cost

    # --- Audio / music cost ---
    snd = getattr(player, "sound", None)
    audio_on = bool(getattr(snd, "enabled", False))
    menu_music = bool(_MENU_MUSIC.get("playing")) if isinstance(_MENU_MUSIC, dict) else False
    if audio_on:
        music_cost = 8.0  # real-time mixing of bgm + ambient channels
        music_lbl = "~8% CPU (on)"
    elif menu_music:
        music_cost = 5.0
        music_lbl = "~5% CPU (menu)"
    else:
        music_cost = 0.0
        music_lbl = "0% (off)"

    total_cost = sim_cost + music_cost

    def _rate(v):
        if v < 30: return "LOW"
        if v < 90: return "MED"
        return "HIGH"

    rows = [
        ("🐾 Animals", str(n_animals)),
        ("   in hunt", str(hunting)),
        ("🌳 Clusters", str(clusters)),
        ("", ""),
        ("⚙️ Sim cost", f"{sim_cost:.0f} ({_rate(sim_cost)})"),
        ("🎵 Music", music_lbl),
        ("💻 Total", f"{total_cost:.0f} ({_rate(total_cost)})"),
    ]

    title = "🛠 DEV MODE"
    lines = [vfit(title, width), vfit("─" * width, width)]
    cmd_w = min(14, max(10, width // 2 - 1))
    desc_w = width - cmd_w - 1
    for label, val in rows:
        line = vfit(label, cmd_w) + " " + vfit(val, desc_w)
        lines.append(vfit(line, width))
        if len(lines) >= height:
            break
    while len(lines) < height:
        lines.append(" " * width)
    return lines[:height]


def vljust(s, width):
    """Space-pad string on right so visual width >= width (no truncation)."""
    s = str(s); gap = width - vlen(s)
    return s + ' ' * max(0, gap)

# ==================== CONFIGURATION ====================
SAVES_DIR = "saves"  # directory that holds all named save files
FOG_RADIUS = 12
SPD_DAY = 0.5; SPD_NIGHT = 1.5
HUNGER_IDLE_RATE = 1.0 / 25.0; THIRST_IDLE_RATE = HUNGER_IDLE_RATE * 0.5
import base64 as _b64
# Embedded audio (OGG/Vorbis, base64). Generated from uploaded clips so the game
# needs no external downloads. Decoded at runtime into pygame Sounds.
_CAT_MEOW_OGG_B64 = [
    # cat_d1.ogg
    (
        "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"
        "llqMKbUWQymphVJaK6W0llqqMbVWY8SYlMw5KZljUkoprZVSWqsck5IxKKmDkEopKcVSUouVc1Iy6Kh0EEoqqcRUUmmtpNJSKaXFklJsKcVUW4u1hlJaLKnE"
        "VlJqMbVUW4sx14gxKRlzUjLnpJRSUiultJY5J6WDjkrmoKSSUmulpBQz5qR0DkrKIKNSUootpRJTKKW1klJspaTWWoy1ptRaLSW1VlJqsZQSW4sx1xZLTZ2U"
        "1koqMYZSWmsx5ppaizGUElspKcaSSmytxZpbbDmGUlosqcRWSmqx1ZZja7Hm1FKNKbWaW2y5xpRTj7X2nFqrNbVUY2ux5lhbb7XWnDsprYVSWislxZhai7HF"
        "WHMoJbaSUmylpBhbbLm2FmMPobRYSmqxpBJjazHmGFuOqbVaW2y5ptRirbX2HFtuPaUWa4ux5tJSjTXX3mNNORUAADDgAAAQYEIZKDRkJQAQBQAAGMMYYxAa"
        "pZxzTkqDlHPOScmcgxBCSplzEEJIKXNOQkotZc5BSKm1UEpKrcUWSkmptRYLAAAocAAACLBBU2JxgEJDVgIAUQAAiDFKMQahMUYp5yA0xijFGIRKKcack1Ap"
        "xZhzUDLHnINQSuaccxBKCSGUUkpKIYRSSkmpAACAAgcAgAAbNCUWByg0ZEUAEAUAABhjnDPOIQqdpc5SJKmj1lFrKKUaS4ydxlZ767nTGnttuTeUSo2p1o5r"
        "y7nV3mlNPbccCwAAO3AAADuwEAoNWQkA5AEAEMYoxZhzzhmFGHPOOecMUow555xzijHnnIMQQsWYc85BCCFzzjkIoYSSOecchBBK6JyDUEoppXTOQQihlFI6"
        "5yCEUkopnXMQSimllAIAgAocAAACbBTZnGAkqNCQlQBAHgAAYAxCzklprWHMOQgt1dgwxhyUlGKLnIOQUou5RsxBSCnGoDsoKbUYbPCdhJRaizkHk1KLNefe"
        "g0iptZqDzj3VVnPPvfecYqw1595zLwAAd8EBAOzARpHNCUaCCg1ZCQDkAQAQCCnFmHPOGaUYc8w554xSjDHmnHOKMcacc85BxRhjzjkHIWPMOecghJAx5pxz"
        "EELonHMOQgghdM45ByGEEDrnoIMQQgidcxBCCCGEAgCAChwAAAJsFNmcYCSo0JCVAEA4AAAAIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQggh"
        "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"
        "hjeXKf3O0iTrwH1EpMx+RHlrsMSUflcWEgA="
    ),
    # cat_d2.ogg
    (
        "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"
        "llqMKbUWQymphVJaK6W0llqqMbVWY8SYlMw5KZljUkoprZVSWqsck5IxKKmDkEopKcVSUouVc1Iy6Kh0EEoqqcRUUmmtpNJSKaXFklJsKcVUW4u1hlJaLKnE"
        "VlJqMbVUW4sx14gxKRlzUjLnpJRSUiultJY5J6WDjkrmoKSSUmulpBQz5qR0DkrKIKNSUootpRJTKKW1klJspaTWWoy1ptRaLSW1VlJqsZQSW4sx1xZLTZ2U"
        "1koqMYZSWmsx5ppaizGUElspKcaSSmytxZpbbDmGUlosqcRWSmqx1ZZja7Hm1FKNKbWaW2y5xpRTj7X2nFqrNbVUY2ux5lhbb7XWnDsprYVSWislxZhai7HF"
        "WHMoJbaSUmylpBhbbLm2FmMPobRYSmqxpBJjazHmGFuOqbVaW2y5ptRirbX2HFtuPaUWa4ux5tJSjTXX3mNNORUAADDgAAAQYEIZKDRkJQAQBQAAGMMYYxAa"
        "pZxzTkqDlHPOScmcgxBCSplzEEJIKXNOQkotZc5BSKm1UEpKrcUWSkmptRYLAAAocAAACLBBU2JxgEJDVgIAUQAAiDFKMQahMUYp5yA0xijFGIRKKcack1Ap"
        "xZhzUDLHnINQSuaccxBKCSGUUkpKIYRSSkmpAACAAgcAgAAbNCUWByg0ZEUAEAUAABhjnDPOIQqdpc5SJKmj1lFrKKUaS4ydxlZ767nTGnttuTeUSo2p1o5r"
        "y7nV3mlNPbccCwAAO3AAADuwEAoNWQkA5AEAEMYoxZhzzhmFGHPOOecMUow555xzijHnnIMQQsWYc85BCCFzzjkIoYSSOecchBBK6JyDUEoppXTOQQihlFI6"
        "5yCEUkopnXMQSimllAIAgAocAAACbBTZnGAkqNCQlQBAHgAAYAxCzklprWHMOQgt1dgwxhyUlGKLnIOQUou5RsxBSCnGoDsoKbUYbPCdhJRaizkHk1KLNefe"
        "g0iptZqDzj3VVnPPvfecYqw1595zLwAAd8EBAOzARpHNCUaCCg1ZCQDkAQAQCCnFmHPOGaUYc8w554xSjDHmnHOKMcacc85BxRhjzjkHIWPMOecghJAx5pxz"
        "EELonHMOQgghdM45ByGEEDrnoIMQQgidcxBCCCGEAgCAChwAAAJsFNmcYCSo0JCVAEA4AAAAIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQggh"
        "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"
    ),
    # cat_d3.ogg
    (
        "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"
        "llqMKbUWQymphVJaK6W0llqqMbVWY8SYlMw5KZljUkoprZVSWqsck5IxKKmDkEopKcVSUouVc1Iy6Kh0EEoqqcRUUmmtpNJSKaXFklJsKcVUW4u1hlJaLKnE"
        "VlJqMbVUW4sx14gxKRlzUjLnpJRSUiultJY5J6WDjkrmoKSSUmulpBQz5qR0DkrKIKNSUootpRJTKKW1klJspaTWWoy1ptRaLSW1VlJqsZQSW4sx1xZLTZ2U"
        "1koqMYZSWmsx5ppaizGUElspKcaSSmytxZpbbDmGUlosqcRWSmqx1ZZja7Hm1FKNKbWaW2y5xpRTj7X2nFqrNbVUY2ux5lhbb7XWnDsprYVSWislxZhai7HF"
        "WHMoJbaSUmylpBhbbLm2FmMPobRYSmqxpBJjazHmGFuOqbVaW2y5ptRirbX2HFtuPaUWa4ux5tJSjTXX3mNNORUAADDgAAAQYEIZKDRkJQAQBQAAGMMYYxAa"
        "pZxzTkqDlHPOScmcgxBCSplzEEJIKXNOQkotZc5BSKm1UEpKrcUWSkmptRYLAAAocAAACLBBU2JxgEJDVgIAUQAAiDFKMQahMUYp5yA0xijFGIRKKcack1Ap"
        "xZhzUDLHnINQSuaccxBKCSGUUkpKIYRSSkmpAACAAgcAgAAbNCUWByg0ZEUAEAUAABhjnDPOIQqdpc5SJKmj1lFrKKUaS4ydxlZ767nTGnttuTeUSo2p1o5r"
        "y7nV3mlNPbccCwAAO3AAADuwEAoNWQkA5AEAEMYoxZhzzhmFGHPOOecMUow555xzijHnnIMQQsWYc85BCCFzzjkIoYSSOecchBBK6JyDUEoppXTOQQihlFI6"
        "5yCEUkopnXMQSimllAIAgAocAAACbBTZnGAkqNCQlQBAHgAAYAxCzklprWHMOQgt1dgwxhyUlGKLnIOQUou5RsxBSCnGoDsoKbUYbPCdhJRaizkHk1KLNefe"
        "g0iptZqDzj3VVnPPvfecYqw1595zLwAAd8EBAOzARpHNCUaCCg1ZCQDkAQAQCCnFmHPOGaUYc8w554xSjDHmnHOKMcacc85BxRhjzjkHIWPMOecghJAx5pxz"
        "EELonHMOQgghdM45ByGEEDrnoIMQQgidcxBCCCGEAgCAChwAAAJsFNmcYCSo0JCVAEA4AAAAIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQggh"
        "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"
    ),
    # cat_sg.ogg
    (
        "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"
        "llqMKbUWQymphVJaK6W0llqqMbVWY8SYlMw5KZljUkoprZVSWqsck5IxKKmDkEopKcVSUouVc1Iy6Kh0EEoqqcRUUmmtpNJSKaXFklJsKcVUW4u1hlJaLKnE"
        "VlJqMbVUW4sx14gxKRlzUjLnpJRSUiultJY5J6WDjkrmoKSSUmulpBQz5qR0DkrKIKNSUootpRJTKKW1klJspaTWWoy1ptRaLSW1VlJqsZQSW4sx1xZLTZ2U"
        "1koqMYZSWmsx5ppaizGUElspKcaSSmytxZpbbDmGUlosqcRWSmqx1ZZja7Hm1FKNKbWaW2y5xpRTj7X2nFqrNbVUY2ux5lhbb7XWnDsprYVSWislxZhai7HF"
        "WHMoJbaSUmylpBhbbLm2FmMPobRYSmqxpBJjazHmGFuOqbVaW2y5ptRirbX2HFtuPaUWa4ux5tJSjTXX3mNNORUAADDgAAAQYEIZKDRkJQAQBQAAGMMYYxAa"
        "pZxzTkqDlHPOScmcgxBCSplzEEJIKXNOQkotZc5BSKm1UEpKrcUWSkmptRYLAAAocAAACLBBU2JxgEJDVgIAUQAAiDFKMQahMUYp5yA0xijFGIRKKcack1Ap"
        "xZhzUDLHnINQSuaccxBKCSGUUkpKIYRSSkmpAACAAgcAgAAbNCUWByg0ZEUAEAUAABhjnDPOIQqdpc5SJKmj1lFrKKUaS4ydxlZ767nTGnttuTeUSo2p1o5r"
        "y7nV3mlNPbccCwAAO3AAADuwEAoNWQkA5AEAEMYoxZhzzhmFGHPOOecMUow555xzijHnnIMQQsWYc85BCCFzzjkIoYSSOecchBBK6JyDUEoppXTOQQihlFI6"
        "5yCEUkopnXMQSimllAIAgAocAAACbBTZnGAkqNCQlQBAHgAAYAxCzklprWHMOQgt1dgwxhyUlGKLnIOQUou5RsxBSCnGoDsoKbUYbPCdhJRaizkHk1KLNefe"
        "g0iptZqDzj3VVnPPvfecYqw1595zLwAAd8EBAOzARpHNCUaCCg1ZCQDkAQAQCCnFmHPOGaUYc8w554xSjDHmnHOKMcacc85BxRhjzjkHIWPMOecghJAx5pxz"
        "EELonHMOQgghdM45ByGEEDrnoIMQQgidcxBCCCGEAgCAChwAAAJsFNmcYCSo0JCVAEA4AAAAIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQggh"
        "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"
    ),
    # cat_su.ogg
    (
        "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"
        "llqMKbUWQymphVJaK6W0llqqMbVWY8SYlMw5KZljUkoprZVSWqsck5IxKKmDkEopKcVSUouVc1Iy6Kh0EEoqqcRUUmmtpNJSKaXFklJsKcVUW4u1hlJaLKnE"
        "VlJqMbVUW4sx14gxKRlzUjLnpJRSUiultJY5J6WDjkrmoKSSUmulpBQz5qR0DkrKIKNSUootpRJTKKW1klJspaTWWoy1ptRaLSW1VlJqsZQSW4sx1xZLTZ2U"
        "1koqMYZSWmsx5ppaizGUElspKcaSSmytxZpbbDmGUlosqcRWSmqx1ZZja7Hm1FKNKbWaW2y5xpRTj7X2nFqrNbVUY2ux5lhbb7XWnDsprYVSWislxZhai7HF"
        "WHMoJbaSUmylpBhbbLm2FmMPobRYSmqxpBJjazHmGFuOqbVaW2y5ptRirbX2HFtuPaUWa4ux5tJSjTXX3mNNORUAADDgAAAQYEIZKDRkJQAQBQAAGMMYYxAa"
        "pZxzTkqDlHPOScmcgxBCSplzEEJIKXNOQkotZc5BSKm1UEpKrcUWSkmptRYLAAAocAAACLBBU2JxgEJDVgIAUQAAiDFKMQahMUYp5yA0xijFGIRKKcack1Ap"
        "xZhzUDLHnINQSuaccxBKCSGUUkpKIYRSSkmpAACAAgcAgAAbNCUWByg0ZEUAEAUAABhjnDPOIQqdpc5SJKmj1lFrKKUaS4ydxlZ767nTGnttuTeUSo2p1o5r"
        "y7nV3mlNPbccCwAAO3AAADuwEAoNWQkA5AEAEMYoxZhzzhmFGHPOOecMUow555xzijHnnIMQQsWYc85BCCFzzjkIoYSSOecchBBK6JyDUEoppXTOQQihlFI6"
        "5yCEUkopnXMQSimllAIAgAocAAACbBTZnGAkqNCQlQBAHgAAYAxCzklprWHMOQgt1dgwxhyUlGKLnIOQUou5RsxBSCnGoDsoKbUYbPCdhJRaizkHk1KLNefe"
        "g0iptZqDzj3VVnPPvfecYqw1595zLwAAd8EBAOzARpHNCUaCCg1ZCQDkAQAQCCnFmHPOGaUYc8w554xSjDHmnHOKMcacc85BxRhjzjkHIWPMOecghJAx5pxz"
        "EELonHMOQgghdM45ByGEEDrnoIMQQgidcxBCCCGEAgCAChwAAAJsFNmcYCSo0JCVAEA4AAAAIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQggh"
        "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"
    ),
    # cat_ra.ogg
    (
        "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"
        "llqMKbUWQymphVJaK6W0llqqMbVWY8SYlMw5KZljUkoprZVSWqsck5IxKKmDkEopKcVSUouVc1Iy6Kh0EEoqqcRUUmmtpNJSKaXFklJsKcVUW4u1hlJaLKnE"
        "VlJqMbVUW4sx14gxKRlzUjLnpJRSUiultJY5J6WDjkrmoKSSUmulpBQz5qR0DkrKIKNSUootpRJTKKW1klJspaTWWoy1ptRaLSW1VlJqsZQSW4sx1xZLTZ2U"
        "1koqMYZSWmsx5ppaizGUElspKcaSSmytxZpbbDmGUlosqcRWSmqx1ZZja7Hm1FKNKbWaW2y5xpRTj7X2nFqrNbVUY2ux5lhbb7XWnDsprYVSWislxZhai7HF"
        "WHMoJbaSUmylpBhbbLm2FmMPobRYSmqxpBJjazHmGFuOqbVaW2y5ptRirbX2HFtuPaUWa4ux5tJSjTXX3mNNORUAADDgAAAQYEIZKDRkJQAQBQAAGMMYYxAa"
        "pZxzTkqDlHPOScmcgxBCSplzEEJIKXNOQkotZc5BSKm1UEpKrcUWSkmptRYLAAAocAAACLBBU2JxgEJDVgIAUQAAiDFKMQahMUYp5yA0xijFGIRKKcack1Ap"
        "xZhzUDLHnINQSuaccxBKCSGUUkpKIYRSSkmpAACAAgcAgAAbNCUWByg0ZEUAEAUAABhjnDPOIQqdpc5SJKmj1lFrKKUaS4ydxlZ767nTGnttuTeUSo2p1o5r"
        "y7nV3mlNPbccCwAAO3AAADuwEAoNWQkA5AEAEMYoxZhzzhmFGHPOOecMUow555xzijHnnIMQQsWYc85BCCFzzjkIoYSSOecchBBK6JyDUEoppXTOQQihlFI6"
        "5yCEUkopnXMQSimllAIAgAocAAACbBTZnGAkqNCQlQBAHgAAYAxCzklprWHMOQgt1dgwxhyUlGKLnIOQUou5RsxBSCnGoDsoKbUYbPCdhJRaizkHk1KLNefe"
        "g0iptZqDzj3VVnPPvfecYqw1595zLwAAd8EBAOzARpHNCUaCCg1ZCQDkAQAQCCnFmHPOGaUYc8w554xSjDHmnHOKMcacc85BxRhjzjkHIWPMOecghJAx5pxz"
        "EELonHMOQgghdM45ByGEEDrnoIMQQgidcxBCCCGEAgCAChwAAAJsFNmcYCSo0JCVAEA4AAAAIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQggh"
        "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"
    ),
    # cat_vv.ogg
    (
        "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"
        "llqMKbUWQymphVJaK6W0llqqMbVWY8SYlMw5KZljUkoprZVSWqsck5IxKKmDkEopKcVSUouVc1Iy6Kh0EEoqqcRUUmmtpNJSKaXFklJsKcVUW4u1hlJaLKnE"
        "VlJqMbVUW4sx14gxKRlzUjLnpJRSUiultJY5J6WDjkrmoKSSUmulpBQz5qR0DkrKIKNSUootpRJTKKW1klJspaTWWoy1ptRaLSW1VlJqsZQSW4sx1xZLTZ2U"
        "1koqMYZSWmsx5ppaizGUElspKcaSSmytxZpbbDmGUlosqcRWSmqx1ZZja7Hm1FKNKbWaW2y5xpRTj7X2nFqrNbVUY2ux5lhbb7XWnDsprYVSWislxZhai7HF"
        "WHMoJbaSUmylpBhbbLm2FmMPobRYSmqxpBJjazHmGFuOqbVaW2y5ptRirbX2HFtuPaUWa4ux5tJSjTXX3mNNORUAADDgAAAQYEIZKDRkJQAQBQAAGMMYYxAa"
        "pZxzTkqDlHPOScmcgxBCSplzEEJIKXNOQkotZc5BSKm1UEpKrcUWSkmptRYLAAAocAAACLBBU2JxgEJDVgIAUQAAiDFKMQahMUYp5yA0xijFGIRKKcack1Ap"
        "xZhzUDLHnINQSuaccxBKCSGUUkpKIYRSSkmpAACAAgcAgAAbNCUWByg0ZEUAEAUAABhjnDPOIQqdpc5SJKmj1lFrKKUaS4ydxlZ767nTGnttuTeUSo2p1o5r"
        "y7nV3mlNPbccCwAAO3AAADuwEAoNWQkA5AEAEMYoxZhzzhmFGHPOOecMUow555xzijHnnIMQQsWYc85BCCFzzjkIoYSSOecchBBK6JyDUEoppXTOQQihlFI6"
        "5yCEUkopnXMQSimllAIAgAocAAACbBTZnGAkqNCQlQBAHgAAYAxCzklprWHMOQgt1dgwxhyUlGKLnIOQUou5RsxBSCnGoDsoKbUYbPCdhJRaizkHk1KLNefe"
        "g0iptZqDzj3VVnPPvfecYqw1595zLwAAd8EBAOzARpHNCUaCCg1ZCQDkAQAQCCnFmHPOGaUYc8w554xSjDHmnHOKMcacc85BxRhjzjkHIWPMOecghJAx5pxz"
        "EELonHMOQgghdM45ByGEEDrnoIMQQgidcxBCCCGEAgCAChwAAAJsFNmcYCSo0JCVAEA4AAAAIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQggh"
        "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"
    ),
    # cat_fs.ogg
    (
        "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"
        "llqMKbUWQymphVJaK6W0llqqMbVWY8SYlMw5KZljUkoprZVSWqsck5IxKKmDkEopKcVSUouVc1Iy6Kh0EEoqqcRUUmmtpNJSKaXFklJsKcVUW4u1hlJaLKnE"
        "VlJqMbVUW4sx14gxKRlzUjLnpJRSUiultJY5J6WDjkrmoKSSUmulpBQz5qR0DkrKIKNSUootpRJTKKW1klJspaTWWoy1ptRaLSW1VlJqsZQSW4sx1xZLTZ2U"
        "1koqMYZSWmsx5ppaizGUElspKcaSSmytxZpbbDmGUlosqcRWSmqx1ZZja7Hm1FKNKbWaW2y5xpRTj7X2nFqrNbVUY2ux5lhbb7XWnDsprYVSWislxZhai7HF"
        "WHMoJbaSUmylpBhbbLm2FmMPobRYSmqxpBJjazHmGFuOqbVaW2y5ptRirbX2HFtuPaUWa4ux5tJSjTXX3mNNORUAADDgAAAQYEIZKDRkJQAQBQAAGMMYYxAa"
        "pZxzTkqDlHPOScmcgxBCSplzEEJIKXNOQkotZc5BSKm1UEpKrcUWSkmptRYLAAAocAAACLBBU2JxgEJDVgIAUQAAiDFKMQahMUYp5yA0xijFGIRKKcack1Ap"
        "xZhzUDLHnINQSuaccxBKCSGUUkpKIYRSSkmpAACAAgcAgAAbNCUWByg0ZEUAEAUAABhjnDPOIQqdpc5SJKmj1lFrKKUaS4ydxlZ767nTGnttuTeUSo2p1o5r"
        "y7nV3mlNPbccCwAAO3AAADuwEAoNWQkA5AEAEMYoxZhzzhmFGHPOOecMUow555xzijHnnIMQQsWYc85BCCFzzjkIoYSSOecchBBK6JyDUEoppXTOQQihlFI6"
        "5yCEUkopnXMQSimllAIAgAocAAACbBTZnGAkqNCQlQBAHgAAYAxCzklprWHMOQgt1dgwxhyUlGKLnIOQUou5RsxBSCnGoDsoKbUYbPCdhJRaizkHk1KLNefe"
        "g0iptZqDzj3VVnPPvfecYqw1595zLwAAd8EBAOzARpHNCUaCCg1ZCQDkAQAQCCnFmHPOGaUYc8w554xSjDHmnHOKMcacc85BxRhjzjkHIWPMOecghJAx5pxz"
        "EELonHMOQgghdM45ByGEEDrnoIMQQgidcxBCCCGEAgCAChwAAAJsFNmcYCSo0JCVAEA4AAAAIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQggh"
        "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"
    ),
    # cat_mp.ogg
    (
        "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"
        "llqMKbUWQymphVJaK6W0llqqMbVWY8SYlMw5KZljUkoprZVSWqsck5IxKKmDkEopKcVSUouVc1Iy6Kh0EEoqqcRUUmmtpNJSKaXFklJsKcVUW4u1hlJaLKnE"
        "VlJqMbVUW4sx14gxKRlzUjLnpJRSUiultJY5J6WDjkrmoKSSUmulpBQz5qR0DkrKIKNSUootpRJTKKW1klJspaTWWoy1ptRaLSW1VlJqsZQSW4sx1xZLTZ2U"
        "1koqMYZSWmsx5ppaizGUElspKcaSSmytxZpbbDmGUlosqcRWSmqx1ZZja7Hm1FKNKbWaW2y5xpRTj7X2nFqrNbVUY2ux5lhbb7XWnDsprYVSWislxZhai7HF"
        "WHMoJbaSUmylpBhbbLm2FmMPobRYSmqxpBJjazHmGFuOqbVaW2y5ptRirbX2HFtuPaUWa4ux5tJSjTXX3mNNORUAADDgAAAQYEIZKDRkJQAQBQAAGMMYYxAa"
        "pZxzTkqDlHPOScmcgxBCSplzEEJIKXNOQkotZc5BSKm1UEpKrcUWSkmptRYLAAAocAAACLBBU2JxgEJDVgIAUQAAiDFKMQahMUYp5yA0xijFGIRKKcack1Ap"
        "xZhzUDLHnINQSuaccxBKCSGUUkpKIYRSSkmpAACAAgcAgAAbNCUWByg0ZEUAEAUAABhjnDPOIQqdpc5SJKmj1lFrKKUaS4ydxlZ767nTGnttuTeUSo2p1o5r"
        "y7nV3mlNPbccCwAAO3AAADuwEAoNWQkA5AEAEMYoxZhzzhmFGHPOOecMUow555xzijHnnIMQQsWYc85BCCFzzjkIoYSSOecchBBK6JyDUEoppXTOQQihlFI6"
        "5yCEUkopnXMQSimllAIAgAocAAACbBTZnGAkqNCQlQBAHgAAYAxCzklprWHMOQgt1dgwxhyUlGKLnIOQUou5RsxBSCnGoDsoKbUYbPCdhJRaizkHk1KLNefe"
        "g0iptZqDzj3VVnPPvfecYqw1595zLwAAd8EBAOzARpHNCUaCCg1ZCQDkAQAQCCnFmHPOGaUYc8w554xSjDHmnHOKMcacc85BxRhjzjkHIWPMOecghJAx5pxz"
        "EELonHMOQgghdM45ByGEEDrnoIMQQgidcxBCCCGEAgCAChwAAAJsFNmcYCSo0JCVAEA4AAAAIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQggh"
        "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"
        "4gA="
    ),
]
_GOD_VOICE_OGG_B64 = None  # loaded from assets/audiomass-output_1785068794813.ogg

_AMBIENT_BGM_OGG_B64 = None  # loaded from assets/hayden-folker-adrift-_1_.ogg
_EMBEDDED_OGG_B64 = {}  # audio loaded from assets/ folder

SOUND_SAMPLE_RATE = 48000
SOUND_BUFFER_SIZE = 1024
LOW_HEALTH_BEEP_SECONDS = 6.0

class SoundManager:
    """Minimal optional audio layer using pygame for in-game sound effects."""
    def __init__(self):
        self.enabled = False
        self.last_low_health = 0.0
        self.bgm_channel = None
        self.ambient_channel = None
        self.craft_channel = None
        self.eat_channel = None
        self.inspect_channel = None
        self.gather_channel = None
        self.combat_bgm_channel = None
        self.last_biome = None
        self.in_combat_bgm = False
        self._last_craft_station = None
        self.sounds = {}
        self.cat_meow_sounds = []
        if not pygame or not PYGAME_AVAILABLE:
            return

        # Cross-platform driver sequence (SDL2 auto-selects if driver=None)
        import sys as _sys2
        _plat2 = _sys2.platform
        if _plat2 == "linux":
            driver_sequence = [None, "pulseaudio", "alsa", "oss", "dsp", "jack", "dummy"]
        elif _plat2 == "darwin":
            driver_sequence = [None, "coreaudio", "dummy"]
        else:  # Windows and others
            driver_sequence = [None, "directsound", "dummy"]

        # Initialise the base pygame library once (safe to call multiple times)
        try:
            pygame.init()
        except Exception:
            pass

        self._init_error = None
        for driver in driver_sequence:
            try:
                if driver:
                    os.environ["SDL_AUDIODRIVER"] = driver
                elif "SDL_AUDIODRIVER" in os.environ:
                    del os.environ["SDL_AUDIODRIVER"]   # let SDL auto-pick
                if pygame.mixer.get_init():
                    pygame.mixer.quit()
                pygame.mixer.init(SOUND_SAMPLE_RATE, -16, 2, SOUND_BUFFER_SIZE)
                pygame.mixer.set_num_channels(16)
                pygame.mixer.set_reserved(7)
                self.bgm_channel = pygame.mixer.Channel(0)
                self.ambient_channel = pygame.mixer.Channel(1)
                self.craft_channel = pygame.mixer.Channel(2)
                self.eat_channel = pygame.mixer.Channel(3)
                self.inspect_channel = pygame.mixer.Channel(4)
                self.gather_channel = pygame.mixer.Channel(5)
                self.combat_bgm_channel = pygame.mixer.Channel(6)
                self.enabled = True
                self._load_sounds()
                self._load_cat_meows()
                break
            except Exception as _e:
                self._init_error = str(_e)
                continue

    def _make_sound(self, samples):
        if not self.enabled:
            return None
        try:
            return pygame.mixer.Sound(buffer=array('h', samples))
        except Exception:
            return None

    def _envelope(self, t, duration):
        if t < 0.05:
            return t / 0.05
        if t > duration - 0.05:
            return max(0.0, (duration - t) / 0.05)
        return 1.0

    def _tone(self, freq, duration, volume=0.20, shape="sine", detune=0.0):
        samples = []
        for i in range(int(SOUND_SAMPLE_RATE * duration)):
            t = i / SOUND_SAMPLE_RATE
            if shape == "triangle":
                cycle = (t * freq) % 1.0
                value = 2.0 * abs(2.0 * cycle - 1.0) - 1.0
            elif shape == "square":
                value = 1.0 if math.sin(2.0 * math.pi * freq * t) >= 0 else -1.0
            else:
                value = math.sin(2.0 * math.pi * freq * t)
            if detune:
                value += 0.3 * math.sin(2.0 * math.pi * (freq + detune) * t)
            env = self._envelope(t, duration)
            samples.append(int(max(-1.0, min(1.0, value * volume * env)) * 32767))
        return self._make_sound(samples)

    def _noise(self, duration, volume=0.16, tone_freq=0.0):
        samples = []
        noise_val = 0.0
        for i in range(int(SOUND_SAMPLE_RATE * duration)):
            t = i / SOUND_SAMPLE_RATE
            noise_val = noise_val * 0.96 + (random.random() * 2.0 - 1.0) * 0.08
            value = noise_val
            if tone_freq:
                value += 0.2 * math.sin(2.0 * math.pi * tone_freq * t)
            env = self._envelope(t, duration)
            samples.append(int(max(-1.0, min(1.0, value * volume * env)) * 32767))
        return self._make_sound(samples)

    def _sequence(self, notes, durations, volume=0.18, shape="sine"):
        samples = []
        for freq, dur in zip(notes, durations):
            for i in range(int(SOUND_SAMPLE_RATE * dur)):
                t = i / SOUND_SAMPLE_RATE
                if shape == "triangle":
                    cycle = (t * freq) % 1.0
                    value = 2.0 * abs(2.0 * cycle - 1.0) - 1.0
                elif shape == "square":
                    value = 1.0 if math.sin(2.0 * math.pi * freq * t) >= 0 else -1.0
                else:
                    value = math.sin(2.0 * math.pi * freq * t)
                env = self._envelope(t, dur)
                samples.append(int(max(-1.0, min(1.0, value * volume * env)) * 32767))
        return self._make_sound(samples)

    def _load_sounds(self):
        SR = SOUND_SAMPLE_RATE

        # ── raw generators (return sample lists for mixing) ──────────────────
        def rt(freq, dur, vol=0.14, shape="sine", detune=0.0):
            out = []
            for i in range(int(SR * dur)):
                t = i / SR
                if shape == "triangle":
                    cyc = (t * freq) % 1.0; v = 2.0 * abs(2.0 * cyc - 1.0) - 1.0
                elif shape == "square":
                    v = 1.0 if math.sin(2*math.pi*freq*t) >= 0 else -1.0
                else:
                    v = math.sin(2*math.pi*freq*t)
                if detune: v += 0.3 * math.sin(2*math.pi*(freq+detune)*t)
                out.append(int(max(-1, min(1, v*vol*self._envelope(t, dur))) * 32767))
            return out

        def rn(dur, vol=0.12, tone=0.0):
            out = []; nv = 0.0
            for i in range(int(SR * dur)):
                t = i / SR
                nv = nv*0.96 + (random.random()*2-1)*0.08
                v = nv + (0.2*math.sin(2*math.pi*tone*t) if tone else 0)
                out.append(int(max(-1, min(1, v*vol*self._envelope(t, dur))) * 32767))
            return out

        def rs(notes, durs, vol=0.14, shape="sine"):
            out = []
            for freq, d in zip(notes, durs): out.extend(rt(freq, d, vol, shape))
            return out

        def mx(*streams):
            n = max(len(s) for s in streams)
            return [int(max(-32767, min(32767, sum(s[i] if i < len(s) else 0 for s in streams)))) for i in range(n)]

        def mk(samples): return self._make_sound(samples)

        # ── Forest BGM: slow, low, peaceful — all notes ≤ 262 Hz, no high shriek ─
        mel_n = [196,220,247,220,196,175,196,220,247,220,196,175,220,247,220,196]
        mel_d = [1.05,1.05,1.05,1.50,1.05,1.56,1.05,1.05,1.05,1.05,1.50,1.56,1.05,1.05,1.05,2.0]
        b_total = sum(mel_d)
        bas_n = [87, 98, 87, 110, 87, 98, 110, 87]
        bas_d = [b_total/8]*8
        self.sounds["forest"] = mk(mx(rs(mel_n, mel_d, vol=0.13), rs(bas_n, bas_d, vol=0.065, shape="triangle")))

        # ── Arctic BGM: very slow, low, sparse — all notes ≤ 247 Hz ─────────────
        arc_n = [175,196,220,196,175,165,175,196]
        arc_d = [1.82,1.40,2.10,1.40,1.82,2.34,1.56,1.82]
        a_total = sum(arc_d)
        drn_n = [82,82,82,82]; drn_d = [a_total/4]*4
        self.sounds["arctic"] = mk(mx(rs(arc_n, arc_d, vol=0.11), rs(drn_n, drn_d, vol=0.055, shape="triangle")))

        # ── Intro jingle ─────────────────────────────────────────────────────
        self.sounds["intro"] = mk(rs([330,392,440,523,440,523,659,784],[0.12,0.10,0.10,0.14,0.10,0.10,0.12,0.35], vol=0.15))

        # ── Collect: resonant ding (louder, richer) ──────────────────────────
        self.sounds["collect"] = mk(mx(rt(880,0.55,vol=0.32), rt(1320,0.42,vol=0.14), rt(660,0.22,vol=0.10)))

        # ── Inspect: loopable vibrato hum (1.6 s, flat amplitude for seamless loop)
        hmm_dur = 1.6; hmm = []
        for i in range(int(SR * hmm_dur)):
            t = i / SR
            lfo = 6.0 * math.sin(2*math.pi*4.2*t)
            v  = math.sin(2*math.pi*(210+lfo)*t) * 0.28
            v += math.sin(2*math.pi*(420+lfo*0.5)*t) * 0.10
            v += math.sin(2*math.pi*(105+lfo*0.25)*t) * 0.06
            hmm.append(int(max(-32767, min(32767, v * 32767))))
        self.sounds["inspect"] = mk(hmm)

        # ── Quest complete: "tido-LING!" fanfare — louder, longer ────────────
        setup = rs([330,392,494,659,784],[0.12,0.10,0.10,0.12,0.15], vol=0.38)
        bell  = mx(rt(1047,1.20,vol=0.42), rt(1568,0.90,vol=0.18))
        self.sounds["quest_complete"] = mk(setup + bell)

        # ── Eat: wet "chomp, chomp" chews — squishy low thuds, no beeps ───────────
        eat = []
        for ci in range(3):
            # Each chomp: a downward-pitched squishy bite (jaw closing) made of
            # filtered noise + a low body thump, NOT pure sine beeps.
            chomp = 0.16
            n = int(SR * chomp)
            nv_e = 0.0
            for i in range(n):
                t = i / SR
                prog = t / chomp
                # low body of the chomp drops in pitch as the jaw closes
                body_f = 150 - 70 * prog
                # heavily smoothed noise = wet/squishy mouth texture
                nv_e = nv_e * 0.90 + (random.random() * 2 - 1) * 0.10
                v  = nv_e * 0.85
                v += math.sin(2 * math.pi * body_f * t) * 0.45
                v += math.sin(2 * math.pi * (body_f * 0.5) * t) * 0.20
                v = max(-1.0, min(1.0, v))
                # quick attack, soft decay → "chomp"
                env = (prog / 0.12) if prog < 0.12 else (1.0 - (prog - 0.12) / 0.88)
                eat.append(int(v * env * 0.9 * 32767))
            eat.extend([0] * int(SR * 0.18))   # clear gap between chomps
        self.sounds["eat"] = mk(eat)


        # ── Chop: woody axe thwack — longer, louder ───────────────────────────────
        self.sounds["chop"] = mk(mx(rn(0.48, vol=0.82, tone=108), rt(78, 0.52, vol=0.56, shape="triangle")))

        # ── Pickaxe: metallic ring — longer, louder, bright ───────────────────
        self.sounds["pickaxe"] = mk(mx(
            rt(1600, 0.55, vol=0.38),
            rt(800,  0.45, vol=0.28),
            rt(3200, 0.28, vol=0.14),
            rn(0.06, vol=0.22, tone=2000),
        ))

        # ── Combat strike: BOTW swoosh + impact ──────────────────────────────
        swp = []; ph = 0.0; swp_dur = 0.13
        for i in range(int(SR*swp_dur)):
            t = i/SR; freq = 700*(1-t/swp_dur)+100*(t/swp_dur); ph += 2*math.pi*freq/SR
            swp.append(int(max(-32767, min(32767, math.sin(ph)*0.17*self._envelope(t,swp_dur)*32767))))
        imp = rn(0.14, vol=0.20, tone=80)
        self.sounds["attack"] = mk(mx(swp+[0]*len(imp), [0]*len(swp)+imp))

        # ── Spear throw: BOTW-style — dramatic sweep + deep thump ────────────────
        # Layer 1: long high-to-low pitch sweep (the "shhhoom")
        wsh = []; ph2 = 0.0; wsh_dur = 0.55
        for i in range(int(SR * wsh_dur)):
            t = i / SR
            prog = t / wsh_dur
            freq2 = 1100 * (1 - prog) ** 1.6 + 75  # steep pitch drop
            ph2 += 2 * math.pi * freq2 / SR
            env2 = self._envelope(t, wsh_dur) * (1.0 - prog * 0.4)  # slight vol taper
            wsh.append(int(max(-32767, min(32767, math.sin(ph2) * 0.46 * env2 * 32767))))
        # Layer 2: bright air-friction noise riding the sweep
        air = []
        for i in range(int(SR * wsh_dur)):
            t = i / SR
            nva = (random.random() * 2 - 1)
            env_a = self._envelope(t, wsh_dur) * (1.0 - t / wsh_dur)
            air.append(int(max(-32767, min(32767, nva * 0.22 * env_a * 32767))))
        # Layer 3: deep thump impact at the end
        thump_len = int(SR * 0.18)
        thump = []
        for i in range(thump_len):
            t = i / SR
            v = math.sin(2 * math.pi * 62 * t) * 0.55 + (random.random() * 2 - 1) * 0.20
            thump.append(int(max(-32767, min(32767, v * self._envelope(t, 0.18) * 32767))))
        gap = [0] * int(SR * 0.38)  # thump starts ~0.38s in (near end of sweep)
        self.sounds["spear_throw"] = mk(mx(wsh + [0]*thump_len,
                                           air + [0]*thump_len,
                                           gap + thump))

        # ── Walk: louder footstep swish ──────────────────────────────────────
        self.sounds["walk"] = mk(mx(rn(0.075, vol=0.30, tone=320),
                                    rt(70, 0.08, vol=0.22, shape="triangle")))

        # ── Low health: single clean lub-dub heartbeat (~0.45 s) ─────────────
        # "lub" — stronger first beat
        lh1 = []
        for i in range(int(SR * 0.10)):
            t = i / SR
            v = math.sin(2 * math.pi * 68 * t) * 0.72
            v += math.sin(2 * math.pi * 36 * t) * 0.22
            v += (random.random() * 2 - 1) * 0.08
            lh1.append(int(max(-32767, min(32767, v * self._envelope(t, 0.10) * 32767))))
        # gap between lub and dub
        lh_mid = [0] * int(SR * 0.09)
        # "dub" — softer second beat
        lh2 = []
        for i in range(int(SR * 0.08)):
            t = i / SR
            v = math.sin(2 * math.pi * 58 * t) * 0.44
            v += math.sin(2 * math.pi * 30 * t) * 0.14
            lh2.append(int(max(-32767, min(32767, v * self._envelope(t, 0.08) * 32767))))
        self.sounds["low_health"] = mk(lh1 + lh_mid + lh2)

        # ── Damage taken — three tiers ────────────────────────────────────────
        def _make_dmg(thump_hz, thump_vol, thump_dur, crack_vol, dub_hz, dub_vol, tail_dur):
            d = []
            # Big thump
            for i in range(int(SR * thump_dur)):
                t = i / SR
                v = math.sin(2*math.pi*thump_hz*t)*thump_vol + (random.random()*2-1)*0.10
                d.append(int(max(-32767, min(32767, v*self._envelope(t, thump_dur)*32767))))
            d.extend([0]*int(SR*0.03))
            # Crack/stutter
            for i in range(int(SR*0.04)):
                t = i/SR
                v = (random.random()*2-1)*crack_vol
                d.append(int(max(-32767, min(32767, v*self._envelope(t,0.04)*32767))))
            d.extend([0]*int(SR*0.055))
            # Weak dub
            for i in range(int(SR*0.09)):
                t = i/SR
                v = math.sin(2*math.pi*dub_hz*t)*dub_vol
                d.append(int(max(-32767, min(32767, v*self._envelope(t,0.09)*32767))))
            d.extend([0]*int(SR*0.04))
            # Crackle tail
            for i in range(int(SR*tail_dur)):
                t = i/SR
                fade = 1.0 - t/tail_dur
                d.append(int(max(-32767, min(32767, (random.random()*2-1)*0.45*fade*32767))))
            return d

        # Light (< 8 HP): higher-pitched, short, quiet
        self.sounds["damage_light"] = mk(_make_dmg(90, 0.45, 0.07, 0.40, 72, 0.28, 0.07))
        # Medium (8–20 HP): the classic broken heartbeat
        self.sounds["damage_medium"] = mk(_make_dmg(70, 0.78, 0.10, 0.72, 55, 0.45, 0.12))
        # Heavy (> 20 HP): lower, longer, louder, more crackle
        self.sounds["damage_heavy"] = mk(_make_dmg(52, 0.92, 0.14, 0.88, 40, 0.60, 0.22))

        # ── Death ─────────────────────────────────────────────────────────────
        self.sounds["death"] = mk(rs([110,82,65],[0.22,0.28,0.40], vol=0.18, shape="triangle"))

        # ── Storm ─────────────────────────────────────────────────────────────
        self.sounds["lightning"] = mk(rn(0.18, vol=0.22, tone=80))
        self.sounds["tornado"]   = mk(rn(0.70, vol=0.10, tone=120))
        self.sounds["animal"]    = mk(rs([660,520],[0.10,0.14], vol=0.12))

        # ── Gather all: sweeping multi-collect whoosh + ding ──────────────────
        ga_swp = []; ga_ph = 0.0; ga_dur = 0.30
        for i in range(int(SR * ga_dur)):
            t = i / SR; freq = 300 + 500 * (t / ga_dur)
            ga_ph += 2 * math.pi * freq / SR
            ga_swp.append(int(max(-32767, min(32767, math.sin(ga_ph) * 0.28 * self._envelope(t, ga_dur) * 32767))))
        ga_ding = mx(rt(880, 0.55, vol=0.38), rt(1100, 0.35, vol=0.15))
        self.sounds["gather_all"] = mk(ga_swp + [0] * int(SR * 0.05) + ga_ding)

        # ── Craft woodworking station: slow, spaced-out hammer strikes ──────────
        hw = []
        for _ in range(3):
            hit_dur = 0.11
            nv3 = 0.0
            for i in range(int(SR * hit_dur)):
                t = i / SR; nv3 = nv3 * 0.84 + (random.random() * 2 - 1) * 0.30
                v = nv3 + 0.38 * math.sin(2 * math.pi * 140 * t)
                hw.append(int(max(-32767, min(32767, v * 0.72 * self._envelope(t, hit_dur) * 32767))))
            hw.extend([0] * int(SR * 0.85))   # much longer pause between hits (slower, less frequent)
        self.sounds["craft_woodworking"] = mk(hw)

        # ── Craft furnace: loopable sizzle (2.0 s, flat envelope for seamless loop)
        siz = []
        dur_siz = 2.0
        for i in range(int(SR * dur_siz)):
            t = i / SR
            nv4 = random.random() * 2 - 1
            lfo = 0.55 + 0.45 * math.sin(2 * math.pi * 3.2 * t)
            siz.append(int(max(-32767, min(32767, nv4 * 0.42 * lfo * 32767))))
        self.sounds["craft_furnace"] = mk(siz)

        # ── Craft smelter: loopable bubbling (2.0 s, flat envelope) ──────────────
        smelt = []
        dur_sm = 2.0
        for i in range(int(SR * dur_sm)):
            t = i / SR
            nv5 = random.random() * 2 - 1
            bub = 0.45 + 0.55 * abs(math.sin(2 * math.pi * 1.8 * t))
            # Louder bubbling sound for the smelter craft effect.
            smelt.append(int(max(-32767, min(32767, nv5 * 0.80 * bub * 32767))))
        self.sounds["craft_smelter"] = mk(smelt)

        # ── Craft water filter: loopable drip pattern (2.0 s) ─────────────────────
        drp = []
        for _ in range(10):
            drp_len = int(SR * 0.09)
            for i in range(drp_len):
                t = i / SR
                v = math.sin(2 * math.pi * 480 * t) * 0.40 + math.sin(2 * math.pi * 680 * t) * 0.16
                drp.append(int(max(-32767, min(32767, v * self._envelope(t, 0.09) * 32767))))
            drp.extend([0] * int(SR * 0.17))
        self.sounds["craft_water_filter"] = mk(drp)

        # ── Craft generic: loopable soft mechanical whir (1.5 s) ──────────────────
        gen = []
        dur_gen = 1.5
        for i in range(int(SR * dur_gen)):
            t = i / SR
            lfo2 = 0.7 + 0.3 * math.sin(2 * math.pi * 5.0 * t)
            v = math.sin(2 * math.pi * 120 * t) * 0.22 * lfo2
            v += (random.random() * 2 - 1) * 0.08
            gen.append(int(max(-32767, min(32767, v * 32767))))
        self.sounds["craft_generic"] = mk(gen)

        # ── Cat meow: "mee-ow" — higher, brighter, two-phase pitch (not a horse) ──
        mw_dur = 0.70; mw = []
        for i in range(int(SR * mw_dur)):
            t = i / SR
            prog = t / mw_dur
            # Pitch contour: quick rise (the "mee") then a longer glide down (the "ow").
            if prog < 0.30:
                freq = 620 + 360 * (prog / 0.30)        # 620 → 980 Hz
            else:
                freq = 980 - 560 * ((prog - 0.30) / 0.70)  # 980 → 420 Hz
            # Gentle vibrato adds the lively feline quality

            vibrato = 12 * math.sin(2 * math.pi * 7.0 * t)
            f = freq + vibrato
            # Rich but bright harmonic stack (cats have strong upper partials)
            v  = math.sin(2 * math.pi * f * t) * 0.50
            v += math.sin(2 * math.pi * 2 * f * t) * 0.30
            v += math.sin(2 * math.pi * 3 * f * t) * 0.16
            v += math.sin(2 * math.pi * 4 * f * t) * 0.08
            # Vowel shift "ee"→"ow": fade upper partials toward the end (handled by mix above)
            v += (random.random() * 2 - 1) * 0.04        # tiny breathiness
            # Envelope: fast attack, sustained, soft tail
            if prog < 0.10:
                env = prog / 0.10
            elif prog > 0.75:
                env = max(0.0, (1.0 - prog) / 0.25)
            else:
                env = 1.0
            mw.append(int(max(-32767, min(32767, v * env * 0.60 * 32767))))
        self.sounds["cat_meow"] = mk(mw)

        # ── Squirrel: rapid gnawing clicks ────────────────────────────────────
        sq = []
        for _ in range(10):
            nv6 = 0.0
            for i in range(int(SR * 0.028)):
                t = i / SR; nv6 = nv6 * 0.80 + (random.random() * 2 - 1) * 0.28
                sq.append(int(max(-32767, min(32767, nv6 * 0.38 * self._envelope(t, 0.028) * 32767))))
            sq.extend([0] * int(SR * random.uniform(0.025, 0.06)))
        self.sounds["squirrel"] = mk(sq)

        # ── Deer: soft low grazing/leaf crunch ────────────────────────────────
        dr_s = []
        for _ in range(3):
            nv7 = 0.0
            for i in range(int(SR * 0.18)):
                t = i / SR; nv7 = nv7 * 0.97 + (random.random() * 2 - 1) * 0.04
                dr_s.append(int(max(-32767, min(32767, (nv7 + 0.08 * math.sin(2*math.pi*55*t)) * 0.35 * self._envelope(t, 0.18) * 32767))))
            dr_s.extend([0] * int(SR * random.uniform(0.20, 0.40)))
        self.sounds["deer"] = mk(dr_s)

        # ── New quest: "tido-LING!" — quick rise + bright bell ────────────────
        nq_rise = rs([300, 440, 590], [0.06, 0.06, 0.08], vol=0.44, shape="sine")
        nq_bell = mx(rt(1320, 0.85, vol=0.46), rt(1760, 0.60, vol=0.20), rt(880, 0.70, vol=0.16))
        self.sounds["new_quest"] = mk(nq_rise + [0]*int(SR*0.04) + nq_bell)

        # ── Buy: descending coin tinks — coins leaving (negative feel) ────────
        buy_s = []
        for pitch in [1400, 1050, 750]:
            buy_s += mx(rt(pitch, 0.13, vol=0.38), rt(int(pitch*1.5), 0.09, vol=0.14))
            buy_s += [0] * int(SR * 0.075)
        self.sounds["buy"] = mk(buy_s)

        # ── Sell: ascending coin tinks — coins arriving (positive feel) ───────
        sell_s = []
        for pitch in [650, 900, 1200, 1600]:
            sell_s += mx(rt(pitch, 0.12, vol=0.34), rt(int(pitch*1.5), 0.08, vol=0.12))
            sell_s += [0] * int(SR * 0.065)
        self.sounds["sell"] = mk(sell_s)

        # ── Drink water: two swallow gulps ────────────────────────────────────
        drk = []
        for gulp_freq, gulp_dur in [(155, 0.28), (140, 0.22)]:
            for i in range(int(SR * gulp_dur)):
                t = i / SR
                lfo = 0.45 + 0.55 * abs(math.sin(2 * math.pi * 8.5 * t))
                nv = (random.random() * 2 - 1) * 0.30 * lfo
                v = nv + math.sin(2 * math.pi * gulp_freq * t) * 0.14 * lfo
                drk.append(int(max(-32767, min(32767, v * self._envelope(t, gulp_dur) * 32767))))
            drk += [0] * int(SR * 0.14)
        self.sounds["drink"] = mk(drk)

        # ── Tool break: hard crack + crumble ──────────────────────────────────
        tb = []
        for i in range(int(SR * 0.07)):
            t = i / SR
            v = (random.random() * 2 - 1) * 0.92
            tb.append(int(max(-32767, min(32767, v * self._envelope(t, 0.07) * 32767))))
        for i in range(int(SR * 0.22)):
            t = i / SR
            fade = (1.0 - t / 0.22) ** 2.0
            tb.append(int(max(-32767, min(32767, (random.random()*2-1) * 0.50 * fade * 32767))))
        self.sounds["tool_break"] = mk(tb)

        # ── Gather loop: slow, sparse soft thumps while gather-all runs ──────────
        ga_loop = []
        for _ in range(2):
            hit_d = 0.09
            for i in range(int(SR * hit_d)):
                t = i / SR
                nv = (random.random() * 2 - 1) * 0.30
                v = nv + math.sin(2 * math.pi * 200 * t) * 0.18
                ga_loop.append(int(max(-32767, min(32767, v * self._envelope(t, hit_d) * 32767))))
            ga_loop.extend([0] * int(SR * 0.80))   # much longer gap → less frequent, slower
        self.sounds["gather_loop"] = mk(ga_loop)

        # ── Gather loop (wood): spaced-out axe chops, like single-chopping ──────
        ga_wood = []
        for _ in range(2):
            chop_one = mx(rn(0.40, vol=0.78, tone=108), rt(78, 0.46, vol=0.52, shape="triangle"))
            ga_wood.extend(chop_one)
            ga_wood.extend([0] * int(SR * 0.55))   # gap between chops
        self.sounds["gather_loop_wood"] = mk(ga_wood)


        # ── Combat BGM: loaded from assets/music_combat_bgm.ogg ────
        self.sounds["combat_bgm"] = None  # lazy-loaded by _ensure_combat_bgm()

    def _play(self, sound_name, loops=0, channel=None):
        if not self.enabled:
            return
        sound = self.sounds.get(sound_name)
        if not sound:
            return
        try:
            if channel is None:
                channel = pygame.mixer.find_channel(True)
            if channel:
                try:
                    channel.set_volume(1.0)
                except Exception:
                    pass
            channel.play(sound, loops=loops)
        except Exception:
            pass

    def duck_volume(self, level=0.12):
        """Lower all sound volumes (called when paused)."""
        if not self.enabled: return
        try:
            for s in self.sounds.values():
                if s: s.set_volume(level)
        except Exception: pass

    def restore_volume(self):
        """Restore full sound volumes (called when unpaused)."""
        if not self.enabled: return
        try:
            for s in self.sounds.values():
                if s: s.set_volume(1.0)
        except Exception: pass

    def play_intro(self):
        if self.enabled:
            self._play("intro")
            self.start_ambient_bgm()

    def play_environment(self, biome):
        # The biome ambience loops were replaced by the single ambient music
        # track ("Adrift"), so only one piece of music ever plays at a time.
        if not self.enabled:
            return
        self.last_biome = biome
        try:
            if self.ambient_channel:
                self.ambient_channel.stop()
        except Exception:
            pass
        self.start_ambient_bgm()

    def play_walk(self):        self._play("walk")
    def play_collect(self):     self._play("collect")
    def play_chop(self):        self._play("chop")
    def play_pickaxe(self):     self._play("pickaxe")
    def play_attack(self):      self._play("attack")
    def play_spear_throw(self): self._play("spear_throw")
    def play_inspect(self):
        if not self.enabled: return
        snd = self.sounds.get("inspect")
        if not snd: return
        try:
            ch = self.inspect_channel or pygame.mixer.find_channel(True)
            ch.play(snd, loops=-1)
        except Exception: pass

    def stop_inspect(self):
        if not self.enabled: return
        try:
            if self.inspect_channel: self.inspect_channel.stop()
        except Exception: pass
    def play_eat(self):         self._play("eat")
    def play_drink(self):       self._play("drink")
    def play_new_quest(self):   self._play("new_quest")
    def play_buy(self):         self._play("buy")
    def play_sell(self):        self._play("sell")
    def play_tool_break(self):  self._play("tool_break")
    def play_quest_complete(self): self._play("quest_complete")
    def play_gather_all(self):  self._play("gather_all")
    def play_animal(self):      self._play("animal")
    def play_lightning(self):   self._play("lightning")
    def play_tornado(self):     self._play("tornado")
    def play_low_health(self):  self._play("low_health")
    def play_damage(self, amount=0):
        if amount < 8:
            self._play("damage_light")
        elif amount <= 20:
            self._play("damage_medium")
        else:
            self._play("damage_heavy")
    def play_death(self):       self._play("death")
    @staticmethod
    def _asset_sound(filename):
        """Load an OGG/WAV from the assets/ folder next to 9planets.py.
        Returns a pygame.mixer.Sound on success, or None if the file is missing."""
        import pathlib
        path = pathlib.Path(__file__).parent / "assets" / filename
        if not path.exists():
            return None
        try:
            return pygame.mixer.Sound(str(path))
        except Exception:
            return None

    def _load_cat_meows(self):
        """Load cat-meow recordings (still embedded) plus the crafting /
        death sounds from the assets/ folder."""
        self.cat_meow_sounds = []
        if not self.enabled:
            return
        for data in _CAT_MEOW_OGG_B64:
            try:
                raw = _b64.b64decode(data)
                snd = pygame.mixer.Sound(io.BytesIO(raw))
                self.cat_meow_sounds.append(snd)
            except Exception:
                pass
        asset_map = {
            "music_death.ogg":      "death",
            "music_cook_start.ogg": "craft_cook_start",
            "music_cook_body.ogg":  "craft_furnace",
            "music_cook_end.ogg":   "craft_cook_end",
            "music_smelter.ogg":    "craft_smelter",
            "music_sewing.ogg":     "craft_sewing_station",
        }
        for filename, sname in asset_map.items():
            snd = self._asset_sound(filename)
            if snd:
                self.sounds[sname] = snd
        try:
            self._load_god_voice()
        except Exception:
            self.god_voice = None

    def _load_god_voice(self):
        """Load the god-voice clip from assets/."""
        self.god_voice = None
        if not self.enabled:
            return
        self.god_voice = self._asset_sound("audiomass-output_1785068794813.ogg")

    def play_god_voice(self):
        if not self.enabled:
            return
        if getattr(self, "god_voice", None) is None:
            self._load_god_voice()
        snd = getattr(self, "god_voice", None)
        if snd is None:
            return
        try:
            snd.set_volume(1.0)
        except Exception:
            pass
        # Try a plain Sound.play() first (allocates its own channel); fall back
        # to force-stealing a channel if every channel is busy.
        try:
            if snd.play() is not None:
                return
        except Exception:
            pass
        try:
            ch = pygame.mixer.find_channel(True)
            if ch:
                ch.play(snd)
        except Exception:
            pass

    def play_cat_meow(self):
        # Prefer the real embedded cat recordings (randomly chosen); fall back
        # to the synthesized meow if decoding failed / pygame lacks OGG support.
        if self.enabled and self.cat_meow_sounds:
            try:
                snd = random.choice(self.cat_meow_sounds)
                ch = pygame.mixer.find_channel(True)
                if ch:
                    ch.play(snd)
                    return
            except Exception:
                pass
        self._play("cat_meow")
    def play_squirrel(self):    self._play("squirrel")
    def play_deer(self):        self._play("deer")

    def play_craft(self, station):
        """Legacy one-shot craft sound — delegates to loop_craft."""
        self.loop_craft(station)

    def loop_craft(self, station):
        """Start looping the appropriate craft sound on the dedicated craft channel.
        For the furnace (cooking) we play a 'placing pan' intro one-shot, then
        loop the sizzling body; stop_craft plays the stove 'end' clip."""
        if not self.enabled:
            return
        mapping = {
            "woodworking_station": "craft_woodworking",
            "furnace":             "craft_furnace",
            "smelter":             "craft_smelter",
            "water_filter":        "craft_water_filter",
            "sewing_station":      "craft_sewing_station",
        }
        self._last_craft_station = station
        name = mapping.get(station, "craft_generic") if station else "craft_generic"
        snd = self.sounds.get(name)
        if not snd:
            return
        try:
            ch = self.craft_channel or pygame.mixer.find_channel(True)
            if not ch:
                return
            self.craft_channel = ch
            # Cooking: play the 'placing pan on stove' intro first (one-shot on a
            # free channel), then loop the sizzling body on the craft channel.
            if station == "furnace":
                intro = self.sounds.get("craft_cook_start")
                if intro:
                    try:
                        ich = pygame.mixer.find_channel(True)
                        if ich: ich.play(intro)
                    except Exception:
                        pass
            ch.play(snd, loops=-1)
        except Exception:
            pass

    def stop_craft(self):
        """Stop the looping craft sound (and play the cooking 'end' clip)."""
        if not self.enabled:
            return
        try:
            if self.craft_channel:
                self.craft_channel.stop()
                self.craft_channel = None
            if getattr(self, "_last_craft_station", None) == "furnace":
                endsnd = self.sounds.get("craft_cook_end")
                if endsnd:
                    ech = pygame.mixer.find_channel(True)
                    if ech: ech.play(endsnd)
            self._last_craft_station = None
        except Exception:
            pass

    def loop_gather(self, item=None):
        """Start looping the gather ambient sound on its dedicated channel.
        For wood, use the axe-chop variant so gather-all sounds like chopping."""
        if not self.enabled: return
        name = "gather_loop_wood" if item == "wood" else "gather_loop"
        snd = self.sounds.get(name) or self.sounds.get("gather_loop")
        if not snd: return
        try:
            ch = self.gather_channel or pygame.mixer.find_channel(True)
            ch.play(snd, loops=-1)
        except Exception: pass

    def stop_gather(self):
        """Stop the looping gather ambient sound."""
        if not self.enabled: return
        try:
            if self.gather_channel: self.gather_channel.stop()
        except Exception: pass

    def _ensure_combat_bgm(self):
        """Lazily load the battle track from assets/ if it is missing."""
        if not self.enabled:
            return None
        snd = self.sounds.get("combat_bgm")
        if snd is not None:
            return snd
        snd = self._asset_sound("music_combat_bgm.ogg")
        self.sounds["combat_bgm"] = snd
        return snd

    def _combat_channel(self):
        """Return a usable channel for the battle track (recreate if lost)."""
        ch = self.combat_bgm_channel
        if ch is None:
            try:
                ch = pygame.mixer.Channel(6)
            except Exception:
                try:
                    ch = pygame.mixer.find_channel(True)
                except Exception:
                    ch = None
            self.combat_bgm_channel = ch
        return ch

    def combat_bgm_playing(self):
        """True only when the battle track is *actually* coming out of a channel."""
        try:
            ch = self.combat_bgm_channel
            return bool(ch and ch.get_busy())
        except Exception:
            return False

    def _ensure_bgm_track(self, key="ambient_bgm"):
        """Lazily load an ambience track from assets/."""
        snd = self.sounds.get(key)
        if snd is not None:
            return snd
        filename = {
            "ambient_bgm": "hayden-folker-adrift-_1_.ogg",
            "arctic_bgm":  "arctic_ambience.ogg",
        }.get(key)
        if not filename:
            return None
        snd = self._asset_sound(filename)
        if snd is not None:
            self.sounds[key] = snd
        return snd

    def _ensure_ambient_bgm(self):
        return self._ensure_bgm_track("ambient_bgm")

    def _music_channel(self):
        ch = self.bgm_channel
        if ch is None:
            try:
                ch = pygame.mixer.Channel(0)
            except Exception:
                try:
                    ch = pygame.mixer.find_channel(True)
                except Exception:
                    ch = None
            self.bgm_channel = ch
        return ch

    def ambient_bgm_playing(self):
        try:
            ch = self.bgm_channel
            return bool(ch and ch.get_busy())
        except Exception:
            return False

    def start_ambient_bgm(self):
        """Loop the biome ambience track (silent while combat music plays)."""
        if not self.enabled or self.in_combat_bgm:
            return
        key = "ambient_bgm"
        if self.last_biome == "Arctic":
            key = "arctic_bgm"
        if self.ambient_bgm_playing():
            if getattr(self, "current_bgm_key", None) == key:
                return
            self.stop_ambient_bgm()
        try:
            snd = self._ensure_bgm_track(key)
            if not snd and key != "ambient_bgm":
                key = "ambient_bgm"
                snd = self._ensure_bgm_track(key)
            ch = self._music_channel()
            if not snd or not ch:
                return
            try: snd.set_volume(0.20)  # ambient is quieter than other sounds
            except Exception: pass
            try: ch.set_volume(0.85)
            except Exception: pass
            ch.play(snd, loops=-1)
            self.current_bgm_key = key
        except Exception:
            pass

    def stop_ambient_bgm(self):
        try:
            if self.bgm_channel:
                self.bgm_channel.stop()
        except Exception:
            pass

    def start_combat_bgm(self):
        """Fade to combat BGM, silencing the ambient BGM."""
        if not self.enabled:
            return
        # Never trust the flag alone: a pause / stop_all_loops / channel steal can
        # leave in_combat_bgm True while nothing is playing, which used to make the
        # battle music silently never start again for the rest of the session.
        if self.in_combat_bgm and self.combat_bgm_playing():
            return
        self.in_combat_bgm = True
        try:
            snd = self._ensure_combat_bgm()
            ch = self._combat_channel()
            if not snd or not ch:
                return
            if self.ambient_channel:
                try: self.ambient_channel.set_volume(0.0)
                except Exception: pass
            if self.bgm_channel:
                try: self.bgm_channel.set_volume(0.0)
                except Exception: pass
            try: snd.set_volume(1.0)
            except Exception: pass
            try: ch.set_volume(1.0)
            except Exception: pass
            ch.play(snd, loops=-1)
        except Exception:
            pass

    def stop_combat_bgm(self):
        """Restore ambient BGM, stop combat music."""
        if not self.enabled: return
        self.in_combat_bgm = False
        try:
            if self.combat_bgm_channel: self.combat_bgm_channel.stop()
            if self.ambient_channel: self.ambient_channel.set_volume(1.0)
            if self.bgm_channel: self.bgm_channel.set_volume(1.0)
        except Exception: pass
        self.start_ambient_bgm()

    def tick_combat_bgm(self, in_combat):
        """Watchdog run every game tick: keeps the battle track in sync with the
        actual combat state, so a missed start/stop call (or a stolen channel)
        can't leave the wrong music playing."""
        if not self.enabled:
            return
        try:
            if in_combat:
                if not self.combat_bgm_playing():
                    self.in_combat_bgm = False
                    self.start_combat_bgm()
            elif self.in_combat_bgm or self.combat_bgm_playing():
                self.stop_combat_bgm()
            if not in_combat:
                self.start_ambient_bgm()
        except Exception:
            pass

    def stop_all_loops(self):
        """Stop all looping channels (call on pause or cleanup)."""
        if not self.enabled: return
        try:
            for ch in (self.inspect_channel, self.craft_channel,
                       self.gather_channel, self.combat_bgm_channel):
                if ch: ch.stop()
        except Exception: pass
        # The battle track was stopped above — clear the flag so the next combat
        # (or the watchdog) restarts it instead of thinking it is still playing.
        self.in_combat_bgm = False

    def play_animal_type(self, atype):
        """Play an ambient sound for the given animal type (best-effort)."""
        if not self.enabled:
            return
        if atype in ("squirrel", "young_squirrel"):
            self._play("squirrel")
        elif atype in ("deer", "young_deer"):
            self._play("deer")
        elif atype in ("cat", "young_cat"):
            self._play("cat_meow")
        else:
            self._play("animal")
HUNGER_TRAVEL_RATE = 1.0 / 30.0; THIRST_TRAVEL_RATE = HUNGER_TRAVEL_RATE * 2.0
DAY_NIGHT_HUNGER_LOSS = 20.0
BEGINNER_HUNGER_MULT = 0.25
NORMAL_HUNGER_MULT = 1.0
HARD_HUNGER_MULT = 1.3
# ---- LIGHT MODE ----------------------------------------------------------
# A relaxed difficulty: only Health, Hunger and Energy exist. Thirst and
# Fatigue are disabled (pinned full, hidden from every HUD), and Energy
# REGENERATES instead of draining, at 5x the normal passive drain rate.
LIGHT_MODE = {"on": False}
LIGHT_ENERGY_REGEN_MULT = 5.0

def is_light(player=None):
    if player is not None and getattr(player, "light_mode", False):
        return True
    return bool(LIGHT_MODE.get("on"))
GROT_GRID_STEP_DELAY = 0.18
GROT_ENERGY_BASE = 85
PASSIVE_ENERGY_RATE = HUNGER_IDLE_RATE * 0.5
DAY_LENGTH = 720
DAY_NIGHT_CYCLE = DAY_LENGTH / 5  # day/night flip is 5x faster than game-hour timers
TERM_WIDTH = 80  # default; will be updated dynamically
MAX_STAT_CAP = 100
STATION_MAX_HP = 500.0
TRAP_RANGE_VISIBLE = 30; TRAP_RANGE_SAFE = 15; TRAP_CATCH_TIME = 60.0; TRAP_MEAT = 10
FIRE_FUEL_PARTS  = 50             # fuel parts per fire_fuel item (each = 1 game-hour)
GAME_HOUR        = DAY_LENGTH / 24  # real seconds per game-hour (30 s at default DAY_LENGTH)
# ---- Temperature ----
# 0 = freezing, 50 = neutral/comfortable, 100 = burning
TEMP_NEUTRAL         = 50.0
TEMP_COLD_THRESH     = 30.0   # below → cold damage
TEMP_HOT_THRESH      = 75.0   # above → heat damage
TEMP_ARCTIC_DROP     = 3.0    # °/s temperature drop in Arctic (no insulation)
TEMP_FOREST_DRIFT    = 1.0    # °/s drift toward neutral in Forest
TEMP_CAMPFIRE_RISE   = 2.0    # °/s rise when resting at campfire
TEMP_COLD_DMG_FULL   = 10.0   # HP/game-hour at max insulation deficit
TEMP_HOT_DMG_FULL    = 8.0    # HP/game-hour at temp 100
# ---- Clothing insulation levels ----
CLOTHING_INSULATION = {
    "pants": 3, "shirt": 3,
    "medium_pants": 4, "medium_shirt": 4,
    "heavy_pants": 5, "heavy_shirt": 5,
}
CLOTHING_PANTS  = {"pants", "medium_pants", "heavy_pants"}
CLOTHING_SHIRTS = {"shirt", "medium_shirt", "heavy_shirt"}
ARCTIC_INSULATION_BASE = 6.0   # requirement to survive base Arctic
ARCTIC_INSULATION_MAX  = 10.0  # maximum possible requirement
FATIGUE_PASSIVE_RATE = HUNGER_IDLE_RATE * 0.5   # same drain rate as energy
REST_FATIGUE_RATE    = 30         # fatigue recovered per game-hour while resting
REST_CAMPFIRE_HP     = 15         # HP healed per game-hour (campfire rest)
REST_CAMPFIRE_ENERGY = 5          # energy healed per game-hour (campfire rest)
REST_FLOOR_DMG       = 10         # HP lost per game-hour (floor rest)
TOOL_DUR = 30
TOOL_DUR_ADV = 150   # advanced axe durability (5× basic)
INSPECT_COST = 5
MAX_INSPECTIONS = 5
INSPECT_TIME = 3.0
# Biome geography: Forest is a disc centred on (0,0); Arctic wraps around it.
# 120 game-travel-minutes at SPD_DAY (0.5 s/step) = 120*60/0.5 = 14 400 coordinate units.
FOREST_RADIUS = 3500
ANIMAL_GRID_SIZE = 3

# ==================== SPEARS ====================
# cursor_mult: multiplier on the cursor speed in the aiming minigame.
#   < 1.0 = slower cursor (easier to aim), > 1.0 = faster cursor (harder).
# strike_cost: durability lost per melee strike (defaults to strike dmg if absent).
# Shield definitions
# complete_block_pct: chance of full block (0 dmg)
# partial_miss_pct:   chance block fails entirely (after complete_block fails)
# partial_reduce_range: (min%, max%) damage reduction if partially blocking
# max_blocks: durability in number of blocks
# max_absorb: durability in total HP absorbed
# cursor_mult_throw: multiplier applied to throw cursor speed while equipped
SHIELD_DEFS = {
    "simple_shield":   {"complete_block_pct":0.20, "partial_miss_pct":0.35, "partial_reduce_range":(30,50), "max_blocks":15, "max_absorb":50,   "energy_cost":10, "icon":"🛡️", "no_heavy_spear":True, "cursor_mult_throw":1.5},
    "standard_shield": {"complete_block_pct":0.35, "partial_miss_pct":0.35, "partial_reduce_range":(40,65), "max_blocks":30, "max_absorb":125,  "energy_cost":12, "icon":"🛡️", "no_heavy_spear":True, "cursor_mult_throw":1.5},
    "advanced_shield": {"complete_block_pct":0.50, "partial_miss_pct":0.35, "partial_reduce_range":(50,75), "max_blocks":30, "max_absorb":400,  "energy_cost":15, "icon":"🛡️", "no_heavy_spear":True, "cursor_mult_throw":1.5},
    "sakos_shield":    {"complete_block_pct":0.85, "partial_miss_pct":0.10, "partial_reduce_range":(60,90), "max_blocks":100,"max_absorb":2000, "energy_cost":8,  "icon":"🗼", "no_heavy_spear":True, "cursor_mult_throw":1.5},
}

SPEAR_DEFS = {
    "spear":                   {"dur":100, "strike":5,  "throw":15, "miss_pct":0.10, "throw_cost":20,   "cursor_mult":1.0,  "icon":"🗡️"},
    "advanced_spear":          {"dur":200, "strike":10, "throw":25, "miss_pct":0.10, "throw_cost":20,   "cursor_mult":1.0,  "icon":"⚔️"},
    "ice_spear":               {"dur":25,  "strike":10, "throw":30, "miss_pct":0.15, "throw_cost":9999, "cursor_mult":1.2,  "icon":"🧊"},
    "advanced_ice_spear":      {"dur":80,  "strike":15, "throw":40, "miss_pct":0.10, "throw_cost":50,   "cursor_mult":0.9,  "icon":"❄️⚔️"},
    "throwing_spear":          {"dur":100, "strike":5,  "throw":5,  "miss_pct":0.0,  "throw_cost":10,   "cursor_mult":0.5,  "strike_cost":5,  "icon":"🎯"},
    "advanced_throwing_spear": {"dur":250, "strike":10, "throw":20, "miss_pct":0.0,  "throw_cost":10,   "cursor_mult":0.4,  "strike_cost":5,  "icon":"🎯⚔️"},
    "heavy_spear":             {"dur":200, "strike":10, "throw":30, "miss_pct":0.0,  "throw_cost":50,   "cursor_mult":1.8,  "strike_cost":5,  "icon":"⚒️"},
    "advanced_heavy_spear":    {"dur":500, "strike":10, "throw":30, "miss_pct":0.0,  "throw_cost":50,   "cursor_mult":1.8,  "strike_cost":5,  "icon":"⚒️⚔️"},
    "grot_tooth":              {"dur":100, "strike":15, "throw":0,  "miss_pct":0.10, "throw_cost":9999, "cursor_mult":1.0,  "range":1, "icon":"🦴", "cat":"🗡️ Melee"},
}

# ==================== SPEAR MINIGAME DATA ====================
# Per-animal aiming data for the spear-throw minigame.
# cursor_speed: base cells/sec the |_| moves (scaled by spear's cursor_mult).
# anim_speed:   cells/sec the silhouette moves along the bar.
# movement:     "smooth" | "hopping" | "erratic"
# dist_tiers:   (min_dist, max_dist, tier_name) — first match wins.
SPEAR_MINIGAME_ANIMALS = {
    "deer": {
        "silhouettes":  {"close":"░▒▓██▓▒░","medium":"▒▓█▓▒","far":"▓█▓","very_far":"█"},
        "dist_tiers":   [(0,3,"close"),(3,5,"medium"),(5,8,"far"),(8,99,"very_far")],
        "cursor_speed": {"close":8,"medium":10,"far":14,"very_far":18},
        "anim_speed":   {"close":6,"medium":8,"far":10,"very_far":14},
        "movement":     "smooth",
    },
    "young_deer": {
        "silhouettes":  {"close":"░▒▓█▓▒░","medium":"▒▓█▓▒","far":"▓█▓","very_far":"█"},
        "dist_tiers":   [(0,3,"close"),(3,5,"medium"),(5,8,"far"),(8,99,"very_far")],
        "cursor_speed": {"close":8,"medium":10,"far":14,"very_far":18},
        "anim_speed":   {"close":5,"medium":7,"far":9,"very_far":13},
        "movement":     "smooth",
    },
    "rabbit": {
        "silhouettes":  {"close":"░▓█▓░","medium":"▓█▓","far":"█","very_far":"█"},
        "dist_tiers":   [(0,2,"close"),(2,5,"medium"),(5,8,"far"),(8,99,"very_far")],
        "cursor_speed": {"close":14,"medium":17,"far":22,"very_far":28},
        "anim_speed":   {"close":14,"medium":18,"far":22,"very_far":28},
        "movement":     "hopping",
    },
    "young_rabbit": {
        "silhouettes":  {"close":"▓█▓","medium":"█","far":"█","very_far":"█"},
        "dist_tiers":   [(0,2,"close"),(2,5,"medium"),(5,8,"far"),(8,99,"very_far")],
        "cursor_speed": {"close":16,"medium":20,"far":25,"very_far":30},
        "anim_speed":   {"close":16,"medium":20,"far":24,"very_far":30},
        "movement":     "hopping",
    },
    "squirrel": {
        "silhouettes":  {"close":"░▒▓█▓▒░","medium":"▒▓█▓▒","far":"▓█","very_far":"█"},
        "dist_tiers":   [(0,2,"close"),(2,5,"medium"),(5,8,"far"),(8,99,"very_far")],
        "cursor_speed": {"close":12,"medium":15,"far":20,"very_far":26},
        "anim_speed":   {"close":10,"medium":14,"far":18,"very_far":24},
        "movement":     "erratic",
    },
    "young_squirrel": {
        "silhouettes":  {"close":"▒▓█▓▒","medium":"▓█▓","far":"█","very_far":"█"},
        "dist_tiers":   [(0,2,"close"),(2,5,"medium"),(5,8,"far"),(8,99,"very_far")],
        "cursor_speed": {"close":13,"medium":16,"far":21,"very_far":26},
        "anim_speed":   {"close":11,"medium":15,"far":19,"very_far":25},
        "movement":     "erratic",
    },
    "antelope": {
        "silhouettes":  {"close":"▒▓██▓▒","medium":"▓██▓","far":"▓█▓","very_far":"█"},
        "dist_tiers":   [(0,2,"close"),(2,5,"medium"),(5,8,"far"),(8,99,"very_far")],
        "cursor_speed": {"close":10,"medium":13,"far":17,"very_far":22},
        "anim_speed":   {"close":22,"medium":28,"far":36,"very_far":44},
        "movement":     "smooth",
    },
    "young_antelope": {
        "silhouettes":  {"close":"▒▓█▓▒","medium":"▓█▓","far":"▓█▓","very_far":"█"},
        "dist_tiers":   [(0,2,"close"),(2,5,"medium"),(5,8,"far"),(8,99,"very_far")],
        "cursor_speed": {"close":10,"medium":13,"far":17,"very_far":22},
        "anim_speed":   {"close":14,"medium":18,"far":24,"very_far":32},
        "movement":     "smooth",
    },
}

# ==================== ANIMALS ====================
CAT_MEOWS = [
    "Mmmmmmmmmeeeoow!!!!",
    "Meow!",
    "Meeeeeeeeeeeeeeeeeeeeeeeeeeeeeoooooooow!!!!!!",
    "Meooooooooo!",
    "Mah!",
    "Mreow!",
    "Meow, meow meow!",
    "Purrumreow!",
    "Purrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrr…",
    "Meooooooooooooooooooow!",
    "MOO!!!!",
    "Purrumeow.",
    "Meow, meow, meow meow meoooooow!",
    "Neeeeeow!",
    "Naaaaaaaaaaaaaaaaaaaah!",
    "Kirimeow!",
    "Memeow!",
    "Memoo!",
    "Me-ooooooooooooooooooout!",
    "Me-in!",
    "Me-in, me-in!",
    "Meouch!",
    "Meeeeeeeeeeeeeeeeeeeeeeeeeeaaaaaaaah!",
    "Gurmeow!",
    "Gurmoo!",
    "Meowhoo!",
    "Keemeow!",
    "Meeeeeeeeeeeeeeeeeeeeee-iiiiiiiiiiiiinnnnnnnnnnnnnnnnnn!",
]

ANIMAL_DEFS = {
    "rabbit":        {"biome":"Forest","hp":2,  "speed_cpm":40,"vision_peak":2,"vision_max":3,  "group":(1,1),  "loot":{"meat":2},         "icon":"🐇","spawn_rate":0.00},
    "young_rabbit":  {"biome":"Forest","hp":1,  "speed_cpm":20,"vision_peak":2,"vision_max":3,  "group":(1,1),  "loot":{"meat":1},         "icon":"🐇","spawn_rate":0.00},
    "squirrel":      {"biome":"Forest","hp":2,  "speed_cpm":15,"vision_peak":5,"vision_max":10, "group":(1,1),  "loot":{"meat":2},         "icon":"🐿️","spawn_rate":0.00},
    "young_squirrel":{"biome":"Forest","hp":1,  "speed_cpm":15,"vision_peak":2.5,"vision_max":5,"group":(1,1),  "loot":{"meat":1},         "icon":"🐿️","spawn_rate":0.00},
    "deer":          {"biome":"Forest","hp":20, "speed_cpm":30,"vision_peak":5,"vision_max":10, "group":(1,1),  "loot":{"meat":15},        "icon":"🦌","spawn_rate":0.00},
    "young_deer":    {"biome":"Forest","hp":10, "speed_cpm":20,"vision_peak":5,"vision_max":10, "group":(1,1),  "loot":{"meat":10},        "icon":"🦌","spawn_rate":0.00},
    "antelope":      {"biome":"Forest","hp":30, "speed_cpm":20,"vision_peak":5,"vision_max":10, "group":(1,1),  "loot":{"meat":15},        "icon":"🐐","spawn_rate":0.00},
    "young_antelope":{"biome":"Forest","hp":15, "speed_cpm":10,"vision_peak":2.5,"vision_max":5,"group":(1,1),  "loot":{"meat":10},        "icon":"🐐","spawn_rate":0.00},
    "cat":           {"biome":"Forest","hp":3,  "speed_cpm":30,"vision_peak":5,"vision_max":10, "group":(1,1),  "loot":{},                 "icon":"🐈","spawn_rate":0.00,"atk":2,"def":1},
    "young_cat":     {"biome":"Forest","hp":1,  "speed_cpm":20,"vision_peak":3,"vision_max":5,  "group":(1,1),  "loot":{},                 "icon":"🐱","spawn_rate":0.00,"atk":0,"def":0},
    "salmon":        {"biome":"Arctic","hp":5,  "speed_cpm":20,"vision_peak":3,"vision_max":6,  "group":(1,1),  "loot":{"meat":2},         "icon":"🐟","spawn_rate":0.02},
    "seal":          {"biome":"Arctic","hp":10, "speed_cpm":25,"vision_peak":5,"vision_max":10, "group":(2,4),  "loot":{"meat":6,"bone":3},"icon":"🦭","spawn_rate":0.01},
    "penguin":       {"biome":"Arctic","hp":10, "speed_cpm":8, "vision_peak":5,"vision_max":10, "group":(50,50),"loot":{"meat":6,"bone":3},"icon":"🐧","spawn_rate":0.02,"panic":True},
    "grot":          {"biome":["Forest","Arctic"],"hp":5,"speed_cpm":15,"vision_peak":5,"vision_max":5,"group":(1,1),"icon":"👹","spawn_rate":0.00},
    "grot_leader":   {"biome":["Forest","Arctic"],"hp":12,"speed_cpm":12,"vision_peak":8,"vision_max":10,"group":(1,1),"loot":{"grot_hide":2,"grot_tooth":1,"coins":15},"icon":"👑","spawn_rate":0.00},
}

ANIMAL_XP = {
    "rabbit": 3,
    "squirrel": 4,
    "deer": 15,
    "antelope": 25,
    "cat": 5,
    "young_cat": 2,
    "grot": 10,
    "grot_leader": 30,
}


def biome_matches(adef, biome):
    bm = adef.get("biome")
    if isinstance(bm, (list, tuple, set)):
        return biome in bm
    return biome == bm


def grot_stats(hidden_xp, grace=False):
    if hidden_xp < 40:
        stats = {"hp":5, "atk":2, "def":1, "speed_cpm":15, "vision_peak":5, "vision_max":5}
    elif hidden_xp < 100:
        stats = {"hp":6, "atk":3, "def":2, "speed_cpm":25, "vision_peak":7, "vision_max":7}
    elif hidden_xp < 140:
        stats = {"hp":7, "atk":4, "def":3, "speed_cpm":30, "vision_peak":10, "vision_max":10}
    else:
        stats = {"hp":9, "atk":5, "def":3, "speed_cpm":35, "vision_peak":12, "vision_max":12}
    if grace:
        for key in ("hp","atk","def","speed_cpm","vision_peak","vision_max"):
            stats[key] = max(1, int(round(stats[key] * 0.6)))
    return stats

# ==================== ACHIEVEMENTS ====================
ACHIEVEMENTS = {
    "first_sunrise":  {"name":"First Sunrise",          "desc":"Survive 1 night and day without dying",       "pts":10, "coins":10},
    "survivor_5":     {"name":"Nice job, survivor!",    "desc":"Survive 5 days and nights without dying",     "pts":100,"coins":100},
    "survivor_15":    {"name":"Survivor Hardcore",      "desc":"Survive 15 days and nights without dying",    "pts":500,"coins":300},
    "arctic_explore": {"name":"Arctic Explorer",        "desc":"Reach the Arctic",                            "pts":100,"coins":100},
    "meat_hunter":    {"name":"Meat Hunter",            "desc":"Catch your first meat from a kill",           "pts":50, "coins":50},
    "trap_man":       {"name":"Trap Man",               "desc":"Catch 5 meat in traps",                       "pts":75, "coins":75},
    "penguin_1":      {"name":"Penguin Hunter",         "desc":"Catch 1 penguin",                             "pts":100,"coins":50},
    "penguin_5":      {"name":"Penguin Killer",         "desc":"Catch 5 penguins",                            "pts":300,"coins":100},
    "penguin_10":     {"name":"Pro Penguin Murderer",   "desc":"Catch 10 penguins",                           "pts":500,"coins":200},
    "time_15":        {"name":"Time is Ticking By",     "desc":"Spend 15 real minutes playing",               "pts":30, "coins":10},
    "time_30":        {"name":"Wow! 30 Minutes!",       "desc":"Spend 30 real minutes playing",               "pts":100,"coins":50},
    "time_60":        {"name":"An Hour Has Gone By",    "desc":"Spend 60 real minutes playing",               "pts":200,"coins":100},
    "wood_10":        {"name":"First Trees",            "desc":"Gather 10 wood",                              "pts":10, "coins":10},
    "wood_50":        {"name":"Experienced Cutting",    "desc":"Gather 50 wood",                              "pts":100,"coins":100},
    "wood_100":       {"name":"Expert Cutter",          "desc":"Gather 100 wood",                             "pts":300,"coins":250},
    "seal_1":         {"name":"Seal Hunter",            "desc":"Kill a seal",                                 "pts":100,"coins":50},
    "seal_5":         {"name":"Seal Killer",            "desc":"Hunt 5 seals",                                "pts":200,"coins":100},
    "seal_10":        {"name":"Pro Seal Murderer",      "desc":"Hunt 10 seals",                               "pts":300,"coins":150},
    "fish_1":         {"name":"Angler",                 "desc":"Hunt a salmon or other fish",                 "pts":50, "coins":25},
    "fish_5":         {"name":"Good Angler",            "desc":"Hunt 5 salmon or other fish",                 "pts":100,"coins":50},
    "fish_10":        {"name":"Pro Angler",             "desc":"Hunt 10 salmon or other fish",                "pts":250,"coins":100},
    "full_workshop":  {"name":"Full Workshop",          "desc":"Own all 6 stations simultaneously",           "pts":500,"coins":300},
}

MUSHROOM_ITEMS = {"mushrooms", "black_trumpets", "spotted_mushrooms", "mystery_mushroom"}

QUESTS = {
    "first_night": {
        "name": "Quest 1",
        "desc": "Hi, explorer! Tryin’ to survive a night here in the forest, eh? I dare you to survive!",
        "pts": 10,
        "coins": 10,
    },
    "beginners_luck": {
        "name": "Quest 2",
        "desc": "Beginner's luck! Beginner’s luck, I say! Either that or you’re an okay explorer. Either way, you won’t survive 3 more days and nights! Well, go on!",
        "pts": 50,
        "coins": 30,
    },
    "experienced_luck": {
        "name": "Quest 3",
        "desc": "Well, this is the end of your beginner’s luck! You’re a lucky one, youngling, either that or you really are an experienced explorer. But I have something that beginner’s luck can’t get you through, and even experienced explorer’s sometimes have to call for backup doing this… not that you have that option! Har har har, do it if you must, but really, I don’t expect much. Go on and survive 10 nights and days!",
        "pts": 350,
        "coins": 200,
    },
    "deadly_trial": {
        "name": "Quest 4",
        "desc": "Got it. I’m impressed, really. Either you really are a good explorer, which is the least likely… or you just have insane beginner’s luck. Either way, you’re dead. Try to survive 15 more nights and days!",
        "pts": 500,
        "coins": 500,
    },
    "survivor_reward": {
        "name": "Quest 5",
        "desc": "Har har har! You really are an experienced explorer! Har har har! You might even be a match for me surviving!",
        "pts": 0,
        "coins": 0,
    },
    "fight_old_man": {
        "name": "Quest 5b",
        "desc": "You think you can match me? Har! Then fight me! (Type: fight old_man)",
        "pts": 500,
        "coins": 250,
    },
    "berry_gathering": {
        "name": "Quest 6a",
        "desc": "Berries are essential food! Gather 12 safe berries — wild, sweet, or frostberry. Poisonous and glowing berries don't count.",
        "pts": 20,
        "coins": 15,
    },
    "disease_recovery": {
        "name": "Quest 35",
        "desc": "You got sick! That's what happens when you drink dirty water or eat raw food. Get some antidote tea or moss healing to cure it!",
        "pts": 30,
        "coins": 25,
    },
    "berry_collection": {
        "name": "Quest 6b",
        "desc": "Hi! I see you’ve tried a berry. Collect me all of the berry types and you’ll get a reward!",
        "pts": 30,
        "coins": 20,
    },
    "mushroom_gathering": {
        "name": "Quest 7a",
        "desc": "Mushrooms grow in abundance! Gather 12 safe mushrooms — common mushrooms or black trumpets.",
        "pts": 20,
        "coins": 15,
    },
    "mushroom_collection": {
        "name": "Quest 7b",
        "desc": "Hi! I see you’ve tried a mushroom. Collect all of the mushroom types… including the most poisonous of them all… and you’ll get a reward!",
        "pts": 50,
        "coins": 30,
    },
    "mushroom_feast": {
        "name": "Quest 8",
        "desc": "Wow. I’m impressed. You wouldn’t, then, eat them all? I dare you to!",
        "pts": 100,
        "coins": 50,
    },
    "lumberjack_apprentice": {
        "name": "Quest 9",
        "desc": "Hi, lumberjack! Get 40 more wood for a reward!",
        "pts": 75,
        "coins": 50,
    },
    "wood_supply": {
        "name": "Quest 10",
        "desc": "Heh heh heh… an experienced lumberjack, eh? You see, back when I was a youngling like you, I could get all the wood I wanted. But my old bones… well, you see… typing ‘gather’ isn’t as easy as it used to be. And my wood supply is running out. If you would supply me with 100 wood that you gathered in the forest, I could offer you a supreme prize!",
        "pts": 50,
        "coins": 200,
    },
    "bee_hive_research": {
        "name": "Quest 11",
        "desc": "Ho ho ho! I need to ask of you a favor. You see, I’m doing some research on bee hives. But I’m no valiant explorer like I was before, and so… Well, could you gather them for me? I need 2. You can keep them after I investigate them… okay?",
        "pts": 50,
        "coins": 50,
    },
    "armor_light": {
        "name": "Quest 12",
        "desc": "So… hohoho. You took damage taking those bee hives, huh? Fortunately, you have a sewing station now! So, I heard you could get armor to reduce damage taken. So get some light armor, it will help.",
        "pts": 65,
        "coins": 50,
    },
    "armor_medium": {
        "name": "Quest 13",
        "desc": "Try upgrading to medium armor. It will reduce damage more, but it won’t make you slower.",
        "pts": 125,
        "coins": 100,
    },
    "armor_heavy": {
        "name": "Quest 14",
        "desc": "Heavy armor is a tradeoff. On the one hand, you’re very well protected, but hunting will be very difficult, as you will be slower. You will thus use more energy per step… however, you will be protected against tons and tons of hazards… Overall, forgetting about the resource use, heavy armor is good. So make it.",
        "pts": 400,
        "coins": 300,
    },
    "pickaxe_starter": {
        "name": "Quest 15",
        "desc": "With a pickaxe you can get rock. With rock you can make a furnace. With a furnace, you can cook! Cooked stuff is important. Simply type: craft pickaxe",
        "pts": 30,
        "coins": 30,
    },
    "furnace_builder": {
        "name": "Quest 16",
        "desc": "Now that you have a pickaxe and can get rock, I suggest you build a furnace to be able to cook stuff… cooked stuff is normally better stuff.",
        "pts": 30,
        "coins": 40,
    },
    "spear_hunter": {
        "name": "Quest 17",
        "desc": "Great, you have a furnace! Now, build a spear so you can hunt!",
        "pts": 25,
        "coins": 30,
    },
    "bunny_hunt": {
        "name": "Quest 18",
        "desc": "Now you can hunt! Go catch a big, fat bunny! If you throw your spear (t+enter), then it will be easier to hit it, but your spear will break down faster. For bunnies specifically I recommend just using the walk to [coordinates bunny is at] command, then pressing a +enter or s +enter to strike.",
        "pts": 25,
        "coins": 10,
    },
    "squirrel_hunt": {
        "name": "Quest 19",
        "desc": "Great job! Now, go catch a squirrel for some more meat and variety! There is no real advantages to hunting squirrels over bunnies, and squirrels are harder. But heh heh heh! You need the practice! Squirrels are much slower than bunnies, so with a little luck, even if they see you, you can still get them good.",
        "pts": 30,
        "coins": 15,
    },
    "deer_hunt": {
        "name": "Quest 20",
        "desc": "Ha! Kicked the squirrel’s rear end! Go hunt a deer now. I think you’re prepared, and deers bring in LOTS of meat. I recommend throwing your spear this time, but you do you…",
        "pts": 50,
        "coins": 30,
    },
    "antelope_hunt": {
        "name": "Quest 21",
        "desc": "An experienced hunter, huh? Great! I think you’re prepared to kill an antelope!",
        "pts": 60,
        "coins": 35,
    },
    "plank_safety": {
        "name": "Quest 22",
        "desc": "Now that you have all of this equipment, I suggest you maintain it. Make 7 planks. It will be tedious, but you’ll thank me in the long run. 7 planks is enough to make both a woodworking station and an axe, in case one of them breaks. Whenever you build something new, don’t use these planks. Instead, treat them as “emergency” planks.",
        "pts": 40,
        "coins": 25,
    },
    "sewing_station": {
        "name": "Quest 23",
        "desc": "Sewing stations are incredibly useful. The biggest help, I would say, of a sewing machine, is the bandages. That and you can now craft armor. Bandages help with easy healing. Go make a sewing station!",
        "pts": 100,
        "coins": 40,
    },
    "spider_silk": {
        "name": "Quest 24",
        "desc": "Now that you have light armor, try harvesting some spider silk! Harvest 20.",
        "pts": 25,
        "coins": 15,
    },
    "water_filter": {
        "name": "Quest 25",
        "desc": "Great! Now, craft a water filter. Filtered water will allow you to restore health!",
        "pts": 30,
        "coins": 20,
    },
    "fresh_water": {
        "name": "Quest 26",
        "desc": "If you find fresh water, keep it. Fresh water is used in tons of recipes, and it allows you to recover thirst without taking damage.",
        "pts": 10,
        "coins": 30,
    },
    "filtered_water_drink": {
        "name": "Quest 27",
        "desc": "Great! Now craft some filtered water and drink it.",
        "pts": 10,
        "coins": 5,
    },
    "bandage_stock": {
        "name": "Quest 28",
        "desc": "Bandages are incredibly useful. Make 4, and always have at least 4 for emergencies.",
        "pts": 20,
        "coins": 30,
    },
    "trap_maker": {
        "name": "Quest 29",
        "desc": "Make a trap, they’re great!",
        "pts": 15,
        "coins": 20,
    },
    "poison_trapper": {
        "name": "Quest 30",
        "desc": "Okay, now make a poisonous trap. They yield double meat.",
        "pts": 30,
        "coins": 40,
    },
    "oil_maker": {
        "name": "Quest 31",
        "desc": "Hello! I see you have bee hives, eh? Try makin’ some oil. It helps with lots of stuff…",
        "pts": 100,
        "coins": 40,
    },
    "fire_fuel": {
        "name": "Quest 32",
        "desc": "Great! Now, make fire fuel. Like this, you can recover fatigue.",
        "pts": 25,
        "coins": 30,
    },
    "campfire_rest": {
        "name": "Quest 33",
        "desc": "Congrats! Make a campfire, then rest in it.",
        "pts": 50,
        "coins": 30,
    },
    "drought_survival": {
        "name": "Quest 34",
        "desc": "Well hohohoho. Would you see the weather? It’s a drought! Gather 10 fresh water or craft 5 filtered water before the drought ends!",
        "pts": 0,
        "coins": 0,
    },
    "lightning_warning": {
        "name": "Quest 35",
        "desc": "Hohoho! Hoho! Good god, you were struck by lightning, my dear friend! Craft medium or heavy armor before the next strike!",
        "pts": 0,
        "coins": 0,
    },
    "arctic_souvenir": {
        "name": "Quest 36",
        "desc": "Bring me back 3 items from the Arctic as a souvenir… in exchange, I’ll give you my map… you won’t have to use the inspect command for 20 game hours, or 10 real minutes!",
        "pts": 0,
        "coins": 100,
    },
    "textbook_recommendation": {
        "name": "Quest 37",
        "desc": "Why hohoho! Buy a textbook, it’s a more permanent solution than an ID lens!",
        "pts": 0,
        "coins": 10,
    },
    "textbook_mastery": {
        "name": "Quest 38",
        "desc": "Buy all 3 textbooks, and you’ll be unstoppable!",
        "pts": 0,
        "coins": 0,
    },
    "smelter_craft": {
        "name": "Quest 39",
        "desc": "Craft a smelter. It will help on lots of things.",
        "pts": 0,
        "coins": 0,
    },
    "trap_challenge": {
        "name": "Quest 40",
        "desc": "I dare you to catch 5 animals without missing!",
        "pts": 0,
        "coins": 0,
    },
    "poison_hunter": {
        "name": "Quest 41",
        "desc": "A poison hunter, eh? Hunt 3 animals with poison! Poison lasts 1 extra strike.",
        "pts": 0,
        "coins": 0,
    },
    "salmon_hunter": {
        "name": "Quest 42",
        "desc": "Go catch 3 salmon by throwing your spear!",
        "pts": 25,
        "coins": 50,
    },
    "arctic_speed": {
        "name": "Quest 43",
        "desc": "Reach the Arctic in less than 30 real minutes… go on, I dare you to!",
        "pts": 250,
        "coins": 500,
    },
    "station_challenge": {
        "name": "Quest 44",
        "desc": "I dare you to have all 6 stations simultaneously… do it!",
        "pts": 0,
        "coins": 0,
    },
    "arctic_sales": {
        "name": "Quest 45",
        "desc": "Showcase who you are! Sell 10 Arctic-specific items… and you’ll bump up that price!",
        "pts": 0,
        "coins": 0,
    },
}

QUEST_DISPLAY_NAMES = {
    "first_night": "Survive the First Night",
    "beginners_luck": "Survive Four Days",
    "experienced_luck": "Survive Ten Days",
    "deadly_trial": "Survive Twenty-Five Days",
    "survivor_reward": "Survivor Reward",
    "fight_old_man": "Fight the Old Man",
    "berry_gathering": "Gather Safe Berries",
    "berry_collection": "Collect Berry Types",
    "mushroom_gathering": "Gather Safe Mushrooms",
    "mushroom_collection": "Collect Mushroom Types",
    "mushroom_feast": "Mushroom Feast",
    "pickaxe_starter": "Craft a Pickaxe",
    "fresh_water": "Find Fresh Water",
}
for _qid, _q in QUESTS.items():
    _q["name"] = QUEST_DISPLAY_NAMES.get(_qid, _q["desc"].split(".")[0].split("!")[0].split("…")[0][:40].strip())


def check_achievement_cond(aid, player, current_playtime=None):
    pt = current_playtime if current_playtime is not None else player.total_playtime
    if aid == "first_sunrise":  return player.days_survived >= 1
    if aid == "survivor_5":     return player.days_survived >= 5
    if aid == "survivor_15":    return player.days_survived >= 15
    if aid == "arctic_explore": return player.arctic_visited
    if aid == "meat_hunter":    return player.total_hunts >= 1
    if aid == "trap_man":       return player.trap_meat_total >= 5
    if aid == "penguin_1":      return player.penguin_kills >= 1
    if aid == "penguin_5":      return player.penguin_kills >= 5
    if aid == "penguin_10":     return player.penguin_kills >= 10
    if aid == "time_15":        return pt >= 900
    if aid == "time_30":        return pt >= 1800
    if aid == "time_60":        return pt >= 3600
    if aid == "wood_10":        return player.wood_gathered >= 10
    if aid == "wood_50":        return player.wood_gathered >= 50
    if aid == "wood_100":       return player.wood_gathered >= 100
    if aid == "seal_1":         return player.seal_kills >= 1
    if aid == "seal_5":         return player.seal_kills >= 5
    if aid == "seal_10":        return player.seal_kills >= 10
    if aid == "fish_1":         return player.fish_kills >= 1
    if aid == "fish_5":         return player.fish_kills >= 5
    if aid == "fish_10":        return player.fish_kills >= 10
    if aid == "full_workshop":  return all(player.station_hp.get(s, 0) > 0 for s in ["woodworking_station","furnace","water_filter","liquifier","sewing_station","smelter"])
    return False


def show_quest_screen(term, player, preface=None, status_filter=None):
    if term is None:
        return
    lines = ["📝 OLD MAN QUEST LOG", "─" * TERM_WIDTH, ""]
    if preface:
        for l in vwrap(preface, TERM_WIDTH):
            lines.append(l)
        lines.append("")
    if status_filter in ("active", "completed"):
        visible = [qid for qid in reversed(list(QUESTS.keys())) if player.quests.get(qid) == status_filter]
    else:
        visible = [qid for qid in reversed(list(QUESTS.keys())) if player.quests.get(qid) in ("active", "completed")]
    if not visible:
        if status_filter == "active":
            lines.append("🧓 You have no active quests at the moment.")
        elif status_filter == "completed":
            lines.append("🧓 You haven't completed any quests yet.")
        else:
            lines.append("🧓 The old man has not given you any quests yet.")
        lines.append("")
    else:
        if status_filter == "active":
            lines.append("🟡 ACTIVE QUESTS")
        elif status_filter == "completed":
            lines.append("✅ COMPLETED QUESTS")
        else:
            lines.append("🟡 ACTIVE & ✅ COMPLETED QUESTS")
        lines.append("")
        for qid in visible:
            q = QUESTS[qid]
            status = player.quests.get(qid, "pending")
            icon = "✅" if status == "completed" else "🟡"
            label = "Completed" if status == "completed" else "Active"
            lines.append(f"  {icon} {label}")
            for wrapped in vwrap(q['desc'], TERM_WIDTH - 6):
                lines.append("     " + wrapped)
            lines.append("")
    lines += ["", "Press Enter to continue..."]
    term.print_page(lines, wait=True)


def update_quests(player, weather, world, msg, term=None):
    # The quick interactive tutorial is its own guided objective sequence.
    # Do not activate, complete, announce, or display normal quest progress
    # until that tutorial has finished.
    if getattr(player, "qt_active", False):
        return
    now = time.time()
    raw_playtime = player.total_playtime + max(0.0, now - player.session_start)
    if not hasattr(player, "quests"):
        player.quests = {qid: "pending" for qid in QUESTS}
    for qid in QUESTS:
        player.quests.setdefault(qid, "pending")
    if not hasattr(player, "quest_announced"):
        player.quest_announced = {qid: False for qid in QUESTS}
    if not hasattr(player, "quest_clock_started_at"):
        player.quest_clock_started_at = None
    if player.quest_clock_started_at is None:
        has_quest_progress = any(status != "pending" for status in player.quests.values())
        player.quest_clock_started_at = 0.0 if has_quest_progress else raw_playtime
    current_playtime = max(0.0, raw_playtime - player.quest_clock_started_at)

    def ensure(attr, default):
        if not hasattr(player, attr):
            setattr(player, attr, default)
        return getattr(player, attr)

    ensure("berries_gathered", 0)
    ensure("mushrooms_gathered", 0)
    ensure("frostberry_warm_since", 0.0)
    ensure("freezing_water_warm_since", 0.0)
    ensure("used_campfire", False)
    ensure("berry_types_eaten", [])
    ensure("mushroom_types_eaten", [])
    ensure("spider_silk_gathered", 0)
    ensure("bee_hives_collected", 0)
    ensure("quest11_ready_at", None)
    ensure("quest22_ready_at", None)
    ensure("quest23_ready_at", None)
    ensure("quest24_ready_at", None)
    ensure("quest28_ready_at", None)
    ensure("quest29_ready_at", None)
    ensure("quest31_ready_at", None)
    ensure("filtered_water_drank", False)
    ensure("bandages_made", 0)
    ensure("traps_set", 0)
    ensure("trap_successes", 0)
    ensure("poison_traps_crafted", 0)
    ensure("oil_made", 0)
    ensure("fire_fuel_crafted", 0)
    ensure("campfire_rested", False)
    ensure("textbooks_bought", 0)
    ensure("id_lens_bought", 0)
    ensure("smelter_crafted", False)
    ensure("poison_kills", 0)
    ensure("rabbit_kills", 0)
    ensure("squirrel_kills", 0)
    ensure("deer_kills", 0)
    ensure("antelope_kills", 0)
    ensure("arctic_items_sold", 0)
    ensure("arctic_reached_at", None)
    ensure("drought_quest_active", False)
    ensure("lightning_quest_triggered", False)
    ensure("trap_challenge_started", False)
    ensure("arctic_hunt_started", False)
    ensure("arctic_items_brought", 0)

    def activate(qid, text):
        if player.mode not in ("quest", "combat"):
            return
        if player.quests.get(qid) == "pending":
            player.quests[qid] = "active"
            player.quest_announced[qid] = True
            snd_act = getattr(player, "sound", None)
            if snd_act and getattr(snd_act, "enabled", False): snd_act.play_new_quest()
            # Show new quests in a dedicated full-screen prompt
            if term is not None:
                term.print_page(["📝 NEW QUEST", "─" * TERM_WIDTH, "", text, "", "Press Enter to continue."])
            msg.append(text)
            msg.append("🧓 Old Man: Type 'quests' to view details.")

    def complete(qid, text, reward=None):
        if player.quests.get(qid) != "completed":
            player.quests[qid] = "completed"
            player.points += QUESTS[qid]["pts"]
            player.coins += QUESTS[qid]["coins"]
            player.quest_announced[qid] = True
            snd = getattr(player, "sound", None)
            if snd and getattr(snd, "enabled", False): snd.play_quest_complete()
            reward_text = None
            if reward == "health_potion":
                player.inventory["health_potion"] = player.inventory.get("health_potion", 0) + 1
                reward_text = "✅ Received a Health Potion for your reward."
            if reward == "hp_tonic":
                player.inventory["health_potion"] = player.inventory.get("health_potion", 0) + 1
                reward_text = "✅ Received a Health Potion for your reward."
            # Build popup content
            popup = ["✅ QUEST COMPLETE", "─" * TERM_WIDTH, ""]
            popup.append("Objective:")
            for wrapped in vwrap(QUESTS[qid]["desc"], TERM_WIDTH - 4):
                popup.append("  " + wrapped)
            popup.append("")
            popup.append(f"Completed: {text.split(':')[1].strip() if ':' in text else 'Quest objective achieved!'}")
            popup.append("")
            popup.append("Rewards:")
            if QUESTS[qid]["pts"] > 0:
                popup.append(f"  🏆 {QUESTS[qid]['pts']} points")
            if QUESTS[qid]["coins"] > 0:
                popup.append(f"  🪙 {QUESTS[qid]['coins']} coins")
            if reward_text:
                popup.append(f"  {reward_text}")
            popup.append("")
            popup.append("Press Enter to continue.")
            # Show popup
            if term is not None:
                term.print_page(popup)
            # Announce completion in the message log
            msg.append(text)
            msg.append("🧓 Old Man: Well done. I have more for you soon.")
            if reward_text:
                msg.append(reward_text)
            msg.append("🧓 Old Man: Type 'quests' to open the quest log.")


    if player.mode not in ("quest", "combat"):
        return

    active_any = any(status == "active" for status in player.quests.values())
    if player.quests.get("first_night") == "pending" and not active_any:
        activate("first_night", "🧓 Old Man: Hi, explorer! Tryin’ to survive a night here in the forest, eh? I dare you to survive!")

    if player.quests.get("first_night") == "active":
        if player.days_survived >= 1 and player.wood_gathered >= 5:
            complete("first_night", "✅ QUEST COMPLETE: First Night survived! The old man rewards you with 10 points and 10 coins.")

    if player.quests.get("beginners_luck") == "pending" and player.quests.get("first_night") == "completed" and current_playtime >= 60:
        activate("beginners_luck", "🧓 Old Man: Beginner's luck! Beginner’s luck, I say! Either that or you’re an okay explorer. Either way, you won’t survive 3 more days and nights! Well, go on!")

    if player.quests.get("beginners_luck") == "active" and player.days_survived >= 4:
        complete("beginners_luck", "✅ QUEST COMPLETE: Beginner's luck survived! 50 points and 30 coins.")

    if player.quests.get("experienced_luck") == "pending" and player.quests.get("beginners_luck") == "completed":
        activate("experienced_luck", "🧓 Old Man: Well, this is the end of your beginner’s luck! You’re a lucky one, youngling, either that or you really are an experienced explorer. But I have something that beginner’s luck can’t get you through, and even experienced explorer’s sometimes have to call for backup doing this… not that you have that option! Har har har, do it if you must, but really, I don’t expect much. Go on and survive 10 nights and days!")

    if player.quests.get("experienced_luck") == "active" and player.days_survived >= 10:
        complete("experienced_luck", "✅ QUEST COMPLETE: 10 nights survived! 350 points and 200 coins.")

    if player.quests.get("deadly_trial") == "pending" and player.quests.get("experienced_luck") == "completed":
        activate("deadly_trial", "🧓 Old Man: Got it. I’m impressed, really. Either you really are a good explorer, which is the least likely… or you just have insane beginner’s luck. Either way, you’re dead. Try to survive 15 more nights and days!")

    if player.quests.get("deadly_trial") == "active" and player.days_survived >= 25:
        complete("deadly_trial", "✅ QUEST COMPLETE: 25 nights survived! 500 points and 500 coins.")

    if player.quests.get("survivor_reward") == "pending" and player.quests.get("deadly_trial") == "completed":
        activate("survivor_reward", "🧓 Old Man: Har har har! You really are an experienced explorer! Har har har! You might even be a match for me surviving!")
        complete("survivor_reward", "✅ QUEST COMPLETE: Reward delivered.", reward="hp_tonic")

    if player.quests.get("fight_old_man") == "pending" and player.quests.get("survivor_reward") == "completed":
        activate("fight_old_man", "🧓 Old Man: You think you can match me? Har! Then fight me! Type 'fight old_man' to begin!")

    # New quest: gather 20 non-poisonous, non-glowing berries
    # Sour berries explicitly excluded: they aren't pleasant or nutritious
    # enough to count toward the "12 safe berries" quest.
    SAFE_BERRIES_Q = {"wild_berries", "sweet_berries", "frostberry"}
    if player.quests.get("berry_gathering") == "pending" and current_playtime >= 10.0:
        activate("berry_gathering", "🧓 Old Man: Berries are essential food! Gather 12 safe berries — wild, sweet, or frostberry. Poisonous and glowing don't count!")
    if player.quests.get("berry_gathering") == "active":
        safe_count = sum(player.inventory.get(b, 0) for b in SAFE_BERRIES_Q)
        if safe_count >= 12:
            complete("berry_gathering", "✅ QUEST COMPLETE: 12 safe berries gathered! 20 points and 15 coins.")

    if player.quests.get("berry_collection") == "pending" and player.berry_types_eaten and player.quests.get("first_night") == "completed":
        activate("berry_collection", "🧓 Old Man: I see you’ve tried a berry. Collect me all of the berry types and you’ll get a reward!")

    if player.quests.get("berry_collection") == "active" and all(player.inventory.get(b, 0) > 0 for b in BERRY_ITEMS):
        complete("berry_collection", "✅ QUEST COMPLETE: Berry collection finished! 30 points and 20 coins.")

    # New quest: gather 20 non-death_cap, non-spotted mushrooms
    SAFE_SHROOMS_Q = {"mushrooms", "black_trumpets"}
    if player.quests.get("mushroom_gathering") == "pending" and current_playtime >= 10.0:
        activate("mushroom_gathering", "🧓 Old Man: Mushrooms grow everywhere! Gather 12 common mushrooms or black trumpets. The spotted and mystery ones don't count!")
    if player.quests.get("mushroom_gathering") == "active":
        safe_shroom_count = sum(player.inventory.get(m, 0) for m in SAFE_SHROOMS_Q)
        if safe_shroom_count >= 12:
            complete("mushroom_gathering", "✅ QUEST COMPLETE: 12 safe mushrooms gathered! 20 points and 15 coins.")

    if player.quests.get("mushroom_collection") == "pending" and player.mushroom_types_eaten and player.quests.get("first_night") == "completed":
        activate("mushroom_collection", "🧓 Old Man: I see you’ve tried a mushroom. Collect all of the mushroom types… including the most poisonous of them all… and you’ll get a reward!")

    if player.quests.get("mushroom_collection") == "active" and all(player.inventory.get(m, 0) > 0 for m in MUSHROOM_ITEMS):
        complete("mushroom_collection", "✅ QUEST COMPLETE: Mushroom collection finished! 50 points and 30 coins.")

    if player.quests.get("mushroom_feast") == "pending" and player.quests.get("mushroom_collection") == "completed" and set(player.mushroom_types_eaten) >= set(MUSHROOM_ITEMS):
        activate("mushroom_feast", "🧓 Old Man: Wow. I’m impressed. You wouldn’t, then, eat them all? I dare you to!")
        complete("mushroom_feast", "✅ QUEST COMPLETE: Mushroom feast achieved! 100 points and 50 coins.")

    if player.quests.get("lumberjack_apprentice") == "pending" and player.wood_gathered >= 10:
        activate("lumberjack_apprentice", "🧓 Old Man: Hi, lumberjack! Get 40 more wood for a reward!")

    if player.quests.get("lumberjack_apprentice") == "active" and player.wood_gathered >= 32:
        complete("lumberjack_apprentice", "✅ QUEST COMPLETE: Lumberjack apprentice done! 75 points and 50 coins.")

    if player.quests.get("wood_supply") == "pending" and player.quests.get("lumberjack_apprentice") == "completed":
        activate("wood_supply", "🧓 Old Man: Heh heh heh… an experienced lumberjack, eh? You see, back when I was a youngling like you, I could get all the wood I wanted. But my old bones… well, you see… typing ‘gather’ isn’t as easy as it used to be. And my wood supply is running out. If you would supply me with 100 wood that you gathered in the forest, I could offer you a supreme prize!")

    # wood_supply quest: need to sell 100 wood to old man (via sell command while quest active)
    if player.quests.get("wood_supply") == "active" and player.inventory.get("wood", 0) >= 92:
        # Old man approaches and asks to buy the wood
        if not getattr(player, '_wood_supply_offered', False):
            player._wood_supply_offered = True
            # Auto-sell/deliver the wood
            player.inventory["wood"] = player.inventory.get("wood", 0) - 92
            player.coins += 150  # bonus payment
            complete("wood_supply", "✅ QUEST COMPLETE: Old Man bought 100 wood for 150 coins! 50 points.")

    if player.quests.get("bee_hive_research") == "pending" and player.quests.get("beginners_luck") == "completed":
        if player.quest11_ready_at is None:
            player.quest11_ready_at = current_playtime + (GAME_HOUR * 2)
        if current_playtime >= player.quest11_ready_at:
            activate("bee_hive_research", "🧓 Old Man: Ho ho ho! I need to ask of you a favor. You see, I’m doing some research on bee hives. But I’m no valiant explorer like I was before, and so… Well, could you gather them for me? I need 2. You can keep them after I investigate them… okay?")

    if player.quests.get("bee_hive_research") == "active" and player.inventory.get("bee_hive", 0) >= 2:
        complete("bee_hive_research", "✅ QUEST COMPLETE: Bee hive research delivered! 50 points and 50 coins.", reward="health_potion")

    if player.quests.get("armor_light") == "pending" and player.quests.get("bee_hive_research") == "completed" and player.quests.get("sewing_station") == "completed":
        activate("armor_light", "🧓 Old Man: So… hohoho. You took damage taking those bee hives, huh? Fortunately, you have a sewing station now! So, I heard you could get armor to reduce damage taken. So get some light armor, it will help.")

    if player.quests.get("armor_light") == "active" and player.inventory.get("light_armor", 0) > 0:
        complete("armor_light", "✅ QUEST COMPLETE: Light armor acquired! 65 points and 50 coins.")
        player.quest24_ready_at = current_playtime + (GAME_HOUR * 2)

    if player.quests.get("armor_medium") == "pending" and player.quests.get("armor_light") == "completed":
        activate("armor_medium", "🧓 Old Man: Try upgrading to medium armor. It will reduce damage more, but it won’t make you slower.")

    if player.quests.get("armor_medium") == "active" and player.inventory.get("medium_armor", 0) > 0:
        complete("armor_medium", "✅ QUEST COMPLETE: Medium armor ready! 125 points and 100 coins.")

    if player.quests.get("armor_heavy") == "pending" and player.quests.get("armor_medium") == "completed":
        activate("armor_heavy", "🧓 Old Man: Heavy armor is a tradeoff. On the one hand, you’re very well protected, but hunting will be very difficult, as you will be slower. You will thus use more energy per step… however, you will be protected against tons and tons of hazards… Overall, forgetting about the resource use, heavy armor is good. So make it.")

    if player.quests.get("armor_heavy") == "active" and player.inventory.get("heavy_armor", 0) > 0:
        complete("armor_heavy", "✅ QUEST COMPLETE: Heavy armor acquired! 400 points and 300 coins.")

    if player.quests.get("pickaxe_starter") == "pending" and current_playtime >= GAME_HOUR * 4:
        activate("pickaxe_starter", "🧓 Old Man: Craft a pickaxe! You can then mine rock, and with rock you can make a furnace, which is better than raw food. To craft a pickaxe, simply type: craft pickaxe to see what resources you need.")

    if player.quests.get("pickaxe_starter") == "active" and player.inventory.get("pickaxe", 0) > 0:
        complete("pickaxe_starter", "✅ QUEST COMPLETE: Pickaxe obtained! 30 points and 30 coins.")

    if player.quests.get("furnace_builder") == "pending" and player.quests.get("pickaxe_starter") == "completed":
        activate("furnace_builder", "🧓 Old Man: Now that you have a pickaxe and can get rock, I suggest you build a furnace to be able to cook stuff… cooked stuff is normally better stuff.")

    if player.quests.get("furnace_builder") == "active" and player.inventory.get("furnace", 0) > 0:
        complete("furnace_builder", "✅ QUEST COMPLETE: Furnace built! 30 points and 40 coins.")

    if player.quests.get("spear_hunter") == "pending" and player.quests.get("furnace_builder") == "completed":
        activate("spear_hunter", "🧓 Old Man: Great, you have a furnace! Now, build a spear so you can hunt!")

    if player.quests.get("spear_hunter") == "active" and any(player.inventory.get(s, 0) > 0 for s in SPEAR_DEFS):
        complete("spear_hunter", "✅ QUEST COMPLETE: Spear ready! 25 points and 30 coins.")
        player.quest22_ready_at = current_playtime + (GAME_HOUR * 4)

    if player.quests.get("bunny_hunt") == "pending" and player.quests.get("spear_hunter") == "completed" and player.rabbit_kills >= 1:
        activate("bunny_hunt", "🧓 Old Man: Now you can hunt! Go catch a big, fat bunny! If you throw your spear (t+enter), then it will be easier to hit it, but your spear will break down faster. For bunnies specifically I recommend just using the walk to [coordinates bunny is at] command, then pressing a +enter or s +enter to strike.")

    if player.quests.get("bunny_hunt") == "active" and player.rabbit_kills >= 1:
        complete("bunny_hunt", "✅ QUEST COMPLETE: Bunny hunt done! 25 points and 10 coins.")

    if player.quests.get("squirrel_hunt") == "pending" and player.quests.get("bunny_hunt") == "completed" and player.squirrel_kills >= 1:
        activate("squirrel_hunt", "🧓 Old Man: Great job! Now, go catch a squirrel for some more meat and variety! There is no real advantages to hunting squirrels over bunnies, and squirrels are harder. But heh heh heh! You need the practice! Squirrels are much slower than bunnies, so with a little luck, even if they see you, you can still get them good.")

    if player.quests.get("squirrel_hunt") == "active" and player.squirrel_kills >= 1:
        complete("squirrel_hunt", "✅ QUEST COMPLETE: Squirrel hunt done! 30 points and 15 coins.")

    if player.quests.get("deer_hunt") == "pending" and player.quests.get("squirrel_hunt") == "completed" and player.deer_kills >= 1:
        activate("deer_hunt", "🧓 Old Man: Ha! Kicked the squirrel’s rear end! Go hunt a deer now. I think you’re prepared, and deers bring in LOTS of meat. I recommend throwing your spear this time, but you do you…")

    if player.quests.get("deer_hunt") == "active" and player.deer_kills >= 1:
        complete("deer_hunt", "✅ QUEST COMPLETE: Deer hunt done! 50 points and 30 coins.")

    if player.quests.get("antelope_hunt") == "pending" and player.quests.get("deer_hunt") == "completed" and player.antelope_kills >= 1:
        activate("antelope_hunt", "🧓 Old Man: An experienced hunter, huh? Great! I think you’re prepared to kill an antelope!")

    if player.quests.get("antelope_hunt") == "active" and player.antelope_kills >= 1:
        complete("antelope_hunt", "✅ QUEST COMPLETE: Antelope hunt done! 60 points and 35 coins.")

    if player.quests.get("plank_safety") == "pending" and player.quests.get("spear_hunter") == "completed" and current_playtime >= player.quest22_ready_at:
        activate("plank_safety", "🧓 Old Man: Now that you have all of this equipment, I suggest you maintain it. Make 7 planks. It will be tedious, but you’ll thank me in the long run. 7 planks is enough to make both a woodworking station and an axe, in case one of them breaks. Whenever you build something new, don’t use these planks. Instead, treat them as “emergency” planks.")

    if player.quests.get("plank_safety") == "active" and player.inventory.get("plank", 0) >= 7:
        complete("plank_safety", "✅ QUEST COMPLETE: Emergency planks ready! 40 points and 25 coins.")
        if player.quest23_ready_at is None:
            player.quest23_ready_at = current_playtime + (GAME_HOUR * 2)

    if player.quests.get("sewing_station") == "pending" and player.quests.get("plank_safety") == "completed" and current_playtime >= player.quest23_ready_at:
        activate("sewing_station", "🧓 Old Man: Sewing stations are incredibly useful. The biggest help, I would say, of a sewing machine, is the bandages. That and you can now craft armor. Bandages help with easy healing. Go make a sewing station!")

    if player.quests.get("sewing_station") == "active" and player.inventory.get("sewing_station", 0) > 0:
        complete("sewing_station", "✅ QUEST COMPLETE: Sewing station built! 100 points and 40 coins.")
        if player.quest28_ready_at is None:
            player.quest28_ready_at = current_playtime + (GAME_HOUR * 2)

    if player.quests.get("spider_silk") == "pending" and player.quests.get("armor_light") == "completed" and current_playtime >= player.quest24_ready_at:
        activate("spider_silk", "🧓 Old Man: Now that you have light armor, try harvesting some spider silk! Harvest 20.")

    if player.quests.get("spider_silk") == "active" and player.spider_silk_gathered >= 12:
        complete("spider_silk", "✅ QUEST COMPLETE: Spider silk gathered! 25 points and 15 coins.")
        if player.quest29_ready_at is None:
            player.quest29_ready_at = current_playtime + (GAME_HOUR * 2)

    if player.quests.get("water_filter") == "pending" and player.quests.get("spider_silk") == "completed":
        activate("water_filter", "🧓 Old Man: Great! Now, craft a water filter. Filtered water will allow you to restore health!")

    if player.quests.get("water_filter") == "active" and (player.inventory.get("water_filter", 0) > 0 or player.station_hp.get("water_filter", 0) > 0):
        complete("water_filter", "✅ QUEST COMPLETE: Water filter crafted! 30 points and 20 coins.")

    if player.quests.get("fresh_water") == "pending" and current_playtime >= GAME_HOUR * 2:
        activate("fresh_water", "🧓 Old Man: If you find fresh water, keep it. Fresh water is used in tons of recipes, and it allows you to recover thirst without taking damage.")

    if player.quests.get("fresh_water") == "active" and player.inventory.get("fresh_water", 0) >= 1:
        complete("fresh_water", "✅ QUEST COMPLETE: Fresh water collected! 10 points and 30 coins.")

    if player.quests.get("filtered_water_drink") == "pending" and player.quests.get("water_filter") == "completed":
        activate("filtered_water_drink", "🧓 Old Man: Great! Now craft some filtered water and drink it.")

    if player.quests.get("filtered_water_drink") == "active" and player.filtered_water_drank:
        complete("filtered_water_drink", "✅ QUEST COMPLETE: Filtered water drunk! 10 points and 5 coins.")

    if player.quests.get("bandage_stock") == "pending" and player.quests.get("sewing_station") == "completed" and current_playtime >= player.quest28_ready_at:
        activate("bandage_stock", "🧓 Old Man: Bandages are incredibly useful. Make 4, and always have at least 4 for emergencies.")

    if player.quests.get("bandage_stock") == "active" and player.bandages_made >= 4:
        complete("bandage_stock", "✅ QUEST COMPLETE: Bandages ready! 20 points and 30 coins.")

    if player.quests.get("trap_maker") == "pending" and player.quests.get("spider_silk") == "completed" and current_playtime >= player.quest29_ready_at:
        activate("trap_maker", "🧓 Old Man: Make a trap, they’re great!")

    if player.quests.get("trap_maker") == "active" and player.traps_set >= 1:
        complete("trap_maker", "✅ QUEST COMPLETE: Trap made! 15 points and 20 coins.")

    if player.quests.get("poison_trapper") == "pending" and player.quests.get("trap_maker") == "completed":
        activate("poison_trapper", "🧓 Old Man: Okay, now make a poisonous trap. They yield double meat.")

    if player.quests.get("poison_trapper") == "active" and player.poison_traps_crafted >= 1:
        complete("poison_trapper", "✅ QUEST COMPLETE: Poison trap crafted! 30 points and 40 coins.")

    if player.quests.get("smelter_craft") == "pending" and player.inventory.get("smelter", 0) > 0:
        activate("smelter_craft", "🧓 Old Man: Craft a smelter. It will help on lots of things.")
        complete("smelter_craft", "✅ QUEST COMPLETE: Smelter crafted!", reward=None)

    if player.quests.get("oil_maker") == "pending" and player.quests.get("bee_hive_research") == "completed" and player.quests.get("smelter_craft") == "completed":
        if player.quest31_ready_at is None:
            player.quest31_ready_at = current_playtime + (GAME_HOUR * 4)
        if current_playtime >= player.quest31_ready_at:
            activate("oil_maker", "🧓 Old Man: Hello! I see you have bee hives, eh? Try makin’ some oil. It helps with lots of stuff…")

    if player.quests.get("oil_maker") == "active" and (player.inventory.get("oil", 0) > 0 or player.oil_made >= 1):
        complete("oil_maker", "✅ QUEST COMPLETE: Oil made! 100 points and 40 coins.")

    if player.quests.get("fire_fuel") == "pending" and player.quests.get("oil_maker") == "completed":
        activate("fire_fuel", "🧓 Old Man: Great! Now, make fire fuel. Like this, you can recover fatigue.")

    if player.quests.get("fire_fuel") == "active" and (player.inventory.get("fire_fuel", 0) > 0 or player.fire_fuel_crafted >= 1):
        complete("fire_fuel", "✅ QUEST COMPLETE: Fire fuel made! 25 points and 30 coins.")

    if player.quests.get("campfire_rest") == "pending" and player.quests.get("oil_maker") == "completed":
        activate("campfire_rest", "🧓 Old Man: Congrats! Make a campfire, then rest in it.")

    if player.quests.get("campfire_rest") == "active" and player.campfire_rested:
        complete("campfire_rest", "✅ QUEST COMPLETE: Campfire rest complete! 50 points and 30 coins.")

    if player.quests.get("drought_survival") == "pending" and weather.is_drought:
        activate("drought_survival", "🧓 Old Man: Well hohohoho. Would you see the weather? It’s a drought! Gather 10 fresh water or craft 5 filtered water before the drought ends!")

    if player.quests.get("drought_survival") == "active" and (player.inventory.get("fresh_water", 0) >= 10 or player.inventory.get("filtered_water", 0) >= 5):
        complete("drought_survival", "✅ QUEST COMPLETE: Drought supplies ready!")

    if player.quests.get("lightning_warning") == "pending" and weather.lightning_hit and player.health > 0 and player.wearing not in ("medium_armor","heavy_armor"):
        activate("lightning_warning", "🧓 Old Man: Hohoho! Hoho! Good god, you were struck by lightning, my dear friend! Craft medium or heavy armor before the next strike!")

    if player.quests.get("lightning_warning") == "active" and player.wearing in ("medium_armor","heavy_armor"):
        complete("lightning_warning", "✅ QUEST COMPLETE: Armor ready to withstand lightning.")

    if player.quests.get("arctic_souvenir") == "pending" and biome_at(player.x, player.y) == "Forest" and dist_to_border(player.x, player.y) <= 500:
        activate("arctic_souvenir", "🧓 Old Man: Bring me back 3 items from the Arctic as a souvenir… in exchange, I’ll give you my map… you won’t have to use the inspect command for 20 game hours, or 10 real minutes!")

    if player.quests.get("arctic_souvenir") == "active" and (player.inventory.get("ice_chunk", 0) + player.inventory.get("freezing_water", 0) + player.inventory.get("freezing_dirty_water", 0) + player.inventory.get("arctic_water", 0) + player.inventory.get("snow", 0) >= 3):
        complete("arctic_souvenir", "✅ QUEST COMPLETE: Arctic souvenirs gathered! 100 coins.")

    if player.quests.get("textbook_recommendation") == "pending" and player.id_lens_bought > 0:
        activate("textbook_recommendation", "🧓 Old Man: Why hohoho! Buy a textbook, it’s a more permanent solution than an ID lens!")
        complete("textbook_recommendation", "✅ QUEST COMPLETE: Textbook recommendation received! 10 coins.")

    if player.quests.get("textbook_mastery") == "pending" and player.textbooks_bought >= 1:
        activate("textbook_mastery", "🧓 Old Man: Buy all 3 textbooks, and you’ll be unstoppable!")

    if player.quests.get("textbook_mastery") == "active" and player.textbooks_bought >= 3:
        complete("textbook_mastery", "✅ QUEST COMPLETE: Textbook mastery!", reward=None)

    if player.quests.get("trap_challenge") == "pending" and player.first_trap_set:
        activate("trap_challenge", "🧓 Old Man: I dare you to catch 5 animals without missing!")

    if player.quests.get("trap_challenge") == "active" and player.trap_successes >= 5:
        complete("trap_challenge", "✅ QUEST COMPLETE: Trap challenge complete!", reward=None)

    if player.quests.get("poison_hunter") == "pending" and player.poison_traps_crafted >= 1:
        activate("poison_hunter", "🧓 Old Man: A poison hunter, eh? Hunt 3 animals with poison!")

    if player.quests.get("poison_hunter") == "active" and player.poison_kills >= 3:
        complete("poison_hunter", "✅ QUEST COMPLETE: Poison hunter victory!", reward=None)

    if player.quests.get("salmon_hunter") == "pending" and player.arctic_items_sold >= 0 and biome_at(player.x, player.y) == "Arctic":
        activate("salmon_hunter", "🧓 Old Man: Go catch 3 salmon by throwing your spear!")

    if player.quests.get("salmon_hunter") == "active" and player.fish_kills >= 3:
        complete("salmon_hunter", "✅ QUEST COMPLETE: Salmon hunted! 50 coins and 25 points.")

    if player.quests.get("arctic_speed") == "pending" and player.days_survived >= 5 and current_playtime <= 1800:
        activate("arctic_speed", "🧓 Old Man: Reach the Arctic in less than 30 real minutes… go on, I dare you to!")

    if player.quests.get("arctic_speed") == "active" and player.arctic_visited and current_playtime <= 1800:
        complete("arctic_speed", "✅ QUEST COMPLETE: Arctic speed achieved! 500 coins and 250 points.")

    if player.quests.get("station_challenge") == "pending" and sum(1 for s in ["woodworking_station","furnace","water_filter","liquifier","sewing_station","smelter"] if player.inventory.get(s, 0) > 0) >= 4:
        activate("station_challenge", "🧓 Old Man: I dare you to have all 6 stations simultaneously… do it!")

    if player.quests.get("station_challenge") == "active" and sum(1 for s in ["woodworking_station","furnace","water_filter","liquifier","sewing_station","smelter"] if player.inventory.get(s, 0) > 0) == 6:
        complete("station_challenge", "✅ QUEST COMPLETE: Station challenge complete!", reward=None)

    if player.quests.get("arctic_sales") == "pending" and player.arctic_visited:
        activate("arctic_sales", "🧓 Old Man: Showcase who you are! Sell 10 Arctic-specific items… and you’ll bump up that price!")

    if player.quests.get("arctic_sales") == "active" and player.arctic_items_sold >= 10:
        complete("arctic_sales", "✅ QUEST COMPLETE: Arctic sales complete!", reward=None)


def _temp_label(temp, player=None):
    """Always-visible temperature meter — adaptive to insulation."""
    t = int(round(temp))
    # Insulation-adaptive: if player has enough insulation for current location,
    # cold temps register as Comfy (not Cold/Freezing).
    if player is not None:
        try:
            insulation = (CLOTHING_INSULATION.get(player.wearing_pants, 0) +
                          CLOTHING_INSULATION.get(player.wearing_shirt, 0))
            biome_here = biome_at(player.x, player.y)
            base_req = getattr(player, "arctic_insulation_req", 0)
            GRADIENT_DEPTH = 200.0
            if biome_here == "Arctic":
                arctic_depth = max(0.0, -dist_to_border(player.x, player.y))
                grad = min(1.0, arctic_depth / GRADIENT_DEPTH)
                effective_req = base_req * grad
            else:
                forest_dist = dist_to_border(player.x, player.y)
                if forest_dist <= GRADIENT_DEPTH:
                    grad = 1.0 - (forest_dist / GRADIENT_DEPTH)
                    effective_req = base_req * grad
                else:
                    effective_req = 0.0
            campfire_warm = (player.resting and getattr(player, "rest_mode", None) == "campfire"
                             and getattr(player, "campfire_fuel", 0) > 0)
            sufficient = (insulation >= effective_req) or campfire_warm
            cold_damaging = getattr(player, "_cold_damaging", False)
            if temp < TEMP_COLD_THRESH and sufficient and not cold_damaging:
                return f"😊 Comfy ({t}°)"
            if temp < TEMP_COLD_THRESH:
                if cold_damaging:
                    return f"🥶 Freezing ({t}°)"
                return f"❄️ Cold ({t}°)"
        except Exception:
            pass
    if temp < TEMP_COLD_THRESH:
        return f"❄️ Cold ({t}°)"
    if temp <= 45:   return f"🧥 Cool ({t}°)"
    if temp <= 65:   return f"😊 Comfy ({t}°)"
    if temp <= 80:   return f"🌡️ Warm ({t}°)"
    if temp <= 90:   return f"🔆 Hot ({t}°)"
    return f"🥵 Burning ({t}°)"

def _fmt_playtime(secs):
    h = int(secs // 3600); m = int((secs % 3600) // 60)
    return f"{h}h {m}m" if h else f"{m}m"

# Items always recognized on sight — everything else starts unknown
ALWAYS_IDENTIFIED = {
    "wood", "rock", "dirt", "fibergrass", "water", "fresh_water", "dirty_water", "ironroot",
    "bee_hive", "steel", "copper_ore", "iron_ore", "gold_ore",
    "ice_chunk", "freezing_water", "freezing_dirty_water", "ash", "arctic_water",
    "pants", "shirt", "medium_pants", "medium_shirt", "heavy_pants", "heavy_shirt",
    "snow",
}

# Berry types that count as "any_berry" for recipes
BERRY_ITEMS = [
    "wild_berries", "sweet_berries", "sour_berries",
    "glowing_berries", "frostberry", "shimmer_frostberry", "poisonous_berry"
]

# ==================== WEATHER & TORNADO DATA ====================
TORNADO_TYPES = {
    "light":  {"name": "🌪️ Light Tornado",   "dmg_hit": 35,  "dmg_near": 10, "radius": 30,  "destroy": 15,  "duration_mins": 20},
    "medium": {"name": "🌪️ Medium Tornado",  "dmg_hit": 50,  "dmg_near": 25, "radius": 75,  "destroy": 100, "duration_mins": 30},
    "huge":   {"name": "🌪️🔥 Huge Tornado", "dmg_hit": 100, "dmg_near": 75, "radius": 100, "destroy_pct": 0.95, "duration_mins": 60}
}

GAME_MECHANICS = {
    "hunger":       "🍽️ Hunger drains over time. At 0: -10 HP immediately, then every 30 seconds.",
    "thirst":       "💧 Thirst drains over time. At 0: continuous damage. Drink water to restore.",
    "energy":       "⚡ Energy fuels actions. Does NOT passively regenerate! Eat food or rest to recover.",
    "health":       "❤️ Your life. Hits 0 = Game Over. Damage from hazards, starvation, dehydration.",
    "armor":        "🛡️ ARMOR TYPES:\n  🟢 Light Armor     | 500 dur  | 20% dmg reduction\n     Hazard immunity: -5 from spider silk, -10 from poisonous spider, -5 from bee hives\n  🟡 Medium Armor    | 1000 dur | 40% dmg reduction\n     Hazard immunity: -0 from spider silk (full block!), -15 from poisonous spider, -10 from bee hives\n  🔴 Heavy Armor     | 1800 dur | 70% dmg reduction, -30% move speed\n     Hazard immunity: Spider damage → 0 (full immunity!), -20 from bee hives\n  Percentage reduction applies to: monster attacks, weather, firestorms.",
    "light rain":   "🌦️ +15 water/patch, -10% clusters. Lasts 1-3 hours.",
    "medium storm": "⛈️ +25 water/patch, -15% clusters. Spawns Lightning.",
    "heavy storm":  "🌩️ +40 water/patch, -30% clusters. Lightning & Tornadoes.",
    "lightning":    "⚡ ~80 dmg hit. Armor reduces. Nearby destroys clusters. Screen flashes RED!",
    "light tornado":"🌪️ 35 dmg hit. Destroys 15 clusters. 20 mins.",
    "medium tornado":"🌪️ 50 dmg hit. Destroys 100 clusters. 30 mins.",
    "huge tornado": "🌪️🔥 100 dmg hit. Destroys 95% area. 60 mins.",
    "drought":      "🏜️ After 3 dry days. Wither 85% non-rock/dirt resources until rain.",
    "identify":     "🔍 Use 'inspect <item>' or 'identify <item>' (5⚡, max 5 tries, 3s/attempt).",
    "walk":         "🚶 'walk to <name>' auto-paths until arrival or energy drain.",
    "gather":       "🪵 Collect at current tile (-2⚡). Yields 1-2 items. Hazards possible.",
    "craft":        "🔨 Uses resources, energy, time (IGM). Check 'recipes'.",
    "shop":         "🏪 Lists all buy/sell prices by category.",
    "save":         "💾 Saves progress to save_data.json. Auto-saves on quit/crash."
}

IDENTIFY_CHANCES = {
    "wood": 1.0, "rock": 1.0, "dirt": 1.0, "fibergrass": 1.0, "water": 1.0,
    "ironroot": 1.0, "bee_hive": 1.0, "steel": 1.0,
    "wild_berries": 0.25, "sweet_berries": 0.25, "sour_berries": 0.25,
    "glowing_berries": 0.25, "poisonous_berry": 0.25,
    "frostberry": 0.25, "shimmer_frostberry": 0.20,
    "mushrooms": 0.25, "black_trumpets": 0.25, "spotted_mushrooms": 0.25,
    "mushroom_death_cap": 0.15, "mystery_mushroom": 0.15,
    "moss_harmful": 0.10, "moss_healing": 0.10, "moss_mystery": 0.10,
    "spider_silk": 0.50, "venom_sac": 0.50, "night_bug": 0.50,
    "catnip": 0.75,
}

UNKNOWN_CATEGORY_MAP = {
    "moss_harmful": "moss", "moss_healing": "moss", "moss_mystery": "moss",
    "mushrooms": "mushrooms", "black_trumpets": "mushrooms", "spotted_mushrooms": "mushrooms",
    "mushroom_death_cap": "mushrooms", "mystery_mushroom": "mushrooms",
    "wild_berries": "berries", "sweet_berries": "berries", "sour_berries": "berries",
    "glowing_berries": "berries", "frostberry": "berries", "shimmer_frostberry": "berries",
    "poisonous_berry": "berries",
    "spider_silk": "spider_silk", "venom_sac": "venom_sac",
    "night_bug": "bugs",
}

UNKNOWN_DISPLAY_MAP = {
    "moss":         "❓ Unknown Moss",
    "mushrooms":    "❓ Unknown Mushroom",
    "berries":      "❓ Unknown Berries",
    "spider_silk":  "❓ Unknown Spider",
    "venom_sac":    "❓ Unknown Spider",
    "bugs":         "❓ Unknown Bugs",
}

UNKNOWN_NAME_MAP = {
    "spider_silk": "🕷️ Unknown Spider Material",
    "venom_sac":   "🕷️ Unknown Spider Material",
    "moss_harmful": "🌿 Unknown Moss", "moss_healing": "🌿 Unknown Moss", "moss_mystery": "🌿 Unknown Moss",
    "night_bug": "🐛 Unknown Bugs",
    "mushrooms": "🍄 Unknown Mushrooms", "black_trumpets": "🍄 Unknown Mushrooms",
    "spotted_mushrooms": "🍄 Unknown Mushrooms", "mushroom_death_cap": "🍄 Unknown Mushrooms",
    "mystery_mushroom": "🍄 Unknown Mushrooms",
    "wild_berries": "🫐 Unknown Berries", "sweet_berries": "🫐 Unknown Berries",
    "sour_berries": "🫐 Unknown Berries", "glowing_berries": "🫐 Unknown Berries",
    "frostberry": "🫐 Unknown Berries", "shimmer_frostberry": "🫐 Unknown Berries",
    "poisonous_berry": "🫐 Unknown Berries",
}

MOSS_TYPES = [
    {"id": "moss_harmful", "name": "🌿 Harmful Moss",  "chance": 0.70},
    {"id": "moss_healing", "name": "💚 Healing Moss",  "chance": 0.25},
    {"id": "moss_mystery", "name": "✨ Mystery Moss",  "chance": 0.05}
]
MUSHROOM_TYPES = [
    {"id": "mushrooms",         "name": "🍄 Common Mushroom",  "chance": 0.50},
    {"id": "black_trumpets",    "name": "🖤 Black Trumpet",    "chance": 0.20},
    {"id": "spotted_mushrooms", "name": "🔴 Spotted Mushroom", "chance": 0.15},
    {"id": "mushroom_death_cap","name": "☠️ Death Cap",        "chance": 0.05},
    {"id": "mystery_mushroom",  "name": "✨ Mystery Mushroom", "chance": 0.10}
]
# Total must = 1.0; glowing and poisonous each at ~0.18-0.20
BERRY_TYPES = [
    {"id": "wild_berries",    "name": "🫐 Wild Berries",      "chance": 0.23},
    {"id": "sweet_berries",   "name": "🍬 Sweet Berries",     "chance": 0.21},
    {"id": "sour_berries",    "name": "🍋 Sour Berries",      "chance": 0.18},
    {"id": "glowing_berries", "name": "✨ Glowing Berries",   "chance": 0.18},
    {"id": "poisonous_berry", "name": "☠️ Poisonous Berry",   "chance": 0.20},
]

DISPLAY_ITEM_NAME_MAP = {
    **{item["id"]: item["name"] for item in BERRY_TYPES},
    **{item["id"]: item["name"] for item in MUSHROOM_TYPES},
    **{item["id"]: item["name"] for item in MOSS_TYPES},
    "grot_tooth": "🐾 👹 Grot Tooth",
    "advanced_axe": "🪓⚡ Advanced Axe",
    "axe": "🪓 Axe",
}

def display_item_name(item):
    item = str(item)
    return DISPLAY_ITEM_NAME_MAP.get(item, item.replace("_"," ").title())

# ==================== GAME DATA ====================
food_effects = {
    "mushrooms":         {"energy": 25, "hunger": 20, "health": 0,   "thirst": 0},
    "black_trumpets":    {"energy": 30, "hunger": 15, "health": 5,   "thirst": 0,   "risk": "low",      "risk_min": 0.05, "risk_max": 0.20, "risk_dmg": 10},
    "spotted_mushrooms": {"energy": 55, "hunger": 45, "health": 5, "thirst": -5, "risk": "medium", "risk_min": 0.35, "risk_max":0.50, "risk_dmg": 15},
    "mushroom_death_cap":{"energy": 0,  "hunger": -20,"health": -35, "thirst": 5,   "notes": "☠️ Death Cap!"},
    "mystery_mushroom":  {"energy": 0,  "hunger": 0,  "health": 0,   "thirst": 0,   "risk": "mystery_mushroom"},
    "wild_berries":      {"energy": 15, "hunger": 10, "health": 0,   "thirst": 5},
    "sweet_berries":     {"energy": 20, "hunger": 15, "health": 5,   "thirst": 5},
    "sour_berries":      {"energy": 10, "hunger": 5,  "health": -5,  "thirst": 10},
    "glowing_berries":   {"energy": 70, "hunger": 60, "health": 0,   "thirst": -10, "risk": "high",     "risk_min": 0.45, "risk_max": 0.65, "risk_dmg": 20},
    "poisonous_berry":   {"energy": 0,  "hunger": 0,  "health": -20, "thirst": 5,   "notes": "☠️ Poisonous Berry! -20 HP"},
    "jerky":             {"energy":10, "hunger":40, "health":0,  "thirst":-5, "notes":"🥩 Dried meat. Extremely filling, low thirst."},
    "roasted_meat":      {"energy":15, "hunger":60, "health":10, "thirst":-10, "notes":"🔥 Savory roasted meat."},
    "thick_cut_meat":    {"energy":20, "hunger":85, "health":15, "thirst":-15, "notes":"🥩 Thick cut steak. Very filling."},
    "stuffed_thin_meat": {"energy":15, "hunger":70, "health":20, "thirst":-10, "notes":"🍄 Stuffed meat with mushrooms."},
    "stuffed_thin_meat_berries": {"energy":20, "hunger":75, "health":15, "thirst":0, "notes":"🍓 Meat stuffed with berries."},
    "stuffed_thin_meat_honey":   {"energy":25, "hunger":80, "health":20, "thirst":0, "notes":"🍯 Sweet honey-glazed meat."},
    "stuffed_thin_meat_meat":    {"energy":20, "hunger":85, "health":25, "thirst":-5, "notes":"🥩 Extra-meaty stuffed roast."},
    "moss_salve":        {"energy":0,  "hunger":5,  "health":25, "thirst":0,  "notes":"🌿 Natural healing paste."},
    "antidote_tea":      {"energy":15, "hunger":10, "health":5,  "thirst":25, "notes":"🍵 Clears toxins & soothes hazard wounds."},
    "frost_tonic":       {"energy":20, "hunger":15, "health":0,  "thirst":15, "notes":"❄️ Warms the core. Great before Arctic travel."},
    "glowing_jam":       {"energy":45, "hunger":25, "health":10, "thirst":-5, "notes":"✨ Potent energy boost. Safe & sweet."},
    "honey_root_tea":    {"energy":20, "hunger":15, "health":5,  "thirst":20, "notes":"☕ Soothing brew. Restores energy & thirst."},
    "compressed_fuel":   {"energy":0,  "hunger":0,  "health":0,  "thirst":0,  "notes":"🪵 Yields 2x Fire Fuel. Highly efficient."},
    "insulated_wrap":    {"energy":0,  "hunger":0,  "health":0,  "thirst":0,  "notes":"🧣 Apply to gear for cold resistance (flavor item)."},
    "ash_poultice":      {"energy":5,  "hunger":5,  "health":10, "thirst":0,  "notes":"🌫️ Cheap early-game wound treatment."},
    "moss_harmful":      {"energy": 0,  "hunger": 5,  "health": -10, "thirst": 5},
    "moss_healing":      {"energy": 0,  "hunger": 0,  "health": 25,  "thirst": 0},
    "moss_mystery":      {"energy": 0,  "hunger": 0,  "health": 0,   "thirst": 0,   "risk": "mystery_moss","risk_dmg": 50},
    "frostberry":        {"energy": 25, "hunger": 35, "health": 0,   "thirst": 0},
    "shimmer_frostberry":{"energy": 65, "hunger": 55, "health": 25,  "thirst": 0,   "risk": "very_high","risk_min": 0.65, "risk_max": 0.85, "risk_dmg": 25},
    "bee_hive":          {"energy": 10, "hunger": 10, "health": -5,  "thirst": 0,   "risk": "high",     "risk_min": 0.70, "risk_max": 0.90, "risk_dmg": 15},
    "honey":             {"energy": 40, "hunger": 10, "health": 10,  "thirst": -5},
    "roasted_berry":     {"energy": 45, "hunger": 5,  "health": 0,   "thirst": -2},
    "roasted_spotted_mushroom": {"energy": 45, "hunger": 20, "health": 5, "thirst": 0, "notes": "🍄 Roasted spotted mushroom. Safe and savory."},
    "cooked_berry":      {"energy": 45, "hunger": 5,  "health": 0,   "thirst": -2,  "risk": "high_reduced", "risk_min": 0.315, "risk_max": 0.455, "risk_dmg": 20},
    "cooked_shimmer_frostberry": {"energy": 65, "hunger": 35, "health": 10, "thirst": 0, "notes": "❄️ Hot shimmer frostberry infusion."},
    "stuffed_mushroom":  {"energy": 20, "hunger": 60, "health": 10,  "thirst": -5, "notes": "🍄 Stuffed mushroom, savory and filling."},
    "thin_cut_meat":     {"energy": 0,  "hunger": 0,  "health": 0,   "thirst": 0},
    "bandages":          {"energy": 0,  "hunger": 0,  "health": 20,  "thirst": 0},
    "enhanced_bandage":  {"energy": 0,  "hunger": 0,  "health": 30,  "thirst": 0},
    "meat":              {"energy": 0,  "hunger": 5,  "health": -5,  "thirst": 0,   "notes": "🥩 Raw meat. Cook it first for best results!"},
    "raw_game":          {"energy": 0,  "hunger": 5,  "health": -5,  "thirst": 0,   "notes": "🥩 Raw meat. Cook first!"},
    "ironroot":          {"energy": 5,  "hunger": 10, "health": 0,   "thirst": 0,   "notes": "🌱 Tough but edible."},
    "dirty_water":       {"energy": 5,  "hunger": 0,  "health": 0,  "thirst": 35, "notes": "💧 Dirty water. May make you sick."},
    "fresh_water":       {"energy": 5,  "hunger": 0,  "health": 0,  "thirst": 40, "notes": "💧 Fresh water. Safe to drink."},
    "water":             {"energy": 5,  "hunger": 0,  "health": 0,  "thirst": 35,  "notes": "💧 Unfiltered water. May make you sick — drink filtered_water when possible."},
    "filtered_water":    {"energy": 5,  "hunger": 0,  "health": 5,   "thirst": 40,  "notes": "💧 Clean filtered water."},
    "night_bug":         {"energy": 10, "hunger": 8,  "health": 0,   "thirst": -3,  "notes": "🐛 Crunchy. Surprisingly filling."},
    "coffee":            {"energy": 30, "hunger": 0,  "health": 0,   "thirst": 5,   "fatigue": 25, "notes": "☕ +30⚡ +25 Fatigue!"},
    "herbal_tea":        {"energy": 10, "hunger": 5,  "health": 5,   "thirst": 20,  "fatigue": 10, "notes": "🍵 Soothing tea. Restores thirst & a little health."},
    "chunky_stew":          {"energy": 25, "hunger": 80, "health": 15,  "thirst": 30,  "notes": "🍲 Hearty stew. Very filling and hydrating."},
    "health_potion":         {"energy": 30, "hunger": 0,  "health": 50,  "thirst": -10, "notes": "💊 Powerful healing potion. +50 HP!"},
    "arctic_water":          {"energy": 5,  "hunger": 0,  "health": -3,  "thirst": 30,  "notes": "❄️ Cold arctic water. Filter for safety."},
    "snow":                  {"energy": 0,  "hunger": 0,  "health": -5,  "thirst": 15,  "notes": "❄️ Eating snow drops your temp! -5 HP."},
    "ice_chunk":             {"energy": 0,  "hunger": 0,  "health": -10, "thirst": 20,  "notes": "🧊 Very cold. Do not eat! -10 HP."},
    "coffee_beans":          {"energy": 5,  "hunger": 0,  "health": 0,   "thirst": -5,  "notes": "☕ Raw beans. Bitter but gives a small energy boost."},
    "freezing_water":       {"energy":0,"hunger":0,"health":-5, "thirst":30,"notes":"❄️ Freezing cold! -5 HP. Cook in furnace first."},
    "freezing_dirty_water": {"energy":0,"hunger":0,"health":-10,"thirst":20,"notes":"❄️ Dirty & freezing! -10 HP. Cook in furnace first."},
}

BIOME_RESOURCES = {
    "Forest": {
        "🌲 Fallen Trees":    {"item": "wood",       "type": "material", "locked": True,  "tool_req": "axe",     "regrows": False, "hazard_key": None},
        "💧 Water Source":     {"item": "water",      "type": "drinkable","regrows": False, "hazard_key": None},
        "🐝 Bee Hive":        {"item": "bee_hive",   "type": "material", "hazard": True,  "regrows": False,      "hazard_key": "bee hive"},
        "🌱 Root Cluster":    {"item": "ironroot",   "type": "material", "regrows": True,  "hazard_key": None},
        "🪨 Rock Vein":       {"item": "rock",       "type": "material", "locked": True,  "tool_req": "pickaxe", "regrows": False, "hazard_key": None},
        "🌿 Moss Patch":      {"item": "moss_harmful","type": "material","regrows": True,  "hazard_key": None},
        "🍄 Mushroom Patch":  {"item": "mushrooms",  "type": "food",    "regrows": True,  "hazard_key": None},
        "🫐 Berry Bush":      {"item": "wild_berries","type": "food",    "regrows": True,  "hazard_key": None},
        "🕷️ Spider Nest":     {"item": "spider_silk","type": "material", "hazard": True,  "regrows": True,       "hazard_key": "spider nest"},
        "🕷️ Venomous Spider": {"item": "venom_sac",  "type": "material", "hazard": True,  "regrows": True,       "hazard_key": "venomous spider"},
        "🌾 Fibergrass Patch":{"item": "fibergrass", "type": "material", "regrows": True,  "hazard_key": None},
        "🌿 Catnip Cluster":  {"item": "catnip",     "type": "material", "regrows": True,  "hazard_key": None, "rare": True},
    },
    "Arctic": {
        "❄️ Snow Patch":        {"item": "snow",             "type": "material",   "regrows": True,  "hazard_key": None},
        "❄️ Snow Melt":         {"item": "arctic_water",     "type": "drinkable",  "regrows": False, "hazard_key": None},
        "🧊 Ice Chunk":         {"item": "ice_chunk",        "type": "material",   "locked": True, "tool_req": "pickaxe", "regrows": False, "hazard_key": None},
        "🫐 Frozen Berries":    {"item": "frostberry",       "type": "food",       "regrows": True,  "hazard_key": None},
        "✨ Shimmering Berries":{"item": "shimmer_frostberry","type": "food_risky", "regrows": True,  "hazard_key": None},
        "⛏️ Ice Vein":          {"item": "ice_chunk",        "type": "material",   "locked": True, "tool_req": "pickaxe", "regrows": False, "hazard_key": None},
        "🪨 Granite Outcrop":   {"item": "rock",             "type": "material",   "locked": True, "tool_req": "pickaxe", "regrows": False, "hazard_key": None},
        "🌿 Moss Patch":        {"item": "moss_harmful",     "type": "material",   "regrows": True,  "hazard_key": None},
    }
}

NIGHT_RESOURCES = {
    "Forest": {"🦗 Night Bugs":   {"item": "night_bug", "type": "food", "regrows": True, "hazard_key": None}},
    "Arctic": {"✨ Aurora Moths":  {"item": "night_bug", "type": "food", "regrows": True, "hazard_key": None}}
}

HAZARDS = {
    "bee hive":       {"dmg": 15, "chance": 0.80, "detour": 4.0},
    "venomous spider":{"dmg": 10, "chance": 0.65, "detour": 3.0},
    "spider nest":    {"dmg": 8,  "chance": 0.25, "detour": 3.0}
}

ITEM_PRICES = {
    "wood": 5, "rock": 8, "ironroot": 10, "spider_silk": 12, "venom_sac": 18,
    "bee_hive": 25, "wild_berries": 3, "sweet_berries": 5, "sour_berries": 4,
    "glowing_berries": 12, "poisonous_berry": 8,
    "mushrooms": 5, "black_trumpets": 6, "mystery_mushroom": 20, "spotted_mushrooms": 15,
    "shimmer_frostberry": 16, "frostberry": 4,
    "water": 2, "dirt": 1, "night_bug": 4, "fibergrass": 8,
    "honey": 40, "roasted_berry": 15, "roasted_spotted_mushroom": 25,
    "cooked_berry": 35, "cooked_shimmer_frostberry": 30,
    "herbal_tea": 20, "chunky_stew": 45, "roasted_meat": 25,
    "health_potion": 60, "filtered_water": 5,
    "catnip": 30,
    "jerky": 15, "moss_salve": 12, "antidote_tea": 25, "frost_tonic": 18, "glowing_jam": 20, "honey_root_tea": 15,
    "compressed_fuel": 50, "insulated_wrap": 40, "ash_poultice": 8,
    "meat": 10, "thin_cut_meat": 15, "stuffed_thin_meat": 30, "thick_cut_meat": 100,
    "stuffed_thin_meat_berries": 35, "stuffed_thin_meat_honey": 80, "stuffed_thin_meat_meat": 40,
    "axe": 100, "advanced_axe": 400, "pickaxe": 120,
    "plank": 15, "trap": 25, "poison_trap": 45,
    "woodworking_station": 200, "furnace": 300, "water_filter": 150, "liquifier": 150,
    "beeswax": 30, "poison": 20, "moss_harmful": 2, "moss_healing": 5, "moss_mystery": 10,
    "mushroom_death_cap": 1, "id_lens": 50, "textbook": 300,
    "sewing_station": 400, "fabric": 30, "bandages": 25, "light_armor": 500, "enhanced_bandage": 40,
    "smelter": 600, "raw_game": 8, "bone": 4, "gold_ore": 100, "copper_ore": 20, "iron_ore": 15,
    "grot_tooth": 20,
    "copper": 40, "iron": 30, "gold": 200, "oil": 150, "very_strong_fabric": 60,
    "plastic": 300, "necroplastic": 800, "steel": 100, "medium_armor": 1500, "heavy_armor": 3000,
    "fire_fuel": 300, "coffee_beans": 30, "coffee": 35,
    "ice_chunk": 15, "freezing_water": 2, "freezing_dirty_water": 1, "ash": 0,
    "snow": 0,
    "sand": 1,
    "gunpowder": 50,
    "pants": 80, "shirt": 80,
    "medium_pants": 160, "medium_shirt": 160,
    "heavy_pants": 240, "heavy_shirt": 240,
    "teepee": 180,
    "spear": 80, "advanced_spear": 200, "ice_spear": 60, "advanced_ice_spear": 150,
    "throwing_spear": 70, "advanced_throwing_spear": 220, "heavy_spear": 120, "advanced_heavy_spear": 350,
    "simple_shield": 80, "standard_shield": 180, "advanced_shield": 400, "sakos_shield": 2500,
    # Housing & furniture
    "glass": 50, "cannonball": 5, "steel_cannonball": 15,
    "wood_arrow": 2, "copper_arrow": 6, "iron_arrow": 8, "steel_arrow": 12,
    "cottage": 280, "bunker": 0, "mansion": 0, "teepee": 20, "dugout": 0,
    "basic_protection": 0, "standard_protection": 0, "extra_fortified_protection": 0,
    "bed": 180, "couch": 220, "gaming_console": 260,
    "cannon": 500, "advanced_cannon": 900, "ballista": 450, "advanced_ballista": 750,
}

SHOP_CATEGORIES = {
    "1. 🌿 Resources":       ["wood","rock","ironroot","fibergrass","water","dirt","night_bug","spider_silk","venom_sac","bee_hive","moss_harmful","moss_healing","moss_mystery","mushroom_death_cap","grot_tooth"],
    "2. 🍄 Foods & Berries": ["wild_berries","sweet_berries","sour_berries","glowing_berries","poisonous_berry","mushrooms","black_trumpets","spotted_mushrooms","mystery_mushroom","frostberry","shimmer_frostberry","honey","roasted_berry","cooked_berry","roasted_spotted_mushroom","cooked_shimmer_frostberry","herbal_tea","chunky_stew","roasted_meat","health_potion","filtered_water","coffee_beans","coffee"],
    "3. 🥩 Meat":            ["meat","raw_game","thin_cut_meat","thick_cut_meat","stuffed_thin_meat","stuffed_thin_meat_berries","stuffed_thin_meat_honey","stuffed_thin_meat_meat"],
    "4. 🔨 Tools & Mats":   ["axe","advanced_axe","pickaxe","plank","trap","poison_trap","beeswax","oil","fire_fuel","plastic","necroplastic","copper","iron","gold","copper_ore","iron_ore","gold_ore","steel","very_strong_fabric","fabric","poison"],
    "5. 🏭 Stations":        ["woodworking_station","sewing_station","furnace","smelter","water_filter","liquifier"],
    "6. 🛡️ Armor & Medical":["light_armor","medium_armor","heavy_armor","bandages","enhanced_bandage","id_lens","textbook"],
    "7. 🛋️ Furniture":      ["bed","couch","gaming_console"],
    "8. 🏠 Defense":        ["cannon","advanced_cannon","ballista","advanced_ballista"],
}

# any_berry = wildcard ingredient: uses whatever berry the player has
RECIPES = {
    "woodworking_station": {"mat": {"plank":5},                         "igm":120,"energy":15, "station": None,               "cat":"🪵 Woodworking"},
    "sewing_station":      {"mat": {"plank":8,"rock":2,"fabric":10},    "igm":90, "energy":15, "station":"woodworking_station", "cat":"🪵 Woodworking"},
    "smelter":             {"mat": {"rock":15,"plank":3,"fibergrass":10},"igm":120,"energy":20,"station":"woodworking_station","cat":"🔥 Smelting"},
    "axe":                 {"mat": {"wood":8,"plank":2},                "igm":60, "energy":5,  "station":"woodworking_station","cat":"🪵 Woodworking"},
    "advanced_axe":        {"mat": {"steel":2,"plank":3},               "igm":90, "energy":10, "station":"woodworking_station","cat":"🪵 Woodworking"},
    "pickaxe":             {"mat": {"wood":10,"plank":3},               "igm":90, "energy":10, "station":"woodworking_station","cat":"🪵 Woodworking"},
    "plank":               {"mat": {"wood":3},                          "igm":15, "energy":3,  "station":"woodworking_station","cat":"🪵 Woodworking"},
    "fabric":              {"mat": {"fibergrass":5},                    "igm":30, "energy":5,  "station":"woodworking_station","cat":"🪵 Woodworking"},
    "water_filter":        {"mat": {"spider_silk":20},                  "igm":90, "energy":5,  "station":"woodworking_station","cat":"🪵 Woodworking"},
    "liquifier":           {"mat": {"rock":5,"ironroot":5},             "igm":90, "energy":10, "station":"woodworking_station","cat":"🪵 Woodworking"},
    "trap":                {"mat": {"spider_silk":10},                  "igm":45, "energy":5,  "station":"sewing_station",    "cat":"🧵 Sewing"},
    "poison_trap":         {"mat": {"trap":1,"poison":1},               "igm":45, "energy":5,  "station":"sewing_station",    "cat":"🧵 Sewing"},
    "very_strong_fabric":  {"mat": {"spider_silk":5,"fibergrass":20},   "igm":60, "energy":10, "station":"sewing_station",    "cat":"🧵 Sewing"},
    "bandages":            {"mat": {"fabric":1},                        "igm":30, "energy":5,  "station":"sewing_station",    "cat":"🧵 Sewing"},
    "light_armor":         {"mat": {"fabric":8},                        "igm":120,"energy":15, "station":"sewing_station",    "cat":"🛡️ Armor"},
    "furnace":             {"mat": {"rock":10,"wood":15,"plank":3},     "igm":90, "energy":15, "station":"woodworking_station","cat":"🔥 Smelting"},
    "honey":               {"mat": {"bee_hive":1},                      "igm":30, "energy":5,  "station":"smelter",           "cat":"🔥 Smelting"},
    "beeswax":             {"mat": {"bee_hive":1},                      "igm":30, "energy":5,  "station":"smelter",           "cat":"🔥 Smelting"},
    "oil":                 {"mat": {"beeswax":2,"fibergrass":10},       "igm":100,"energy":15, "station":"smelter",           "cat":"🔥 Smelting"},
    "plastic":             {"mat": {"oil":2,"very_strong_fabric":3},    "igm":160,"energy":20, "station":"smelter",           "cat":"🔥 Smelting"},
    "copper":              {"mat": {"copper_ore":2},                    "igm":30, "energy":10, "station":"smelter",           "cat":"🔥 Smelting"},
    "iron":                {"mat": {"iron_ore":2},                      "igm":30, "energy":10, "station":"smelter",           "cat":"🔥 Smelting"},
    "gold":                {"mat": {"gold_ore":2},                      "igm":30, "energy":15, "station":"smelter",           "cat":"🔥 Smelting"},
    "steel":               {"mat": {"iron":2,"copper":1},               "igm":150,"energy":25, "station":"smelter",           "cat":"🔥 Smelting"},
    "necroplastic":        {"mat": {"bone":10,"plastic":2},             "igm":180,"energy":25, "station":"woodworking_station","cat":"🪵 Woodworking"},
    "thin_cut_meat":       {"mat": {"meat":1},                          "igm":45, "energy":8,  "station":"furnace",           "cat":"🍳 Furnace"},
    # any_berry = wildcard: any berry type from BERRY_ITEMS counts
    "roasted_berry":       {"mat": {"any_berry":2},                     "igm":20, "energy":5,  "station":"furnace","fuel":1,  "cat":"🍳 Furnace"},
    "cooked_berry":        {"mat": {"glowing_berries":2},               "igm":30, "energy":8,  "station":"furnace","fuel":2,  "cat":"🍳 Furnace"},
    "roasted_spotted_mushroom":{"mat":{"spotted_mushrooms":2},          "igm":30, "energy":8,  "station":"furnace","fuel":2,  "cat":"🍳 Furnace"},
    "cooked_shimmer_frostberry":{"mat":{"shimmer_frostberry":2},        "igm":30, "energy":8,  "station":"furnace","fuel":2,  "cat":"🍳 Furnace"},
    "thawed_frostberry":       {"mat":{"frostberry":10},                       "igm":20, "energy":5,  "station":"furnace","fuel":1,  "cat":"🍳 Furnace","yield":{"wild_berries":10}},
    "roasted_meat":        {"mat": {"meat":1},                          "igm":30, "energy":15, "station":"furnace","fuel":4,  "cat":"🍳 Furnace"},
    "herbal_tea":          {"mat": {"fresh_water":5,"ironroot":1},            "igm":20, "energy":5,  "station":["furnace","liquifier"],"fuel":2,  "cat":"🍳 Furnace"},
    "jerky":               {"mat": {"meat":1, "ash":1},                "igm":40, "energy":8,  "station":"furnace", "cat":"🍳 Furnace"},
    "moss_salve":          {"mat": {"moss_healing":2, "beeswax":1},    "igm":30, "energy":5,  "station":"furnace", "cat":"🍳 Furnace"},
    "antidote_tea":        {"mat": {"ironroot":1, "venom_sac":1, "fresh_water":5}, "igm":22, "energy":8,  "station":["furnace","liquifier"], "fuel":1, "cat":"🍳 Furnace"},
    "frost_tonic":         {"mat": {"frostberry":2, "ice_chunk":1, "fresh_water":3}, "igm":17, "energy":6,  "station":["furnace","liquifier"], "cat":"🍳 Furnace"},
    "glowing_jam":         {"mat": {"glowing_berries":2, "honey":1},    "igm":12, "energy":5,  "station":["furnace","liquifier"], "cat":"🍳 Furnace"},
    "honey_root_tea":      {"mat": {"ironroot":1, "honey":1, "fresh_water":3}, "igm":15, "energy":5,  "station":["furnace","liquifier"], "fuel":1, "cat":"🍳 Furnace"},
    "compressed_fuel":     {"mat": {"wood":20, "fibergrass":5}, "igm":60, "energy":10, "station":"woodworking_station", "cat":"🪵 Woodworking", "yield":{"fire_fuel":2}},
    "insulated_wrap":      {"mat": {"fabric":3, "spider_silk":5, "beeswax":1}, "igm":45, "energy":8, "station":"sewing_station", "cat":"🧵 Sewing"},
    "ash_poultice":        {"mat": {"ash":2, "fresh_water":2},               "igm":15, "energy":3,  "station":"woodworking_station", "cat":"🪵 Woodworking"},
    "chunky_stew":         {"mat": {"meat":1,"fresh_water":10},               "igm":45, "energy":12, "station":["furnace","liquifier"],"fuel":3,  "cat":"🍳 Furnace"},
    "stuffed_thin_meat":   {"mat": {"thin_cut_meat":1,"mushrooms":2},   "igm":60, "energy":10, "station":"furnace","fuel":2,  "cat":"🍳 Furnace"},
    "thick_cut_meat":      {"mat": {"meat":5},                          "igm":180,"energy":25, "station":"furnace","fuel":6,  "cat":"🍳 Furnace"},
    "stuffed_mushroom":    {"mat": {"mushrooms":2},                     "igm":30, "energy":5,  "station":"furnace",           "cat":"🍳 Furnace"},
    "stuffed_thin_meat_berries":{"mat":{"thin_cut_meat":1,"any_berry":3},"igm":45,"energy":10, "station":"furnace","fuel":1,  "cat":"🍳 Furnace"},
    "stuffed_thin_meat_honey":  {"mat":{"thin_cut_meat":1,"honey":1},   "igm":60, "energy":15, "station":"furnace","fuel":2,  "cat":"🍳 Furnace"},
    "stuffed_thin_meat_meat":   {"mat":{"thin_cut_meat":1,"meat":2},    "igm":50, "energy":12, "station":"furnace","fuel":1,  "cat":"🍳 Furnace"},
    "fire_fuel":           {"mat": {"oil":1,"wood":50},                 "igm":60, "energy":10, "station":"woodworking_station","cat":"🪵 Woodworking"},
    "coffee":              {"mat": {"coffee_beans":1,"fresh_water":1},   "igm":15, "energy":5,  "station":["furnace","liquifier"],"fuel":1,   "cat":"🍳 Furnace"},
    "poison":              {"mat": {"venom_sac":2},                     "igm":30, "energy":5,  "station":"woodworking_station","cat":"⚙️ General"},
    "medium_armor":        {"mat": {"plastic":5,"fibergrass":15,"steel":1},"igm":200,"energy":30,"station":["woodworking_station","sewing_station"],"wear":{"woodworking_station":120,"sewing_station":60},"cat":"🛡️ Armor"},
    "heavy_armor":         {"mat": {"necroplastic":3,"fibergrass":30,"steel":10},"igm":400,"energy":50,"station":["woodworking_station","sewing_station"],"wear":{"woodworking_station":250,"sewing_station":150},"cat":"🛡️ Armor"},
    "spear":                   {"mat": {"plank":2,"rock":15},        "igm":60,  "energy":10,"station":"woodworking_station","cat":"🗡️ Weapons"},
    "advanced_spear":          {"mat": {"plank":5,"rock":30},        "igm":90,  "energy":15,"station":"woodworking_station","cat":"🗡️ Weapons"},
    "ice_spear":               {"mat": {"plank":2,"ice_chunk":5},    "igm":45,  "energy":8, "station":"woodworking_station","cat":"🗡️ Weapons"},
    "advanced_ice_spear":      {"mat": {"plank":5,"ice_chunk":15},   "igm":90,  "energy":15,"station":"woodworking_station","cat":"🗡️ Weapons"},
    "throwing_spear":          {"mat": {"rock":10,"plank":3},        "igm":60,  "energy":10,"station":"woodworking_station","cat":"🗡️ Weapons"},
    "advanced_throwing_spear": {"mat": {"steel":3,"plank":3},        "igm":90,  "energy":15,"station":"woodworking_station","cat":"🗡️ Weapons"},
    "heavy_spear":             {"mat": {"rock":20,"plank":5},        "igm":90,  "energy":15,"station":"woodworking_station","cat":"🗡️ Weapons"},
    "advanced_heavy_spear":    {"mat": {"steel":5,"plank":5},        "igm":120, "energy":20,"station":"woodworking_station","cat":"🗡️ Weapons"},
    "simple_shield":           {"mat": {"rock":30,"plank":5},        "igm":90,  "energy":15,"station":"woodworking_station","cat":"🛡️ Armor"},
    "standard_shield":         {"mat": {"rock":45,"wood":10,"plank":10},"igm":120,"energy":20,"station":"woodworking_station","cat":"🛡️ Armor"},
    "advanced_shield":         {"mat": {"rock":60,"steel":5,"plank":15},"igm":180,"energy":30,"station":"woodworking_station","cat":"🛡️ Armor"},
    "sakos_shield":            {"mat": {"copper":5,"steel":5,"grot_hide":5,"gold":5,"rock":100,"plank":15,"wood":75},"igm":600,"energy":80,"station":"woodworking_station","cat":"🛡️ Armor"},
    "fresh_water":        {"mat": {"freezing_water":1},        "igm":5,  "energy":5, "station":"furnace","fuel":1,  "cat":"🍳 Furnace"},
    "dirty_water":        {"mat": {"freezing_dirty_water":1},  "igm":30, "energy":3, "station":"furnace","fuel":1,  "cat":"🍳 Furnace"},
    "filtered_water":     {"mat": {"dirty_water":1},            "igm":10, "energy":5,  "station":"water_filter",      "cat":"🏭 Stations"},
    "pants":              {"mat": {"fabric":5},                "igm":120,"energy":8, "station":"sewing_station",    "cat":"🧵 Sewing"},
    "shirt":              {"mat": {"fabric":5},                "igm":120,"energy":8, "station":"sewing_station",    "cat":"🧵 Sewing"},
    "medium_pants":       {"mat": {"fabric":10},               "igm":120,"energy":12,"station":"sewing_station",    "cat":"🧵 Sewing"},
    "medium_shirt":       {"mat": {"fabric":10},               "igm":120,"energy":12,"station":"sewing_station",    "cat":"🧵 Sewing"},
    "heavy_pants":        {"mat": {"fabric":15},               "igm":150,"energy":15,"station":"sewing_station",    "cat":"🧵 Sewing"},
    "heavy_shirt":        {"mat": {"fabric":15},               "igm":150,"energy":15,"station":"sewing_station",    "cat":"🧵 Sewing"},
    # New materials
    "glass":                     {"mat":{"sand":10},                                                     "igm":60,  "energy":5,  "station":"smelter",                      "cat":"🔥 Smelting"},
    # Ammo (no station needed)
    "cannonball":                {"mat":{"rock":10},                                                     "igm":20,  "energy":5,  "station":None,                           "cat":"🏠 Housing"},
    "steel_cannonball":          {"mat":{"steel":1},                                                     "igm":10,  "energy":5,  "station":None,                           "cat":"🏠 Housing"},
    "wood_arrow":                {"mat":{"wood":10},                                                     "igm":15,  "energy":5,  "station":None,                           "cat":"🏠 Housing"},
    "copper_arrow":              {"mat":{"copper":2,"wood":7},                                           "igm":20,  "energy":5,  "station":None,                           "cat":"🏠 Housing"},
    "iron_arrow":                {"mat":{"iron":2,"wood":8},                                             "igm":25,  "energy":5,  "station":None,                           "cat":"🏠 Housing"},
    "steel_arrow":               {"mat":{"steel":1,"wood":8},                                            "igm":30,  "energy":5,  "station":None,                           "cat":"🏠 Housing"},
    # Houses
    "cottage":                   {"mat":{"wood":20,"spider_silk":15},                                    "igm":180, "energy":30, "station":"woodworking_station",           "cat":"🏠 Housing"},
    "bunker":                    {"mat":{"spider_silk":30,"necroplastic":75,"wood":20,"rock":30,"steel":50}, "igm":500,"energy":60,"station":"woodworking_station",         "cat":"🏠 Housing"},
    "mansion":                   {"mat":{"spider_silk":400,"wood":550,"necroplastic":10},                "igm":1000,"energy":100,"station":"woodworking_station",           "cat":"🏠 Housing"},
    "teepee":                    {"mat":{"plank":10,"fabric":10},                                        "igm":60,  "energy":15, "station":"woodworking_station",           "cat":"🏠 Housing"},
    "dugout":                    {"mat":{"dirt":100},                                                    "igm":120, "energy":20, "station":None,                           "cat":"🏠 Housing"},
    # Furniture (house-only; placed with 'place' command inside house)
    "basic_protection":          {"mat":{"wood":50,"rock":45},                                           "igm":60,  "energy":10, "station":"woodworking_station",           "cat":"🏠 Housing"},
    "standard_protection":       {"mat":{"wood":100,"rock":90},                                          "igm":90,  "energy":15, "station":"woodworking_station",           "cat":"🏠 Housing"},
    "extra_fortified_protection":{"mat":{"steel":5,"wood":20,"rock":25},                                 "igm":120, "energy":20, "station":"woodworking_station",           "cat":"🏠 Housing"},
    "bed":                       {"mat":{"fabric":4,"spider_silk":3,"plank":4,"rock":10},                "igm":130, "energy":20, "station":["sewing_station","woodworking_station"],"wear":{"sewing_station":80,"woodworking_station":50},"cat":"🏠 Housing"},
    "couch":                     {"mat":{"fabric":6,"spider_silk":5,"plank":6,"rock":15},                "igm":130, "energy":20, "station":["sewing_station","woodworking_station"],"wear":{"sewing_station":80,"woodworking_station":50},"cat":"🏠 Housing"},
    "gaming_console":            {"mat":{"glass":1,"plastic":1,"wood":10,"copper":4},                    "igm":160, "energy":25, "station":"woodworking_station",           "cat":"🏠 Housing"},
    "cannon":                    {"mat":{"steel":5,"wood":20,"rock":30},                                 "igm":180, "energy":30, "station":"woodworking_station",           "cat":"🏠 Housing"},
    "advanced_cannon":           {"mat":{"steel":10,"wood":30,"rock":50,"copper":5},                     "igm":300, "energy":50, "station":"woodworking_station",           "cat":"🏠 Housing"},
    "ballista":                  {"mat":{"wood":50,"rock":50,"plank":10},                                "igm":180, "energy":30, "station":"woodworking_station",           "cat":"🏠 Housing"},
    "advanced_ballista":         {"mat":{"wood":65,"rock":75,"plank":15,"steel":3},                      "igm":280, "energy":45, "station":"woodworking_station",           "cat":"🏠 Housing"},
}

# ==================== HOUSING ====================
HOUSE_DEFS = {
    "cottage":  {"hp":400,  "footprint":4, "interior_cols":13,"interior_rows":7,  "emoji":"🏠","portable":False,"camouflage":False,"camouflage_frac":1.0},
    "bunker":   {"hp":2000, "footprint":3, "interior_cols":9, "interior_rows":7,  "emoji":"🏚️","portable":False,"camouflage":False,"camouflage_frac":1.0},
    "mansion":  {"hp":1000, "footprint":6, "interior_cols":20,"interior_rows":20, "emoji":"🏛️","portable":False,"camouflage":False,"camouflage_frac":1.0},
    "teepee":   {"hp":200,  "footprint":2, "interior_cols":9, "interior_rows":5,  "emoji":"⛺","portable":True, "camouflage":False,"camouflage_frac":1.0},
    "dugout":   {"hp":300,  "footprint":2, "interior_cols":9, "interior_rows":5,  "emoji":"🕳️","portable":False,"camouflage":True, "camouflage_frac":1.0/6.0},
}

FURNITURE_DEFS = {
    "basic_protection":          {"emoji":"🧱","w":4,"h":4,"prot_reduction":0.50,"fire_reduction":0.20,"prot_type":"protection"},
    "standard_protection":       {"emoji":"🛡","w":4,"h":4,"prot_reduction":0.75,"fire_reduction":0.40,"prot_type":"protection"},
    "extra_fortified_protection":{"emoji":"💪","w":4,"h":4,"prot_reduction":0.90,"fire_reduction":0.60,"prot_type":"protection"},
    "bed":           {"emoji":"🛏️","w":4,"h":2,"rest_mult":1.3,"skip_to_day":True, "prot_type":"rest"},
    "couch":         {"emoji":"🛋️","w":5,"h":2,"rest_mult":1.3,"skip_to_day":True, "enables_console":True,"prot_type":"rest"},
    "gaming_console":{"emoji":"🎮","w":1,"h":2,"requires":"couch","prot_type":"console"},
    "cannon":         {"emoji":"💣","w":6,"h":4,"ammo_types":("cannonball","steel_cannonball"),"range":9, "miss_per_tile":0.05,"flee_radius":25,"attract_radius":30,"prot_type":"turret"},
    "advanced_cannon":{"emoji":"💣","w":6,"h":4,"ammo_types":("cannonball","steel_cannonball"),"range":14,"miss_per_tile":0.03,"flee_radius":25,"attract_radius":30,"prot_type":"turret"},
    "ballista":         {"emoji":"🏹","w":5,"h":5,"ammo_types":("wood_arrow","copper_arrow","iron_arrow","steel_arrow"),"range":10,"miss_per_tile":0.03,"flee_radius":5, "attract_radius":10,"prot_type":"turret"},
    "advanced_ballista":{"emoji":"🏹","w":6,"h":5,"ammo_types":("wood_arrow","copper_arrow","iron_arrow","steel_arrow"),"range":14,"miss_per_tile":0.03,"flee_radius":7, "attract_radius":15,"prot_type":"turret"},
}

AMMO_DMG_MULT = {
    "cannonball":1.0,"steel_cannonball":2.0,
    "wood_arrow":1.0,"copper_arrow":1.5,"iron_arrow":2.0,"steel_arrow":2.5,
}

HOUSE_EMPTY = "☐"

GATHER_ALIASES = {
    "mushrooms":"mushrooms","mushroom":"mushrooms","fungus":"mushrooms",
    "unknown mushroom":"mushrooms","unknown fungus":"mushrooms","unknown mushrooms":"mushrooms",
    "spotted mushroom":"spotted_mushrooms","spotted":"spotted_mushrooms",
    "black trumpet":"black_trumpets","trumpet":"black_trumpets",
    "berries":"berries","berry":"berries","bush":"berries","unknown berries":"berries",
    "wild berries":"wild_berries","sweet berries":"sweet_berries","sour berries":"sour_berries",
    "glowing berries":"glowing_berries","glowing":"glowing_berries",
    "poisonous berry":"poisonous_berry","poisonous":"poisonous_berry",
    "frostberry":"frostberry","frost":"frostberry",
    "shimmer frostberry":"shimmer_frostberry","shimmer":"shimmer_frostberry",
    "water":"water","puddle":"water","stream":"water","fresh":"water",
    "fresh water":"fresh_water","dirty water":"dirty_water",
    "wood":"wood","trees":"wood","tree":"wood","log":"wood","logs":"wood","fallen":"wood",
    "rock":"rock","stone":"rock","granite":"rock","vein":"rock","outcrop":"rock",
    "ironroot":"ironroot","root":"ironroot","roots":"ironroot","cluster":"ironroot",
    "dirt":"dirt","soil":"dirt","mud":"dirt",
    "bee_hive":"bee_hive","hive":"bee_hive","bee":"bee_hive","bees":"bee_hive",
    "spider_silk":"spider_silk","silk":"spider_silk","spider":"spider_silk","nest":"spider_silk",
    "venom_sac":"venom_sac","venom":"venom_sac","sac":"venom_sac","venomous spider":"venom_sac",
    "unknown spider":"spider_silk","unknown spider material":"spider_silk",
    "night_bug":"night_bug","bug":"night_bug","insect":"night_bug","bugs":"night_bug",
    "moss":"moss_harmful","unknown moss":"moss_harmful",
    "fibergrass":"fibergrass","fiber":"fibergrass","grass":"fibergrass",
    "ice":"ice_chunk","ice chunk":"ice_chunk","ice_chunk":"ice_chunk",
    "ash":"ash","ashes":"ash",
    "freezing water":"freezing_water","freezing_water":"freezing_water",
    "freezing dirty water":"freezing_dirty_water","freezing_dirty_water":"freezing_dirty_water",
    "arctic water":"arctic_water",
    "rabbit":"rabbit","squirrel":"squirrel","salmon":"salmon","seal":"seal","penguin":"penguin",
}

CONSUME_ALIASES = {
    # mushrooms
    "mushroom":"mushrooms","mushrooms":"mushrooms",
    "spotted mushroom":"spotted_mushrooms","spotted mushrooms":"spotted_mushrooms",
    "spotted":"spotted_mushrooms","mystery mushroom":"mystery_mushroom",
    "mystery":"mystery_mushroom","death cap":"mushroom_death_cap",
    "black trumpet":"black_trumpets","black trumpets":"black_trumpets",
    "roasted spotted mushroom":"roasted_spotted_mushroom",
    "roasted spotted":"roasted_spotted_mushroom",
    "stuffed mushroom":"stuffed_mushroom","stuffed mushrooms":"stuffed_mushroom",
    # berries
    "berry":"berries","berries":"berries","wild berries":"berries","wild berry":"berries",
    "glowing berries":"glowing_berries","glowing berry":"glowing_berries",
    "glowing":"glowing_berries","shimmer":"shimmer_frostberry",
    "shimmer frostberry":"shimmer_frostberry","frostberry":"frostberry",
    "frost frostberry":"frostberry",
    "poisonous":"poisonous_berry","poisonous berry":"poisonous_berry",
    "poisonous berries":"poisonous_berry","roasted berry":"roasted_berry",
    "roasted berries":"roasted_berry","cooked berries":"cooked_berry",
    "cooked berry":"cooked_berry","cooked shimmer":"cooked_shimmer_frostberry",
    # meat
    "meat":"roasted_meat","roasted meat":"roasted_meat","roasted":"roasted_meat",
    "steak":"roasted_meat","cooked meat":"roasted_meat",
    "thin meat":"thin_cut_meat","thin_cut":"thin_cut_meat","thin cut meat":"thin_cut_meat",
    "thick meat":"thick_cut_meat","thick_cut":"thick_cut_meat","thick cut meat":"thick_cut_meat",
    "stuffed thin meat":"stuffed_thin_meat","stuffed thin":"stuffed_thin_meat",
    "jerky":"jerky","dried meat":"jerky",
    "raw meat":"raw_game","raw_meat":"raw_game","raw game":"raw_game","game":"raw_game",
    # insects / hives
    "bug":"night_bug","insect":"night_bug","night bug":"night_bug","bee":"bee_hive",
    "hive":"bee_hive","bee hive":"bee_hive","honey":"honey",
    # drinks / water
    "water":"water","drink":"water",
    "fresh water":"fresh_water","fresh":"fresh_water",
    "dirty water":"dirty_water","dirty":"dirty_water",
    "filtered":"filtered_water","filtered water":"filtered_water","safe water":"filtered_water",
    "freezing water":"freezing_water","freezing_water":"freezing_water",
    "freezing dirty water":"freezing_dirty_water","freezing_dirty_water":"freezing_dirty_water",
    "herbal tea":"herbal_tea","herbal":"herbal_tea","tea":"herbal_tea",
    "honey root tea":"honey_root_tea","root tea":"honey_root_tea","root_tea":"honey_root_tea",
    # stews / meals
    "stew":"chunky_stew","chunky stew":"chunky_stew","chunky":"chunky_stew",
    # moss / healing
    "moss":"moss_harmful","healing moss":"moss_healing","mystery moss":"moss_mystery",
    "salve":"moss_salve","moss salve":"moss_salve",
    # bandages
    "bandage":"bandages","bandages":"bandages",
    "enhanced bandage":"enhanced_bandage","enhanced_bandage":"enhanced_bandage",
    # potions / tonics
    "potion":"health_potion","health potion":"health_potion",
    "antidote":"antidote_tea","antidote tea":"antidote_tea",
    "frost tonic":"frost_tonic","frost":"frost_tonic",
    "jam":"glowing_jam","glowing jam":"glowing_jam",
    # other
    "ironroot":"ironroot","wrap":"insulated_wrap","insulated wrap":"insulated_wrap",
    "poultice":"ash_poultice","ash poultice":"ash_poultice",
}

HELP_PAGES = {
    "1. 🎮 Basic Controls": """🎮 BASIC CONTROLS
⬆️⬇️⬅️➡️  Arrow keys      : Move 1 tile (costs 0.5⚡). BLOCKED while crafting, gathering all, or resting!
🚶 walk <name>     : Auto-pathfind to a named resource/cluster
🏹 hunt <animal>   : Hunt an animal. Add 'throw' to throw your spear, or 'grid' for tactical combat.
                    e.g. 'hunt rabbit', 'hunt seal throw', 'hunt deer grid'
🗡️ attack / a      : Strike nearest animal within 2 tiles with equipped spear
🗡️ throw / t       : Throw spear at nearest animal
☠️ poison spear    : Coat your spear: next 4 strikes OR 1 throw deal double damage
🪵 gather          : Collect resources at your current tile (-2⚡)
🪵 gather all      : Auto-gather everything nearby (you can't act until it finishes)
🎒 inv             : View inventory (items & gear)
🍽️ eat <item>      : Eat food    💧 drink <item>  : Drink water/liquids
🔨 craft <item>    : Start crafting (check 'recipes' first)
✋ cancel          : Cancel the current crafting task
🔍 inspect/identify: Identify unknown item (5⚡, max 5 tries, 3s)
📜 recipes         : Browse craftable items by category
🏆 achievements    : View progress, points, and earned rewards
📝 quests          : View active quest log from the old man
🏪 shop            : Browse buy/sell prices by category
⏸️ pause           : Pause/resume the game (freeze time, weather, and auto-walk)
💰 buy/sell <item> : Trade with the shop
🛡️ equip <armor>   : Wear or remove armor (equip none to remove)
🔥 rest            : Toggle resting (campfire or floor). Pauses crafting; blocks other actions.
🪤 trap set/check/remove/list : Manage hunting traps
💾 save / quit     : Save progress or exit
📜 tutorials       : Re-read any tutorial you've unlocked
                    (first spear, spear throw, hunt, grot combat, rest, weather hazards)""",
    "2. ❤️ Survival Stats": """❤️ SURVIVAL STATS
❤️  Health  : Hits 0 = Game Over
🍽️ Hunger  : Drains over time. At 0: -10 HP immediately, then every 30 seconds. Eat food to restore.
💧 Thirst  : Drains over time. At 0: continuous HP loss.
⚡ Energy  : Powers every action. Does NOT regenerate passively!
            Eat food to recover energy.
😴 Fatigue : Drains over time. At 0: gathering and actions are BLOCKED!
            ONLY restored by resting or drinking ☕ coffee (+25).
            Floor rest: +30/game-hr but -10 HP/hr.
            Campfire rest: +30/game-hr, +15 HP/hr, +5 energy/hr (safe).

⚠️  Unfiltered water quenches thirst but costs 5 HP!
   Use a water_filter station to craft filtered_water from water.
""",
    "3. 🌦️ Weather": """🌦️ WEATHER SYSTEM
Weather shifts every 5 real-time minutes.

☀️ Clear       : No effects.
🌦️ Light Rain  : +15 water/patch. Stops water evaporation.
⛈️ Medium Storm: +25 water/patch. Lightning strikes (~80 dmg).
🌩️ Heavy Storm : +40 water/patch. Lightning + Tornadoes.
🏜️ Drought     : After 3 dry days — resources wither rapidly.

⚡ Lightning: screen flashes RED when it hits you!
🌪️ Tornado: screen flashes RED and shows HIT message on impact.
💧 No rain: water clusters lose 35% qty every 30 real seconds.
🌊 Flood: if most water clusters have qty>60, half of all other
          resources are swept away daily.
""",
    "4. 🪤 Traps & 🔥 Campfire": """🪤 TRAPS
Set traps to catch animals passively while you explore.
Craft:  trap (10 spider_silk, sewing_station)
        poison_trap (1 trap + 1 poison)

Commands:
  trap set     — place trap at your tile (consumes 1 trap from inventory)
  trap check   — collect any caught animals at your tile
  trap remove  — retrieve uncaught trap back to inventory
  trap list    — show all active traps with pos, distance, status
  traps        — alias for trap list

Catch chance: 45% (day) / 65% (night) per 60-second window.
Catch yields: 1-3 Raw Game. Poison trap: also +1 Bone.

🔥 CAMPFIRE & REST
craft fire_fuel  — 1 oil + 50 wood (woodworking_station) → 50 fuel parts
craft campfire   — uses 1 fire_fuel → lights campfire (50 game-hours of fuel)

rest — toggles resting on/off. Moving also cancels rest.

  🔥 Campfire mode: +30😴  +15❤️  +5⚡  per game-hour (30 real seconds)
                    burns 1 fuel part per game-hour
  😴 Floor mode:    +30😴  −10❤️         per game-hour (risky!)

At 0 Fatigue: gathering and most actions are BLOCKED.
Use coffee (buy from shop, or brew: coffee_beans + water in furnace) for +25😴.
""",
    "5. 🗡️ Hunting & Weapons": """🗡️ HUNTING & WEAPONS
Use a spear to hunt animals from close range or at a distance.
Attack with:  a / attack      — melee strike within 2 tiles
Throw with:  t / throw       — ranged attack, breaks the spear faster

Weapon notes:
  • Light spears are fast and durable.
  • Ice spears deal extra damage but break on throw.
  • Poison your spear with: poison spear

Hunting strategy:
  1. Use walk to <name> or walk to (<x>,<y>) to reach animals.
  2. Watch the scan list for nearby wildlife and distances.
  3. Attack rabbits and squirrels at close range.
  4. Throw at deer, antelope or fish for safer hits.

Best prey:
  • rabbit  — easiest early game meat.
  • squirrel — fast and tricky.
  • deer    — tougher, great reward for throwing.
  • salmon  — Arctic water fish, hunt from shore.

Pro tips:
  • Use walk to (-1, 4) with parentheses for exact coordinates.
  • Craft better armor before heading into stormy weather.
  • Inspect unknown items before eating or using them.
""",
    "6. \u2623\ufe0f Diseases": """\u2623\ufe0f DISEASES
Dirty water and bad food can make you sick. Diseases tick every day or night.

How you get infected:
  \u2022 Drinking dirty water or unfiltered water
  \u2022 Eating raw meat, certain mushrooms, or spoiled berries
  \u2022 Mystery mushrooms and moss can carry rare infections
  \u2022 After day 5, a small daily chance of random infection

Disease effects:
  Each disease drains health, hunger, thirst, or energy over time.
  Some diseases get WORSE with repeated exposure (stack!).

How to cure them:
  \u2022 moss_healing    \u2014 cures Cholera (90%), Salmonellosis (85%)
  \u2022 filtered_water \u2014 cures Cholera (45%), Dysentery (75%)
  \u2022 fresh_water    \u2014 cures Cholera (20%), Dysentery (50%)
  \u2022 mystery_mushroom / moss_mystery \u2014 cures Toxoplasmosis
  \u2022 Some diseases clear on their own after a few days

Prevention:
  \u2022 Always drink filtered_water when you can
  \u2022 Cook meat before eating (use a furnace)
  \u2022 Avoid risky mushrooms until you're prepared
  \u2022 Keep antidote tea on hand for emergencies
""",
}

def freeze_blocking_time(player=None, world=None, weather=None, elapsed=0.0):
    """Keep blocking popups/tutorial pages from advancing game clocks."""
    if elapsed <= 0:
        return
    if player is not None:
        for attr in ("last_passive", "last_day", "last_weather_check", "session_start", "rest_last", "qt_wait_until", "flee_until", "detour_until", "lore_intro_ready_at"):
            val = getattr(player, attr, None)
            if isinstance(val, (int, float)) and val > 0:
                setattr(player, attr, val + elapsed)
        for task in getattr(player, "active_tasks", []) or []:
            if isinstance(task.get("end"), (int, float)):
                task["end"] += elapsed
        ga = getattr(player, "gather_all", None)
        if ga and isinstance(ga.get("end"), (int, float)):
            ga["end"] += elapsed
        insp = getattr(player, "inspect_pending", None)
        if insp and isinstance(insp.get("end"), (int, float)):
            insp["end"] += elapsed
        for trap in getattr(player, "traps", []) or []:
            if isinstance(trap.get("catch_time"), (int, float)):
                trap["catch_time"] += elapsed
    if world is not None:
        for attr in ("last_regen", "last_spawn", "last_young_spawn", "last_survival_check", "last_resource_depletion", "last_fire_tick"):
            val = getattr(world, attr, None)
            if isinstance(val, (int, float)) and val > 0:
                setattr(world, attr, val + elapsed)
    if weather is not None:
        for attr in ("last_evap", "last_lightning"):
            val = getattr(weather, attr, None)
            if isinstance(val, (int, float)) and val > 0:
                setattr(weather, attr, val + elapsed)

def player_playtime(player):
    return getattr(player, "total_playtime", 0.0) + max(0.0, time.time() - getattr(player, "session_start", time.time()))

def schedule_lore_intro(player, delay=5.0):
    if getattr(player, "lore_intro_shown", False):
        return
    player.lore_intro_ready_at = player_playtime(player) + delay

def check_lore_intro(term, player):
    ready_at = getattr(player, "lore_intro_ready_at", None)
    if ready_at is not None and not getattr(player, "lore_intro_shown", False) and player_playtime(player) >= ready_at:
        show_lore_intro(term, player)
        player.lore_intro_ready_at = None


def _attempt_graphics_mode(player, target_cols=88, target_rows=22):
    """Auto-zoom the terminal for Graphics Mode.

    Strategy (in order):
      1. Already big enough → done.
      2. TIOCSWINSZ ioctl   → OS-level size hint (Linux/macOS, instant).
      3. xterm CSI 8 t      → window-resize escape (xterm, Kitty, iTerm2, WezTerm…).
      4. stty rows/cols     → shell-level hint (some SSH/mosh setups).
      5. Cycle through a table of terminal-specific sequences with measurement
         between each attempt; stop as soon as the terminal is large enough.
      6. Keyboard/font fallback modules when available.
      7. Manual prompt with per-terminal zoom instructions.

    Returns True when the terminal reports at least target_cols × target_rows.
    """
    if not getattr(player, "graphics_mode", False):
        return False
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False

    def _get_size():
        try:
            sz = os.get_terminal_size()
            return sz.columns, sz.lines
        except Exception:
            return 80, 24

    def _send(seq):
        try:
            sys.stdout.write(seq)
            sys.stdout.flush()
        except Exception:
            pass

    def _big_enough(c, r):
        return c >= target_cols and r >= target_rows

    cur_c, cur_r = _get_size()
    if _big_enough(cur_c, cur_r):
        return True

    # ── Detect terminal emulator ──────────────────────────────────────────
    term_prog  = os.environ.get("TERM_PROGRAM", "").lower()
    term_var   = os.environ.get("TERM", "").lower()
    wt_session = os.environ.get("WT_SESSION", "")
    kitty_id   = os.environ.get("KITTY_WINDOW_ID", "")
    colorterm  = os.environ.get("COLORTERM", "").lower()
    is_kitty   = bool(kitty_id) or "kitty" in term_var
    is_iterm2  = "iterm" in term_prog
    is_wt      = bool(wt_session)
    is_vscode  = "vscode" in term_prog
    is_wezterm = "wezterm" in term_prog
    is_apple   = "apple_terminal" in term_prog
    is_xterm   = "xterm" in term_var and not is_kitty
    is_vte     = "vte" in term_var or "gnome" in term_var

    # ── Multiplexer detection (tmux / screen / mosh) ─────────────────────
    # Inside a multiplexer, the inner pty size IS controllable by the child
    # process via TIOCSWINSZ / stty, so those tools actually work.
    # Outside a multiplexer they only lie to the OS without resizing the
    # visible window, so we must NOT count them as success.
    _in_mux = bool(os.environ.get("TMUX") or
                   os.environ.get("STY") or
                   os.environ.get("MOSH_SERVER_PID"))

    # ── Phase 1: TIOCSWINSZ ioctl ────────────────────────────────────────
    # Works reliably inside tmux / screen / mosh.
    # For direct terminal emulators it only changes what the OS reports,
    # NOT the visible window — so we only trust its success there.
    try:
        import fcntl, struct
        _ws = struct.pack("HHHH", target_rows, target_cols, 0, 0)
        fcntl.ioctl(sys.stdout.fileno(), termios.TIOCSWINSZ, _ws)
        time.sleep(0.05)
        if _in_mux:
            cur_c, cur_r = _get_size()
            if _big_enough(cur_c, cur_r):
                return True
    except Exception:
        pass

    # ── Phase 2: xterm CSI 8 t — window resize escape ────────────────────
    # Works on xterm, Kitty, iTerm2, WezTerm, and most VTE-based terminals.
    # {c2}/{r2} are a 10-col/4-row overshoot to overcome rounding.
    c2, r2 = target_cols + 10, target_rows + 4
    _seqs = []

    if is_kitty:
        _seqs += [
            (f"\033[8;{target_rows};{target_cols}t", 0.15),
            (f"\033[8;{r2};{c2}t\033[8;{target_rows};{target_cols}t", 0.25),
        ]
    elif is_iterm2:
        _seqs += [
            (f"\033[8;{target_rows};{target_cols}t", 0.15),
            (f"\033[8;{target_rows};{target_cols}t", 0.25),
        ]
    elif is_wezterm:
        _seqs += [
            (f"\033[8;{target_rows};{target_cols}t", 0.15),
            (f"\033[8;{r2};{c2}t", 0.15),
            (f"\033[8;{target_rows};{target_cols}t", 0.20),
        ]
    elif is_wt:
        _seqs += [
            (f"\033[8;{target_rows};{target_cols}t", 0.20),
        ]
    elif is_xterm or is_vte:
        _seqs += [
            (f"\033[8;{target_rows};{target_cols}t", 0.15),
            (f"\033[8;{r2};{c2}t", 0.10),
            (f"\033[8;{target_rows};{target_cols}t", 0.20),
            (f"\033[4;{target_rows * 16};{target_cols * 8}t", 0.20),
        ]

    _seqs += [
        (f"\033[8;{target_rows};{target_cols}t", 0.15),
        (f"\033[8;{r2};{c2}t",                  0.15),
        (f"\033[8;{target_rows};{target_cols}t", 0.25),
        (f"\033[4;{target_rows * 16};{target_cols * 8}t", 0.20),
        (f"\033[8;{target_rows};{target_cols}t\033[8;{target_rows};{target_cols}t", 0.30),
    ]

    for seq, pause in _seqs:
        _send(seq)
        time.sleep(pause)
        cur_c, cur_r = _get_size()
        if _big_enough(cur_c, cur_r):
            break

    # ── Phase 2b: Keyboard / module zoom fallback ────────────────────────
    # Prefer making the font BIGGER (fewer, larger characters) while keeping
    # enough rows/columns for the map. If the terminal is too small, fall back
    # to zooming out just enough to fit. Manual instructions are last resort.
    #
    # Supported platforms:
    #   Windows (native) — Win32 keybd_event
    #   WSL               — PowerShell SendKeys
    #   macOS             — osascript System Events keystroke
    #   Linux X11         — xdotool key (if installed)

    _VK_CTRL  = 0x11
    _VK_MINUS = 0xBD   # VK code for '-'
    _VK_PLUS  = 0xBB   # VK code for '='
    _VK_KEYUP = 0x0002

    def _send_ctrl_key_win32(vk):
        import ctypes as _ct
        _u = _ct.windll.user32
        _u.keybd_event(_VK_CTRL, 0, 0, 0)
        _u.keybd_event(vk, 0, 0, 0)
        _u.keybd_event(vk, 0, _VK_KEYUP, 0)
        _u.keybd_event(_VK_CTRL, 0, _VK_KEYUP, 0)

    def _send_ctrl_key_ps(vk_char):
        os.system(
            f'powershell.exe -NoProfile -Command "'
            f'Add-Type -AssemblyName System.Windows.Forms; '
            f'[System.Windows.Forms.SendKeys]::SendWait(\\\"^{vk_char}\\\")" 2>/dev/null'
        )

    def _send_key_macos(key_char, use_cmd=True):
        mod = "command" if use_cmd else "control"
        os.system(
            f"osascript -e 'tell application \"System Events\" "
            f"to keystroke \"{key_char}\" using {mod} down' 2>/dev/null"
        )

    def _send_key_xdotool(key_spec):
        os.system(f"xdotool key {key_spec} 2>/dev/null")

    def _send_key_pyautogui(combo):
        import pyautogui as _pag
        _pag.hotkey(*combo)

    def _send_key_pynput(combo):
        from pynput.keyboard import Controller, Key
        kb = Controller()
        key_map = {"ctrl": Key.ctrl, "cmd": Key.cmd, "minus": "-", "equal": "=", "plus": "+"}
        keys = [key_map.get(k, k) for k in combo]
        for k in keys: kb.press(k)
        for k in reversed(keys): kb.release(k)

    def _send_key_keyboard(combo):
        import keyboard as _keyboard
        key_map = {"cmd": "command", "equal": "=", "plus": "+", "minus": "-"}
        _keyboard.press_and_release("+".join(key_map.get(k, k) for k in combo))

    def _run_silent(argv, timeout=3.0):
        try:
            import subprocess as _sp
            return _sp.run(argv, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                           timeout=timeout, check=False).returncode == 0
        except Exception:
            return False

    _is_wsl = (sys.platform != "win32" and
               os.path.exists("/proc/version") and
               "microsoft" in open("/proc/version").read().lower())

    import shutil as _shutil

    def _send_vscode_command(command_id):
        """Resize VS Code integrated-terminal text by editing its settings.

        VS Code does not honor terminal window-resize escape codes, and most
        synthetic hotkeys are swallowed by the integrated terminal.  The
        reliable route is changing terminal.integrated.fontSize in the VS Code
        settings file; VS Code watches that file and resizes the terminal live.
        """
        is_out = "out" in str(command_id).lower() or "minus" in str(command_id).lower()
        delta = -1 if is_out else 1

        def _candidate_settings_paths():
            home = os.path.expanduser("~")
            paths = []
            appdata = os.environ.get("APPDATA")
            portable = os.environ.get("VSCODE_PORTABLE")
            if portable:
                paths += [os.path.join(portable, "data", "user-data", "User", "settings.json")]
            if sys.platform == "win32":
                base = appdata or os.path.join(home, "AppData", "Roaming")
                for product in ("Code", "Code - Insiders", "VSCodium", "Cursor", "Windsurf"):
                    paths.append(os.path.join(base, product, "User", "settings.json"))
            elif sys.platform == "darwin":
                base = os.path.join(home, "Library", "Application Support")
                for product in ("Code", "Code - Insiders", "VSCodium", "Cursor", "Windsurf"):
                    paths.append(os.path.join(base, product, "User", "settings.json"))
            else:
                xdg = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
                for product in ("Code", "Code - Insiders", "VSCodium", "Cursor", "Windsurf"):
                    paths.append(os.path.join(xdg, product, "User", "settings.json"))
                # Remote/server-side VS Code installs sometimes mirror machine settings here.
                for root in (".vscode-server", ".vscode-server-insiders", ".vscode-remote", ".cursor-server", ".windsurf-server"):
                    paths.append(os.path.join(home, root, "data", "Machine", "settings.json"))
            # Prefer existing files, then the normal product default for this platform.
            existing = [q for q in paths if os.path.exists(q)]
            missing = [q for q in paths if q not in existing]
            return existing + missing[:1]

        import re as _re
        last_err = None
        for settings_path in _candidate_settings_paths():
            try:
                os.makedirs(os.path.dirname(settings_path), exist_ok=True)
                try:
                    with open(settings_path, "r", encoding="utf-8") as f:
                        data = f.read()
                except FileNotFoundError:
                    data = ""
                m = _re.search(r'("terminal\.integrated\.fontSize"\s*:\s*)(\d+(?:\.\d+)?)', data)
                cur = float(m.group(2)) if m else 14.0
                nxt = max(6.0, min(36.0, cur + delta))
                val = str(int(nxt)) if float(nxt).is_integer() else str(nxt)
                if m:
                    data2 = data[:m.start(2)] + val + data[m.end(2):]
                else:
                    stripped = data.strip()
                    if not stripped:
                        data2 = '{\n    "terminal.integrated.fontSize": ' + val + '\n}\n'
                    else:
                        brace = data.rfind("}")
                        if brace < 0:
                            raise RuntimeError("settings.json has no closing brace")
                        before = data[:brace].rstrip()
                        after = data[brace:]
                        comma = "" if before.endswith("{") else ","
                        data2 = before + comma + '\n    "terminal.integrated.fontSize": ' + val + '\n' + after
                with open(settings_path, "w", encoding="utf-8") as f:
                    f.write(data2)
                time.sleep(0.45)
                return
            except Exception as exc:
                last_err = exc
        raise RuntimeError(f"VS Code font setting unavailable: {last_err}")

    def _kbd_loop(send_fn, send_arg, flip_arg=None):
        """Zoom out up to 14× until terminal is big enough."""
        nonlocal cur_c, cur_r
        _prev_area = cur_c * cur_r
        _cur_arg   = send_arg
        for _z in range(14):
            cur_c, cur_r = _get_size()
            if _big_enough(cur_c, cur_r):
                return True
            _area = cur_c * cur_r
            if _z == 1 and flip_arg and _prev_area > 0 and _area < _prev_area:
                _cur_arg = flip_arg   # font got bigger → flip direction
            _prev_area = _area
            try:
                send_fn(_cur_arg)
            except Exception:
                return False
            time.sleep(0.30)
        cur_c, cur_r = _get_size()
        return _big_enough(cur_c, cur_r)

    def _kbd_zoom_in_loop(send_fn, zoom_in_arg, zoom_out_arg):
        """Zoom in for larger tiles, but undo the last step if the map no longer fits."""
        nonlocal cur_c, cur_r
        cur_c, cur_r = _get_size()
        if not _big_enough(cur_c, cur_r):
            return False
        changed = False
        # Leave a small safety margin so the HUD/map does not wrap after zooming.
        for _z in range(10):
            prev_c, prev_r = cur_c, cur_r
            try:
                send_fn(zoom_in_arg)
            except Exception:
                return False
            time.sleep(0.30)
            cur_c, cur_r = _get_size()
            # If the terminal did not report a change, keep trying other fallbacks.
            if (cur_c, cur_r) == (prev_c, prev_r):
                continue
            changed = True
            if not _big_enough(cur_c, cur_r):
                try:
                    send_fn(zoom_out_arg)
                    time.sleep(0.30)
                except Exception:
                    pass
                cur_c, cur_r = _get_size()
                return _big_enough(cur_c, cur_r)
            if cur_c <= target_cols + 8 or cur_r <= target_rows + 3:
                return True
        cur_c, cur_r = _get_size()
        return changed and _big_enough(cur_c, cur_r)

    def _try_module_hotkeys(zoom_in=True):
        combos = []
        if sys.platform == "darwin":
            combos = [("cmd", "equal"), ("cmd", "plus")] if zoom_in else [("cmd", "minus")]
        else:
            combos = [("ctrl", "equal"), ("ctrl", "plus")] if zoom_in else [("ctrl", "minus")]
        for combo in combos:
            try:
                if _kbd_zoom_in_loop(_send_key_keyboard, combo, (combo[0], "minus")) if zoom_in else _kbd_loop(_send_key_keyboard, combo):
                    return True
            except Exception:
                pass
            try:
                if _kbd_zoom_in_loop(_send_key_pyautogui, combo, (combo[0], "minus")) if zoom_in else _kbd_loop(_send_key_pyautogui, combo):
                    return True
            except Exception:
                pass
            try:
                if _kbd_zoom_in_loop(_send_key_pynput, combo, (combo[0], "minus")) if zoom_in else _kbd_loop(_send_key_pynput, combo):
                    return True
            except Exception:
                pass
        return False

    def _try_vscode_commands(zoom_in=True):
        if not is_vscode:
            return False
        zin = "workbench.action.terminal.fontZoomIn"
        zout = "workbench.action.terminal.fontZoomOut"
        try:
            if zoom_in:
                return _kbd_zoom_in_loop(_send_vscode_command, zin, zout)
            return _kbd_loop(_send_vscode_command, zout, zin)
        except Exception:
            return False

    cur_c, cur_r = _get_size()
    if _big_enough(cur_c, cur_r):
        if _try_vscode_commands(zoom_in=True):
            return True
        if sys.platform == "win32":
            if _kbd_zoom_in_loop(_send_ctrl_key_win32, _VK_PLUS, _VK_MINUS):
                return True
        elif _is_wsl:
            if _kbd_zoom_in_loop(_send_ctrl_key_ps, "=", "-"):
                return True
        elif sys.platform == "darwin":
            if _kbd_zoom_in_loop(_send_key_macos, "+", "-"):
                return True
        elif sys.platform.startswith("linux") and _shutil.which("xdotool"):
            if _kbd_zoom_in_loop(_send_key_xdotool, "ctrl+equal", "ctrl+minus"):
                return True
        if _try_module_hotkeys(zoom_in=True):
            return True
        return True

    if _try_vscode_commands(zoom_in=False):
        return True
    if sys.platform == "win32":
        if _kbd_loop(_send_ctrl_key_win32, _VK_MINUS, _VK_PLUS):
            return True
    elif _is_wsl:
        if _kbd_loop(_send_ctrl_key_ps, "-", "="):
            return True
    elif sys.platform == "darwin":
        # macOS terminals use Cmd+- to shrink font; Cmd+= to grow it.
        if _kbd_loop(_send_key_macos, "-", "+"):
            return True
    elif sys.platform.startswith("linux") and _shutil.which("xdotool"):
        # Linux X11: xdotool simulates keystrokes to the focused window.
        if _kbd_loop(_send_key_xdotool, "ctrl+minus", "ctrl+equal"):
            return True
    if _try_module_hotkeys(zoom_in=False):
        return True

    # ── Phase 2c: Last-ditch — try to auto-install a keystroke module ────
    # If none of pyautogui / keyboard / pynput are importable, the
    # `_try_module_hotkeys` path above did nothing. Attempt a quiet pip
    # install and retry once. This is the "don't give up" phase.
    def _have(mod):
        try:
            __import__(mod); return True
        except Exception:
            return False

    if not (_have("pyautogui") or _have("keyboard") or _have("pynput")):
        for pkg in ("pyautogui", "pynput", "keyboard"):
            try:
                import subprocess as _sp
                _sp.run([sys.executable, "-m", "pip", "install",
                         "--quiet", "--disable-pip-version-check",
                         "--user", pkg],
                        timeout=45, check=False,
                        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                if _have(pkg):
                    break
            except Exception:
                pass
        # Retry module hotkeys after install attempt.
        try:
            if _try_module_hotkeys(zoom_in=False):
                return True
        except Exception:
            pass

    # ── Phase 3: stty (multiplexer-only; same false-positive caveat) ─────
    if _in_mux:
        try:
            os.system(f"stty rows {target_rows} cols {target_cols} 2>/dev/null")
            time.sleep(0.10)
            cur_c, cur_r = _get_size()
            if _big_enough(cur_c, cur_r):
                return True
        except Exception:
            pass

    # ── Phase 4: manual fallback ──────────────────────────────────────────
    # Tell the user exactly what key to press.  Goal: shrink the font so
    # MORE characters fit in the same window (the opposite of "zoom in").
    sys.stdout.write("\r\n")
    sys.stdout.flush()
    print()
    print("  📐 Graphics Mode: automatic terminal resize was not possible.")
    print(f"     Target  : {target_cols} columns × {target_rows} rows")
    print(f"     Current : {cur_c} columns × {cur_r} rows")
    print()
    print("  I tried automatic keyboard/module zoom first. As a last resort,")
    print("  adjust the terminal zoom/font until the map fits comfortably:")
    if is_iterm2:
        print("  💡 iTerm2         : Cmd+=/Cmd+- to adjust zoom")
    elif is_apple:
        print("  💡 Terminal.app   : Cmd+=/Cmd+- to adjust zoom, or drag the window larger")
    elif is_wt:
        print("  💡 Windows Terminal: Ctrl+=/Ctrl+- to adjust zoom, or drag the window larger")
    elif is_kitty:
        print("  💡 Kitty          : Ctrl+=/Ctrl+- to adjust zoom, or resize the window")
    elif is_vscode:
        print("  💡 VSCode terminal: adjust terminal.integrated.fontSize, or use Ctrl/Cmd+-")
    elif is_wezterm:
        print("  💡 WezTerm        : Ctrl+=/Ctrl+- to adjust zoom, or resize the window")
    else:
        print(f"  💡 Use Ctrl+=/Ctrl+- (or Cmd+=/Cmd+- on Mac) until you see ≥{target_rows} rows,")
        print("     or drag the window corner to make it larger, then press Enter.")
    print()
    try:
        if HAVE_TERMIOS and sys.stdin.isatty():
            sys.stdout.write("  Press Enter when ready (or Enter to play at current size): ")
            sys.stdout.flush()
            while True:
                ch = os.read(sys.stdin.fileno(), 1)
                if ch in (b"\r", b"\n"):
                    break
        else:
            input("  Press Enter when ready (or Enter to play at current size): ")
    except (EOFError, KeyboardInterrupt):
        pass
    cur_c, cur_r = _get_size()
    return _big_enough(cur_c, cur_r)

# Identified-item → map emoji. When a cluster is identified, prefer the
# specific icon so berries/mushrooms/etc. read at a glance. Unidentified
# clusters keep the generic GRID_BERRIES / GRID_MUSHROOMS icon.
_IDENTIFIED_ICON = {
    "wild_berries":       "🫐",
    "sweet_berries":      "🍬",
    "sour_berries":       "🍋",
    "glowing_berries":    "✨",
    "frostberry":         "🫐",
    "shimmer_frostberry": "✨",
    "poisonous_berry":    "☠️",
    "mushrooms":          "🍄",
    "black_trumpets":     "🖤",
    "spotted_mushrooms":  "🔴",
    "mushroom_death_cap": "☠️",
    "mystery_mushroom":   "✨",
    "moss_healing":       "💚",
    "moss_harmful":       "🌿",
    "moss_mystery":       "✨",
    "catnip":             "🌿",
    "bee_hive":           "🐝",
    "spider_silk":        "🕸️",
    "honey":              "🍯",
    "ironroot":           "🌱",
    "fibergrass":         "🌾",
    "snow":               "❄️",
}

def _cluster_icon(cl, default_icon):
    """Return the map emoji for a cluster, honoring is_identified."""
    if cl.get("is_identified"):
        item = cl.get("real_item", "")
        ico = _IDENTIFIED_ICON.get(item)
        if ico:
            return ico
    return default_icon


def _build_mini_map(player, world, map_w=17, map_h=11):
    """Build a mini-map panel showing the world around the player.
    Uses the same grid-mode tile constants (GRID_TREE, GRID_ROCK, etc.)
    so the map looks consistent with grid combat mode.
    Returns a list of strings (each an already-formatted display line).
    map_w / map_h: tile dimensions (each tile is 2 display cols wide).
    """
    # Grid-mode tile constants (resolved at call time — defined later in file)
    _EMPTY    = GRID_EMPTY
    _TREE     = GRID_TREE
    _ROCK     = GRID_ROCK
    _CATNIP   = GRID_CATNIP
    _BERRIES  = GRID_BERRIES
    _MUSHROOMS= GRID_MUSHROOMS
    _WATER    = GRID_WATER
    _GRASS    = GRID_GRASS
    _MOSS     = GRID_MOSS
    _RESOURCE = GRID_RESOURCE

    # Arctic background override
    px, py = _world_tile(player.x, player.y)
    try:
        in_forest = biome_at(px, py) == "Forest"
    except Exception:
        in_forest = True
    bg = _EMPTY if in_forest else "🟦"

    hw = map_w // 2
    hh = map_h // 2
    ox = px - hw
    oy = py - hh

    # Build cell grid: (gi, gj) → emoji string
    cells = {}
    for gj in range(map_h):
        for gi in range(map_w):
            cells[(gi, gj)] = bg

    # Clusters / resources
    clusters = world.clusters if world is not None else {}
    # Track which cluster was actually rendered onto the player's centre cell
    # so the tile label always matches the emoji the player sees underfoot.
    player_cluster = None
    for (cx, cy), cl in clusters.items():
        gi, gj = int(cx) - ox, int(cy) - oy
        if not (0 <= gi < map_w and 0 <= gj < map_h):
            continue
        item = cl.get("real_item", "")
        meta = cl.get("meta", {})
        if meta.get("is_burning"):
            icon = "🔥"
        elif meta.get("is_ash"):
            icon = "💨"
        elif item == "wood":
            icon = _TREE
        elif item == "rock":
            icon = _ROCK
        elif item in ("fresh_water", "dirty_water", "freezing_water", "arctic_water",
                      "freezing_dirty_water", "water"):
            icon = _WATER
        elif item.endswith("berries") or item.endswith("berry") or "berr" in item:
            icon = _cluster_icon(cl, _BERRIES)
        elif "mushroom" in item or item in ("black_trumpets", "spotted_mushrooms"):
            icon = _cluster_icon(cl, _MUSHROOMS)
        elif item in ("fibergrass", "snow"):
            icon = _cluster_icon(cl, _GRASS)
        elif item.startswith("moss"):
            icon = _cluster_icon(cl, _MOSS)
        elif item == "catnip":
            icon = _cluster_icon(cl, _CATNIP)
        elif item in ("bee_hive", "spider_silk"):
            icon = _cluster_icon(cl, _RESOURCE)
        else:
            icon = _cluster_icon(cl, _RESOURCE)
        cells[(gi, gj)] = icon
        if (gi, gj) == (hw, hh):
            player_cluster = cl

    # Houses
    for h in (world.houses if world is not None else []):
        if h.get("hp", 0) <= 0:
            continue
        icon = HOUSE_DEFS.get(h.get("type", ""), {}).get("emoji", "🏠")
        hgi, hgj = int(h["x"]) - ox, int(h["y"]) - oy
        if 0 <= hgi < map_w and 0 <= hgj < map_h:
            cells[(hgi, hgj)] = icon

    # Animals
    for a in (world.animals if world is not None else []):
        agi, agj = int(round(a["x"])) - ox, int(round(a["y"])) - oy
        if not (0 <= agi < map_w and 0 <= agj < map_h):
            continue
        icon = ANIMAL_DEFS.get(a.get("type", ""), {}).get("icon", "🐾")
        cells[(agi, agj)] = icon

    # Player marker (centre cell)
    if 0 <= hw < map_w and 0 <= hh < map_h:
        cells[(hw, hh)] = "⭐"

    # Render bordered box
    inner_w = map_w * 2
    border_top = "┌─ MAP " + "─" * max(0, inner_w - 6) + "┐"
    border_bot = "└" + "─" * inner_w + "┘"
    lines = [border_top]
    for gj in range(map_h):
        row = "│" + "".join(_cell2(cells.get((gi, gj), bg)) for gi in range(map_w)) + "│"
        lines.append(row)
    lines.append(border_bot)
    # Current-tile label — prefer the cluster the map actually drew under the
    # player, falling back to a direct key lookup so the label is always
    # consistent with the emoji at the player's tile.
    cur_cluster = player_cluster or clusters.get((px, py))
    if cur_cluster is None:
        for (cx, cy), cl in clusters.items():
            if int(cx) == px and int(cy) == py:
                cur_cluster = cl
                break
    if cur_cluster:
        if cur_cluster.get("is_identified"):
            tile_item = display_item_name(cur_cluster.get("real_item", ""))
            tile_qty  = cur_cluster.get("qty", 0)
            tile_info = f"{tile_item} (qty:{tile_qty})"
        else:
            tile_info = "❓ Unknown resource"
    else:
        tile_info = "🌲 Forest — clear" if in_forest else "❄️ Arctic — clear"
    lines.append(f"  📍 @({px},{py}): {tile_info}")
    return lines


# ==================== TERMINAL ====================
# ---------------------------------------------------------------------------
# Module-wide "active terminal" pointer so free functions (combat helpers,
# turret fire logic, etc.) can trigger screen flashes without having to
# thread `term` through their signatures.
# ---------------------------------------------------------------------------
_ACTIVE_TERM = None

def _flash_hit(target_type):
    """Flash the screen for a damage event on an entity.

    Grots  → red flash (already used for the human player).
    Others → yellow flash (animals: deer, bunny, squirrel, cat, …).
    Safe to call from anywhere; no-op if no Terminal is active.
    """
    t = _ACTIVE_TERM
    if t is None:
        return
    try:
        t.flash_for_target(target_type)
    except Exception:
        pass


class Terminal:
    def __init__(self):
        self.pause_context_player = None
        self.pause_context_world = None
        self.pause_context_weather = None
        self._red_flash_times = []
        self._yellow_flash_times = []
        self.using_windows_fallback = not HAVE_TERMIOS
        if self.using_windows_fallback:
            self.fd = None
            self.old = None
        else:
            self.fd = sys.stdin.fileno()
            self.old = termios.tcgetattr(self.fd)
        # Register as module-wide active terminal so helpers like
        # _flash_hit() can find us from anywhere in the game code.
        global _ACTIVE_TERM
        _ACTIVE_TERM = self

    def setup(self):
        if not self.using_windows_fallback:
            tty.setraw(self.fd)

    def cleanup(self):
        sys.stdout.write("\033[2J\033[1;1H\033[?25h\033[0m")
        if not self.using_windows_fallback:
            termios.tcsetattr(self.fd, termios.TCSANOW, self.old)
        sys.stdout.flush()

    def _theme_prefix(self, player=None):
        mode = getattr(self, "theme_mode", "dark")
        if mode == "day_night":
            if player and getattr(player, "time_of_day", "day") == "night":
                return "\033[40m\033[37m"
            return "\033[47m\033[30m"
        return "\033[40m\033[37m"

    def get_key(self, timeout=0.1):
        if self.using_windows_fallback:
            start = time.time()
            while time.time() - start < timeout:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch in ('\x00', '\xe0'):
                        seq = msvcrt.getwch()
                        if seq == 'H': return 'UP'
                        if seq == 'P': return 'DOWN'
                        if seq == 'M': return 'RIGHT'
                        if seq == 'K': return 'LEFT'
                        return None
                    return ch
            return None

        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r: return None
        try: char = os.read(self.fd, 1).decode('utf-8', errors='ignore')
        except: return None
        if not char: return None
        if char == '\x1b':
            r2, _, _ = select.select([self.fd], [], [], 0.05)
            if r2:
                seq = os.read(self.fd, 16).decode('utf-8', errors='ignore')
                key_result = None
                if seq.startswith("[A"): key_result = 'UP'
                elif seq.startswith("[B"): key_result = 'DOWN'
                elif seq.startswith("[C"): key_result = 'RIGHT'
                elif seq.startswith("[D"): key_result = 'LEFT'
                if key_result:
                    # Actively drain queued key-repeat bursts until the input
                    # has been quiet for a short settle window. This stops the
                    # "drift" where a single arrow press keeps moving you.
                    try:
                        idle_start = time.time()
                        while time.time() - idle_start < 0.06:
                            rr, _, _ = select.select([self.fd], [], [], 0.02)
                            if rr:
                                try: os.read(self.fd, 64)
                                except Exception: break
                                idle_start = time.time()  # reset settle timer
                        termios.tcflush(self.fd, termios.TCIFLUSH)
                    except Exception:
                        pass
                    return key_result
            return None
        return char

    def get_key_no_flush(self, timeout=0.1):
        if self.using_windows_fallback:
            start = time.time()
            while time.time() - start < timeout:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch in ('\x00', '\xe0'):
                        seq = msvcrt.getwch()
                        if seq == 'H': return 'UP'
                        if seq == 'P': return 'DOWN'
                        return None
                    if ch == '\x1b':
                        return 'ESC'
                    return ch
            return None

        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r: return None
        try: char = os.read(self.fd, 1).decode('utf-8', errors='ignore')
        except: return None
        if not char: return None
        if char == '\x1b':
            r2, _, _ = select.select([self.fd], [], [], 0.05)
            if r2:
                seq = os.read(self.fd, 16).decode('utf-8', errors='ignore')
                if seq.startswith("[A"):
                    try: termios.tcflush(self.fd, termios.TCIFLUSH)
                    except Exception: pass
                    return 'UP'
                if seq.startswith("[B"):
                    try: termios.tcflush(self.fd, termios.TCIFLUSH)
                    except Exception: pass
                    return 'DOWN'
            return 'ESC'
        return char

    def show_menu(self, lines):
        # Flicker-free repaint: home cursor and overwrite each line with EL (clear-to-EOL),
        # then ED (clear-to-EOS) to wipe any leftover rows. Avoids the \033[2J blank-then-draw flash.
        out = "\033[K\r\n".join(vfit(str(l), TERM_WIDTH) for l in lines)
        theme = self._theme_prefix(getattr(self, "pause_context_player", None))
        sys.stdout.write("\033[?25l\033[H" + theme + out + "\033[K\r\n\033[J\033[?25h"); sys.stdout.flush()

    def print_page(self, lines, wait=True):
        wait_started = time.time() if wait else None
        wrapped = []
        for l in lines:
            if l == "":
                wrapped.append("")
            else:
                wrapped.extend(vwrap(str(l), TERM_WIDTH))
        # Flicker-free repaint: overwrite in place instead of clearing first.
        out = "\033[K\r\n".join(vfit(str(l), TERM_WIDTH) for l in wrapped)
        if wait: out += "\033[K\r\n\033[K\r\n  [Press Enter to continue]"
        theme = self._theme_prefix(getattr(self, "pause_context_player", None))
        sys.stdout.write("\033[?25l\033[H" + theme + out + "\033[K\033[J\033[?25h"); sys.stdout.flush()
        if wait:
            while True:
                k = self.get_key_no_flush(0.5)
                if k in ('\r', '\n'): break
            freeze_blocking_time(self.pause_context_player, self.pause_context_world, self.pause_context_weather, time.time() - wait_started)
            sys.stdout.write("\033[H\033[J"); sys.stdout.flush()

    def flash_white(self):
        """Brief white-screen flash."""
        try: cols, rows = os.get_terminal_size()
        except: cols, rows = TERM_WIDTH, 24
        sys.stdout.write("\033[2J\033[H\033[47m\033[30m")
        for _ in range(rows):
            sys.stdout.write((" " * cols) + "\n")
        sys.stdout.write("\033[0m"); sys.stdout.flush()
        time.sleep(0.05)
        sys.stdout.write("\033[2J\033[0m"); sys.stdout.flush()

    def flash_red(self):
        """Brief red-screen flash for damage events (lightning, tornado)."""
        now = time.time()
        self._red_flash_times = [t for t in getattr(self, "_red_flash_times", []) if now - t < 5.0]
        if len(self._red_flash_times) >= 3:
            return
        self._red_flash_times.append(now)
        try: cols, rows = os.get_terminal_size()
        except: cols, rows = TERM_WIDTH, 24
        sys.stdout.write("\033[2J\033[H\033[41m\033[97m")
        for _ in range(rows):
            sys.stdout.write((" " * cols) + "\n")
        sys.stdout.write("\033[0m"); sys.stdout.flush()
        time.sleep(0.05)
        sys.stdout.write("\033[2J\033[0m"); sys.stdout.flush()

    def flash_yellow(self):
        """Brief yellow-screen flash used when a non-grot animal is hit."""
        now = time.time()
        self._yellow_flash_times = [t for t in getattr(self, "_yellow_flash_times", []) if now - t < 5.0]
        if len(self._yellow_flash_times) >= 3:
            return
        self._yellow_flash_times.append(now)
        try: cols, rows = os.get_terminal_size()
        except: cols, rows = TERM_WIDTH, 24
        # \033[43m = yellow bg, \033[30m = black fg for contrast
        sys.stdout.write("\033[2J\033[H\033[43m\033[30m")
        for _ in range(rows):
            sys.stdout.write((" " * cols) + "\n")
        sys.stdout.write("\033[0m"); sys.stdout.flush()
        time.sleep(0.05)
        sys.stdout.write("\033[2J\033[0m"); sys.stdout.flush()

    def flash_for_target(self, target_type):
        """Grots flash red, other creatures (animals, cats) flash yellow."""
        try:
            t = (target_type or "").lower()
            if t in ("grot", "grot_leader"):
                self.flash_red()
            else:
                self.flash_yellow()
        except Exception:
            pass

    def _render_graphics_mode(self, msg, prompt, buf, player, paused, world):
        """Two-panel Graphics Mode renderer.
        Left  : live map (20×20 classic OR adaptive to terminal).
        Right : stats, optional commands panel, tile info, prompt.
        Player emoji changes based on movement/weapon/shield state.
        Frame 1 (even second): player=🟦, grots=🟥, animals blink.
        Frame 2 (odd second) : normal emojis; fallback frame2 = □.
        """
        theme = self._theme_prefix(player)
        try:
            cols, term_h = os.get_terminal_size()
        except Exception:
            cols, term_h = 88, 22
        if term_h < 5:
            term_h = 5

        # ── ANSI colour support detection (cached on player) ──────────────
        if not hasattr(player, "_ansi_blink_ok"):
            ct = os.environ.get("COLORTERM", "").lower()
            tv = os.environ.get("TERM", "").lower()
            player._ansi_blink_ok = bool(ct in ("truecolor","24bit") or
                                         "color" in tv or "xterm" in tv or
                                         "kitty" in tv or "iterm" in tv or
                                         os.environ.get("KITTY_WINDOW_ID"))

        # Which blink frame: alternates every ~0.6 seconds (gentler blink to
        # avoid whole-screen flicker on slower terminals).
        _frame1 = (int(time.time() * 1.6) % 2 == 0)

        # ── Player emoji state ────────────────────────────────────────────
        _now = time.time()
        _last_mv = getattr(player, "last_move_time", 0.0)
        _moving   = (_now - _last_mv) < 0.75
        _has_spear = (getattr(player, "spear_type", None) is not None and
                      getattr(player, "spear_dur", 0) > 0)
        _has_shield = (getattr(player, "shield_type", None) is not None and
                       getattr(player, "shield_dur_blocks", 0) > 0)
        if _moving:
            _PLAYER_EMOJI = "🚶"
        elif _has_shield:
            _PLAYER_EMOJI = "🛡️"
        elif _has_spear:
            _PLAYER_EMOJI = "🗡️"  # U+1F5E1 dagger — 2-wide; ⚔️ U+2694 is 1-wide in many terminals
        else:
            _PLAYER_EMOJI = "🧍"

        # ── Map dimensions: classic 20×20 or adaptive ─────────────────────
        _adaptive = getattr(player, "graphics_adaptive", False)
        if _adaptive:
            # Wider terminal → wider map.
            # Each emoji tile is 2 display-cols wide, 1 row tall.
            # Reserve ~40 cols for the right stats panel + separator + borders.
            _reserved_w = 40
            _max_map_w = max(10, (cols - _reserved_w) // 2)   # tiles wide
            _max_map_h = max(6,  term_h - 2)                   # tiles tall
            # Scale BOTH dimensions proportionally to stay ≤ 400 tiles.
            # This preserves the terminal's natural wide-vs-tall ratio so a
            # wider terminal always yields a wider map.
            if _max_map_w * _max_map_h > 400:
                _scale = (400 / (_max_map_w * _max_map_h)) ** 0.5
                _max_map_w = max(10, int(_max_map_w * _scale))
                _max_map_h = max(6,  int(_max_map_h * _scale))
                # Trim any remaining single-tile excess from height only
                while _max_map_w * _max_map_h > 400 and _max_map_h > 6:
                    _max_map_h -= 1
            # Prevent the map from overflowing the terminal vertically
            _max_map_h = min(_max_map_h, term_h - 2)
            # Guard against too-narrow maps (tile ratio < 0.6 means portrait)
            if _max_map_w / max(1, _max_map_h) < 0.6:
                _max_map_w = max(10, int(_max_map_h * 0.6))
            MAP_TILE_W = _max_map_w
            MAP_TILE_H = _max_map_h
        else:
            MAP_TILE_W = 20
            MAP_TILE_H = 20

        map_panel_w = MAP_TILE_W * 2 + 2   # 2 display cols per emoji + │…│

        px, py = _world_tile(player.x, player.y)
        try:
            in_forest = biome_at(px, py) == "Forest"
        except Exception:
            in_forest = True
        bg_empty = GRID_EMPTY if in_forest else "🟦"

        # Player always at centre
        hw = MAP_TILE_W // 2
        hh = MAP_TILE_H // 2
        ox = px - hw
        oy = py - hh

        # ── Build cell grid ───────────────────────────────────────────────
        cells = {}
        for gj in range(MAP_TILE_H):
            for gi in range(MAP_TILE_W):
                cells[(gi, gj)] = bg_empty

        clusters = getattr(world, "clusters", {}) or {}
        # ── Real-map layer ────────────────────────────────────────────────
        # Build a single authoritative map: (tile_x, tile_y) → cluster.
        # The emoji renderer AND the tile-info panel both read from THIS
        # dict, so the emoji under the player can never disagree with the
        # description of what the player is standing on. Last write wins
        # when multiple clusters share an integer tile, exactly matching
        # what a player visually sees on that tile.
        tile_real_at = {}
        for (cx, cy), cl in clusters.items():
            tile_real_at[(int(cx), int(cy))] = cl

        # Track which cluster was rendered onto the player's centre tile so
        # the tile label always agrees with the emoji the player stands on.
        player_cluster_gfx = tile_real_at.get((px, py))
        for (tx, ty), cl in tile_real_at.items():
            gi, gj = tx - ox, ty - oy
            if not (0 <= gi < MAP_TILE_W and 0 <= gj < MAP_TILE_H):
                continue
            item = cl.get("real_item", "")
            meta = cl.get("meta", {})
            if meta.get("is_burning"):
                icon = "🔥"
            elif meta.get("is_ash"):
                icon = "💨"
            elif item == "wood":
                icon = GRID_TREE
            elif item == "rock":
                icon = GRID_ROCK
            elif item in ("fresh_water", "dirty_water", "freezing_water",
                          "arctic_water", "freezing_dirty_water", "water"):
                icon = GRID_WATER
            elif item.endswith("berries") or item.endswith("berry") or "berr" in item:
                icon = _cluster_icon(cl, GRID_BERRIES)
            elif "mushroom" in item or item in ("black_trumpets", "spotted_mushrooms"):
                icon = _cluster_icon(cl, GRID_MUSHROOMS)
            elif item in ("fibergrass", "snow"):
                icon = _cluster_icon(cl, GRID_GRASS)
            elif item.startswith("moss"):
                icon = _cluster_icon(cl, GRID_MOSS)
            elif item == "catnip":
                icon = _cluster_icon(cl, GRID_CATNIP)
            else:
                icon = _cluster_icon(cl, GRID_RESOURCE)
            cells[(gi, gj)] = icon


        for h in getattr(world, "houses", []) or []:
            if h.get("hp", 0) <= 0:
                continue
            icon = HOUSE_DEFS.get(h.get("type", ""), {}).get("emoji", "🏠")
            hgi, hgj = int(h["x"]) - ox, int(h["y"]) - oy
            if 0 <= hgi < MAP_TILE_W and 0 <= hgj < MAP_TILE_H:
                cells[(hgi, hgj)] = icon

        # Track grot & animal cells for blink colouring
        _grot_cells = set()
        _animal_cells = {}
        for a in getattr(world, "animals", []) or []:
            agi = int(round(a["x"])) - ox
            agj = int(round(a["y"])) - oy
            if not (0 <= agi < MAP_TILE_W and 0 <= agj < MAP_TILE_H):
                continue
            atype = a.get("type", "")
            if atype in ("grot", "grot_leader"):
                icon = ANIMAL_DEFS.get(atype, {}).get("icon", "👹")
                _grot_cells.add((agi, agj))
            else:
                icon = ANIMAL_DEFS.get(atype, {}).get("icon", "🐾")
                _animal_cells[(agi, agj)] = icon
            cells[(agi, agj)] = icon

        # Place player at centre
        cells[(hw, hh)] = _PLAYER_EMOJI

        # ── Build map rows with blink colours ────────────────────────────
        def _cell_display(gi, gj, raw_icon):
            """Frame-alternating highlight for grots and animals.
            Player never blinks (removes the main source of screen flicker)."""
            if (gi, gj) == (hw, hh):
                return raw_icon
            if (gi, gj) in _grot_cells:
                if _frame1 and player._ansi_blink_ok:
                    return "🟥"
                return raw_icon
            if (gi, gj) in _animal_cells:
                if _frame1 and player._ansi_blink_ok:
                    return "🟡"
                return raw_icon
            return raw_icon

        header_dashes = max(0, MAP_TILE_W * 2 - 6)
        map_lines = ["┌─ MAP " + "─" * header_dashes + "┐"]
        for gj in range(MAP_TILE_H):
            row = "│"
            for gi in range(MAP_TILE_W):
                raw = cells.get((gi, gj), bg_empty)
                # _cell2 forces every cell to exactly 2 terminal columns so
                # rows stay aligned when emoji widths differ across terminals.
                row += _cell2(_cell_display(gi, gj, raw))
            row += "│"
            map_lines.append(row)
        map_lines.append("└" + "─" * (MAP_TILE_W * 2) + "┘")

        while len(map_lines) < term_h:
            map_lines.append(" " * map_panel_w)

        # ── Right panel ───────────────────────────────────────────────────
        right_w = max(10, cols - map_panel_w - 3)   # 3 = " │ " separator

        # ── TOP SECTION ───────────────────────────────────────────────────
        # Split into ESSENTIAL rows (always shown) and OPTIONAL rows
        # (dropped from the end first when the terminal is short so the
        # vitals and bottom prompt never get truncated).
        essential = []
        optional  = []

        essential.append(vfit("  🪐 9 PLANETS", right_w))
        essential.append(vfit("─" * right_w, right_w))

        # Row: Day/Night + Day counter + Biome + distance to border
        try:
            day_label = "🌙 NIGHT" if player.time_of_day == "night" else "☀️ DAY"
            _bm_lbl   = "🌲 Forest" if in_forest else "❄️ Arctic"
            try:
                _brd_d   = int(dist_to_border(px, py))
                _brd_lbl = f"  🧭{_brd_d:+d}m"
            except Exception:
                _brd_lbl = ""
            essential.append(vfit(f"  {day_label}  Day {int(getattr(player,'day',1))}  {_bm_lbl}{_brd_lbl}", right_w))
        except Exception:
            essential.append(" " * right_w)

        # Vital stats — ESSENTIAL. Compressed to fit on 2 rows even in
        # narrow panels. Always render regardless of space pressure.
        try:
            hp  = float(player.health);   mhp = float(player.max_health)
            hun = float(player.hunger);   thi = float(player.thirst)
            ene = float(player.energy);   fat = float(player.fatigue)
        except Exception:
            hp = mhp = hun = thi = ene = fat = 0.0

        if is_light(player):
            essential.append(vfit(f"  ❤️ {int(hp)}/{int(mhp)}  🍖 {int(hun)}", right_w))
            essential.append(vfit(f"  ⚡ {int(ene)}", right_w))
        else:
            essential.append(vfit(f"  ❤️ {int(hp)}/{int(mhp)}  🍖 {int(hun)}  💧 {int(thi)}", right_w))
            essential.append(vfit(f"  ⚡ {int(ene)}  😴 {int(fat)}", right_w))

        # Temperature + Coins + Points — ESSENTIAL (one line)
        try:
            temp_str = _temp_label(player.temp, player)
        except Exception:
            temp_str = "?°"
        try:
            coins  = int(player.coins)
            points = int(getattr(player, "points", 0))
        except Exception:
            coins = 0; points = 0
        essential.append(vfit(f"  🌡 {temp_str}  💰 {coins}  🏆 {points}", right_w))

        # ---- Below here is OPTIONAL: dropped from the end if space is tight ----

        # Player state + equipped armor
        state_icons = {"🧍": "Idle", "🚶": "Moving", "🗡️": "Armed", "🛡️": "Shielded"}
        _state_lbl  = state_icons.get(_PLAYER_EMOJI, "")
        _armor      = getattr(player, "wearing", None) or ""
        _armor_disp = {"light_armor": "🛡️Lite", "medium_armor": "🛡️Med",
                       "heavy_armor": "🛡️Hvy"}.get(_armor, "")
        _armor_dur  = getattr(player, "armor_dur", 0)
        if _armor_disp and _armor_dur > 0:
            _armor_disp += f"({int(_armor_dur)})"
        _state_str = f"  {_PLAYER_EMOJI} {_state_lbl}"
        if _armor_disp:
            _state_str += f"  {_armor_disp}"
        optional.append(vfit(_state_str, right_w))

        # Equipped spear
        try:
            _spear_t = getattr(player, "spear_type", None)
            if _spear_t:
                _sdur = getattr(player, "spear_dur", 0)
                _smax = SPEAR_DEFS.get(_spear_t, {}).get("dur", 100)
                _spct = int(100 * max(0, _sdur) / max(1, _smax))
                _sico = SPEAR_DEFS.get(_spear_t, {}).get("icon", "🗡️")
                _spois = " ☠️" if getattr(player, "spear_poison_strikes", 0) > 0 else ""
                _sname = _spear_t.replace("_", " ").title()
                optional.append(vfit(f"  {_sico} {_sname} {_spct}%{_spois}", right_w))
        except Exception:
            pass

        # Diseases
        try:
            _dz = getattr(player, "diseases", {}) or {}
            if _dz:
                optional.append(vfit("  ☣️  " + ", ".join(DISEASE_DISPLAY.get(d, d) for d in _dz), right_w))
        except Exception:
            pass

        # Active crafting task
        try:
            if player.active_tasks:
                t   = player.active_tasks[0]
                rem = (t.get("paused_remaining", max(0, int(t.get("end", 0) - time.time())))
                       if paused else max(0, int(t.get("end", 0) - time.time())))
                optional.append(vfit(f"  🔨 {t['item'].replace('_',' ').title()} ({rem}s)", right_w))
        except Exception:
            pass

        # Resting state
        try:
            if getattr(player, "resting", False):
                _rest_icon = {"campfire": "🔥", "house_bed": "🛏️",
                              "house_floor": "🏠"}.get(getattr(player, "rest_mode", ""), "😴")
                optional.append(vfit(f"  {_rest_icon} Resting…", right_w))
        except Exception:
            pass

        # Paused flag + trap status
        if paused:
            optional.append(vfit("  ⏸️  PAUSED", right_w))
        try:
            setting_t = sum(1 for tr in (player.traps or []) if tr.get("status") == "setting")
            caught_t  = sum(1 for tr in (player.traps or []) if tr.get("status") == "caught")
            if caught_t or setting_t:
                _tp = []
                if caught_t:  _tp.append(f"🟢{caught_t} ready")
                if setting_t: _tp.append(f"⏳{setting_t} setting")
                optional.append(vfit("  🪤 " + "  ".join(_tp), right_w))
        except Exception:
            pass

        # Messages — word-wrapped so nothing is truncated
        _msg_rows = []
        try:
            recent = [m for m in (msg or []) if m.strip()][-3:]
            if recent:
                _msg_rows.append(vfit("  💬", right_w))
                _wrap_w = max(1, right_w - 4)
                for m in recent:
                    for wl in vwrap(m, _wrap_w)[:2]:
                        _msg_rows.append(vfit("    " + wl, right_w))
        except Exception:
            pass
        optional.append(" " * right_w)
        optional.extend(_msg_rows)

        # Compose top with priority: essential always, optional truncated
        # from the end if it won't fit alongside bottom (2 rows) + cmd panel.
        # Reserve at least 2 rows for bottom (tile info + prompt).
        _bottom_reserve = 2
        _max_top = max(len(essential), term_h - _bottom_reserve)
        _room_for_optional = max(0, _max_top - len(essential))
        top = essential + optional[:_room_for_optional]


        # ── BOTTOM SECTION ────────────────────────────────────────────────
        # Single source of truth: whatever cluster the emoji renderer put
        # under the player is exactly what the tile-info panel describes.
        cur_cluster = player_cluster_gfx
        try:
            if cur_cluster and cur_cluster.get("is_identified"):
                tile_desc = f"{display_item_name(cur_cluster.get('real_item',''))} x{cur_cluster.get('qty',0)}"
            elif cur_cluster:
                _ri  = cur_cluster.get("real_item", "") or ""
                _qty = cur_cluster.get("qty", 0)
                _ri_l = _ri.lower()
                if any(w in _ri_l for w in ("berr", "berry")):
                    _cat = "Berries"
                elif any(w in _ri_l for w in ("mushroom", "trumpet", "cap")):
                    _cat = "Mushroom"
                elif _ri_l == "wood":
                    _cat = "Wood"
                elif _ri_l == "rock":
                    _cat = "Rock"
                elif any(w in _ri_l for w in ("water", "drink")):
                    _cat = "Water Source"
                elif any(w in _ri_l for w in ("moss",)):
                    _cat = "Moss"
                elif any(w in _ri_l for w in ("fiber", "grass", "herb", "snow")):
                    _cat = "Plants"
                elif any(w in _ri_l for w in ("catnip", "nip")):
                    _cat = "Herb"
                else:
                    _cat = "Resource"
                tile_desc = f"❓ Unknown {_cat}.  Qty: {_qty}"
            else:
                tile_desc = "Forest — clear" if in_forest else "Arctic — clear"
        except Exception:
            tile_desc = "?"

        try:
            setting_t = sum(1 for tr in (player.traps or []) if tr.get("status") == "setting")
            caught_t  = sum(1 for tr in (player.traps or []) if tr.get("status") == "caught")
            trap_parts = []
            if caught_t:  trap_parts.append(f"🟢{caught_t}")
            if setting_t: trap_parts.append(f"⏳{setting_t}")
            trap_pfx = f"🪤 {' '.join(trap_parts)} " if trap_parts else ""
        except Exception:
            trap_pfx = ""

        prompt_pfx  = trap_pfx + prompt
        avail_buf   = max(0, right_w - vlen(prompt_pfx))
        buf_visible = vtrunc(buf, avail_buf)

        bottom = [
            vfit(f"  📍 @({px},{py}): {tile_desc}", right_w),
            vfit(f"{prompt_pfx}{buf_visible}", right_w),
        ]

        # ── MIDDLE SECTION: optional commands panel ───────────────────────
        show_cmds = getattr(player, "show_commands", True)
        available = max(0, term_h - len(top) - len(bottom))
        cmd_lines = []

        # Which tab index is active (from game loop via player transient attr)
        _gm_tab_idx = getattr(player, "_gm_tab_idx", -1)
        # Build flat list of typeable command tokens matching _TAB_CMDS order
        _tab_cmd_tokens = [
            tok for _raw, _ in SIDEBAR_COMMANDS
            for tok in [_raw.split("/")[0].split("<")[0].strip()]
            if tok and any(c.isalpha() for c in tok)
        ]

        if show_cmds:
            # Header always shows the current tab selection when active
            if 0 <= _gm_tab_idx < len(_tab_cmd_tokens):
                _tab_hint = f" ↹ {_tab_cmd_tokens[_gm_tab_idx]}"
            else:
                _tab_hint = " ↹=cycle"
            cmd_lines.append(vfit(f"  📜 COMMANDS{_tab_hint}", right_w))
            cmd_lines.append(vfit("  " + "─" * max(0, right_w - 2), right_w))
            # Single-column layout — one command per line with its description.
            # Prefix the currently tab-selected command with ▶ for visibility.
            ck_w = max(6, min(20, right_w // 3))
            cd_w = max(1, right_w - ck_w - 4)
            # Compute scroll offset so the tab-highlighted command is always visible
            _content_h = max(1, available - 2)   # 2 rows used by header + separator
            _all_scmds = list(SIDEBAR_COMMANDS)
            if 0 <= _gm_tab_idx < len(_tab_cmd_tokens):
                _tab_tok = _tab_cmd_tokens[_gm_tab_idx]
                _hi_idx = next(
                    (i for i, (_rc, _) in enumerate(_all_scmds)
                     if _rc.split("/")[0].split("<")[0].strip() == _tab_tok),
                    0
                )
                # Keep highlighted row in the middle third of the visible area
                _scroll_off = max(0, _hi_idx - _content_h // 3)
                # Don't scroll past the end
                _scroll_off = min(_scroll_off, max(0, len(_all_scmds) - _content_h))
            else:
                _scroll_off = 0
            _visible_cmds = _all_scmds[_scroll_off:]
            # Scroll indicator
            if _scroll_off > 0:
                cmd_lines.append(vfit(f"  ▲ {_scroll_off} more above", right_w))
            for _raw_cmd, _desc in _visible_cmds:
                if len(cmd_lines) >= available:
                    break
                _tok = _raw_cmd.split("/")[0].split("<")[0].strip()
                _is_tab = (any(c.isalpha() for c in _tok) and
                           0 <= _gm_tab_idx < len(_tab_cmd_tokens) and
                           _tab_cmd_tokens[_gm_tab_idx] == _tok)
                _pfx = "▶ " if _is_tab else "  "
                _line = _pfx + vfit(_raw_cmd, ck_w) + " " + vfit(_desc, cd_w)
                cmd_lines.append(vfit(_line, right_w))
            _remaining = len(_all_scmds) - _scroll_off - len(_visible_cmds[:_content_h])
            if _remaining > 0 and len(cmd_lines) < available:
                cmd_lines.append(vfit(f"  ▼ {_remaining} more below  (↹ to scroll)", right_w))
        else:
            cmd_lines.append(vfit("  📜 COMMANDS hidden  (↹ still cycles)", right_w))
            cmd_lines.append(vfit("  type 'commands' to show panel", right_w))

        while len(cmd_lines) < available:
            cmd_lines.append(" " * right_w)
        cmd_lines = cmd_lines[:available]

        right = (top + cmd_lines + bottom)[:term_h]

        # ── Combine panels and write ──────────────────────────────────────
        # vfit on both sides guarantees the │ separator is always at the same
        # column regardless of emoji-width variance in the map tile cells.
        sep = " │ "
        out = []
        for i in range(term_h):
            left_s  = map_lines[i] if i < len(map_lines) else " " * map_panel_w
            right_s = right[i]     if i < len(right)     else " " * right_w
            out.append(vfit(left_s, map_panel_w) + sep + vfit(right_s, right_w))

        final = "\033[?25l\033[H" + theme + "\033[H" + "\033[K\r\n".join([vtrunc(str(l), cols).rstrip() for l in out]) + "\033[K"
        sys.stdout.write(final + "\033[J")

        # ── ANSI absolute-position fixup for map cells ────────────────────
        # Terminal emoji fonts often render individual glyphs a pixel or two
        # wider/narrower than exactly 2 character cells.  With sequential
        # output that error accumulates across a row: a tile at column 13
        # can end up visually at column 12 or 14, making up/down movement
        # land on the wrong tile visually.
        #
        # Fix: after the normal screen paint, re-write every map cell using
        # an explicit \033[row;col H absolute cursor-move.  Each cell is
        # pinned to its exact grid column regardless of how the terminal
        # rendered earlier cells in the same row.  The right border │ is
        # re-stamped last so a wide final-cell glyph cannot bleed into the
        # right panel.
        _mfx = []
        for _gj in range(MAP_TILE_H):
            _row = _gj + 2          # ANSI 1-indexed row (row 1 = ┌─ MAP…┐)
            for _gi in range(MAP_TILE_W):
                _col = 2 + _gi * 2  # ANSI 1-indexed col (col 1 = left │)
                _ic  = _cell2(_cell_display(_gi, _gj,
                               cells.get((_gi, _gj), bg_empty)))
                _mfx.append(f"\033[{_row};{_col}H{_ic}")
            # Re-stamp the right border: col = map_panel_w (= MAP_TILE_W*2+2)
            _mfx.append(f"\033[{_row};{map_panel_w}H│")
        sys.stdout.write("".join(_mfx))

        # Position cursor at end of prompt on the very last row
        prompt_row  = term_h
        cursor_col  = map_panel_w + len(sep) + vlen(prompt_pfx) + vlen(buf_visible) + 1
        cursor_col  = max(1, min(cols, cursor_col))
        sys.stdout.write(f"\033[{prompt_row};{cursor_col}H\033[?25h")
        sys.stdout.flush()

    def render_main(self, header, scan, msg, prompt, buf, player=None, paused=False):
        # Graphics Mode: completely bypass the normal renderer.
        if player is not None and getattr(player, "graphics_mode", False):
            _gm_world = getattr(self, "pause_context_world", None) or _g_world
            try:
                self._render_graphics_mode(msg, prompt, buf, player, paused, _gm_world)
            except Exception as _gm_err:
                import traceback as _tb
                _err_txt = _tb.format_exc()
                try:
                    with open("/tmp/9p_gm_err.txt", "w") as _f:
                        _f.write(_err_txt)
                except Exception:
                    pass
                try:
                    sys.stdout.write(f"\033[H\033[2J\033[1;1H  [GM ERROR — see /tmp/9p_gm_err.txt]\r\n  {_gm_err}\r\n  Press any key…")
                    sys.stdout.flush()
                except Exception:
                    pass
            # ALWAYS return — never fall through to normal mode in graphics mode.
            return

        # Flicker-free repaint: hide cursor and home instead of clearing the whole screen.
        # The frame below is padded to terminal height and every line ends with \033[K,
        # then \033[J wipes anything below — no blank-then-draw flash while typing.
        theme = self._theme_prefix(player)
        sys.stdout.write("\033[?25l\033[H" + theme)
        try: cols, term_h = os.get_terminal_size()
        except: cols, term_h = TERM_WIDTH, 24
        term_w = max(20, cols)  # Actual terminal width without capping
        # Leave a safety margin so emoji-width differences between Python and
        # the terminal cannot auto-wrap lines and scroll the top HUD off-screen.
        draw_w = max(1, term_w - 8)
        if term_h < 3: term_h = 3
        # If caller didn't provide a proper HUD header (e.g. during overlays),
        # synthesize a minimal top HUD from `player` so stats/biome always show.
        if player is not None:
            has_header = bool(header and any(tok in (header[0] or "") for tok in ("@(", "DAY", "NIGHT", "🌙", "☀️")))
            if not has_header:
                try:
                    day_label = '🌙 NIGHT' if player.time_of_day == 'night' else '☀️ DAY'
                    biome_label = '🌲 Forest' if biome_at(player.x, player.y) == 'Forest' else '❄️ Arctic'
                    dist_lbl = ('↗️' if dist_to_border(player.x, player.y) > 0 else '↙️') + str(abs(int(dist_to_border(player.x, player.y))))
                    h1 = f"{day_label} | 📍@({player.x},{player.y}) | {biome_label} | 🧭{dist_lbl}"
                    h2 = (f"❤️{player.health:.0f} | 🍽️{player.hunger:.0f} | ⚡{int(player.energy)}" if is_light(player) else f"❤️{player.health:.0f} | 🍽️{player.hunger:.0f} | 💧{player.thirst:.0f} | ⚡{int(player.energy)} | 😴{int(player.fatigue)}")
                    h3 = f"🪙{player.coins:.0f} | 📚{player.inventory.get('textbook',0)} | { _temp_label(player.temp, player) }"
                    _dz = getattr(player, "diseases", {}) or {}
                    if _dz:
                        _dlbl = ", ".join(DISEASE_DISPLAY.get(d,d) + (f" x{v['stacks']}" if v.get('stacks',1)>1 else "") for d,v in _dz.items())
                        h4 = f"☣️ {_dlbl}"
                        header = [h1, h2, h3, h4] + (header or [])
                    else:
                        header = [h1, h2, h3] + (header or [])
                except Exception:
                    header = header or []
        # ---- Build the "bottom block" first (msg, status, prompt) so we can
        # reserve the exact rows it needs and only ever drop scan/cluster rows
        # to fit the terminal. This guarantees the HUD header and bottom info
        # bars ALL stay visible at all times (including when paused). ----
        bottom = []
        bottom.append("─" * draw_w)
        bottom.extend(msg[-3:])
        bottom.append("")
        if player and player.active_tasks:
            t = player.active_tasks[0]
            if "paused_remaining" in t:
                rem = t["paused_remaining"]
                tag = "⏸ PAUSED"
            elif paused:
                rem = t.get("paused_remaining", max(0, int(t["end"] - time.time())))
                tag = "⏸ PAUSED"
            else:
                rem = max(0, int(t["end"] - time.time()))
                tag = "movement locked"
            bottom.append(f"🔨 Crafting: {t['item'].replace('_',' ').title()} ({rem}s) — {tag}")
        # Gather-all countdown
        if player and getattr(player, "gather_all", None):
            ga = player.gather_all
            if player.in_combat or getattr(player, "resting", False):
                rem = ga.get("paused_remaining", max(0, int(ga["end"] - time.time())))
                bottom.append(f"⏳ Gather all paused ({rem}s remaining)")
            else:
                rem = max(0, int(ga["end"] - time.time()))
                bottom.append(f"⏳ Gather all: {rem}s remaining — actions locked")
        trap_status = ""
        if paused:
            bottom.append("⏸️ GAME PAUSED — time, weather, and auto-walk are frozen until you resume.")
        elif player and player.resting:
            _rm = player.rest_mode
            if _rm == "campfire":
                mode = "🔥 Campfire"; fuel = f" | 🪵{player.campfire_fuel} fuel left"
            elif _rm == "house_bed":
                mode = "🛏️ Bed"; fuel = " | no damage, ×1.3 recovery"
            elif _rm == "house_floor":
                mode = "🏠 House floor"; fuel = " | no damage"
            else:
                mode = "😴 Floor"; fuel = ""
            bottom.append(f"{mode} REST active: +30😴/hr{fuel} — type 'rest' to stop")
        elif player and player.traps:
            setting = sum(1 for t in player.traps if t.get('status') == 'setting')
            caught  = sum(1 for t in player.traps if t.get('status') == 'caught')
            parts = []
            if caught:  parts.append(f"🟢{caught} CAUGHT!")
            if setting: parts.append(f"⏳{setting} setting")
            trap_status = " | ".join(parts) if parts else ""
        bottom.append(" " * draw_w)
        # Prompt + buf
        prompt_with_trap = prompt
        if trap_status:
            prompt_with_trap = f"🪤 {trap_status} {prompt}"
        buf_to_show = ""
        try:
            if vlen(buf) == 0:
                prompt_disp = prompt_with_trap
                buf_to_show = ""
            else:
                avail = draw_w - vlen(prompt_with_trap)
                if avail <= 0:
                    prompt_disp = vtrunc(prompt_with_trap, max(0, draw_w - 1))
                    buf_to_show = vtrunc(buf[-15:], avail)
                else:
                    prompt_disp = prompt_with_trap
                    buf_to_show = vtrunc(buf, avail)
        except Exception:
            prompt_disp = prompt_with_trap; buf_to_show = vtrunc(buf, draw_w)
        bottom.append(f"{prompt_disp}{buf_to_show}")

        # Reserve rows for header + separator + bottom; everything else is scan.
        header_lines = list(header) if header else []
        reserved = len(header_lines) + 1 + len(bottom)  # +1 = top separator
        max_scan = max(0, term_h - reserved)
        scan = scan[:max_scan]

        out = list(header_lines)
        out.append("─" * draw_w)
        out.extend(scan)
        out.extend(bottom)

        # Pad if short
        while len(out) < term_h:
            # Insert padding just before the bottom block so the prompt stays at the last row
            out.insert(len(out) - len(bottom), " " * draw_w)
        # Last-resort trim: if header itself is taller than the terminal,
        # keep the bottom prompt + as many header rows as possible.
        if len(out) > term_h:
            keep_bottom = bottom[-min(len(bottom), term_h):]
            keep_header_n = max(0, term_h - len(keep_bottom))
            out = (header_lines + ["─" * draw_w])[:keep_header_n] + keep_bottom
        # ---- Right-side commands sidebar (wide terminals only) ----
        sidebar_w = 0
        sidebar_lines = []
        if draw_w >= 100:
            sidebar_w = min(40, max(28, draw_w // 4))
            if _DEV_MODE:
                sidebar_lines = _build_dev_sidebar(sidebar_w, term_h, _g_world, player)
            else:
                sidebar_lines = _build_commands_sidebar(sidebar_w, term_h)
        if sidebar_w > 0:
            sep = " │ "
            main_w = draw_w - sidebar_w - vlen(sep)
            # Header rows (HUD + top separator) get the FULL terminal width so
            # long lines like "☀️ DAY | 📍@... | 🌲 Forest | 🧭↗️N" never get
            # truncated or wrapped by the sidebar. The sidebar starts below.
            header_rows = len(header_lines) + 1  # +1 for the top separator
            # Rebuild the sidebar to fit only the rows below the header
            side_rows = max(0, term_h - header_rows)
            if _DEV_MODE:
                sidebar_lines = _build_dev_sidebar(sidebar_w, side_rows, _g_world, player)
            else:
                sidebar_lines = _build_commands_sidebar(sidebar_w, side_rows)
            merged = []
            for i, line in enumerate(out):
                if i < header_rows:
                    # Full-width HUD row, no sidebar overlay
                    merged.append(vfit(str(line), draw_w))
                else:
                    j = i - header_rows
                    left = vljust(vfit(str(line), main_w), main_w)
                    right = sidebar_lines[j] if j < len(sidebar_lines) else (" " * sidebar_w)
                    merged.append(left + sep + right)
            out = merged
        final = "\033[K\r\n".join([vtrunc(str(l), draw_w).rstrip() for l in out]) + "\033[K"
        sys.stdout.write(final + "\033[J")

        # Repaint the first HUD row after the frame is drawn. If any terminal
        # still auto-wrapped despite the margin, this guarantees the top line
        # remains visible at row 1.
        if header_lines:
            sys.stdout.write("\033[1;1H" + vtrunc(str(header_lines[0]), draw_w).rstrip() + "\033[K")

        # Position cursor at the end of the visible text (after buffer)
        # Position cursor at end of visible buffer portion
        prompt_vlen = vlen(prompt_disp)
        buf_vlen = vlen(buf_to_show)
        cursor_col = prompt_vlen + buf_vlen + 1
        # Ensure cursor doesn't go off-screen
        if cursor_col > draw_w: cursor_col = draw_w
        sys.stdout.write(f"\033[{term_h};{cursor_col}H\033[?25h"); sys.stdout.flush()

# ==================== TUTORIAL ====================
def run_tutorial(term):
    pages = [
        ["🪐 WELCOME TO 9 PLANETS 🪐", "═" * TERM_WIDTH, "",
         "You have crash-landed on an alien world.",
         "Survive by gathering resources, crafting tools,",
         "and managing Health, Hunger, Thirst, Energy, and Fatigue.",
         "", "This tutorial walks you through everything you need to know.",
         "", "  Press ENTER for next page.   Press S to skip the tutorial."],
        ["❤️ SURVIVAL STATS", "═" * TERM_WIDTH, "",
         "❤️  Health  — Hits 0: Game Over. Avoid hazards!",
         "🍽️ Hunger  — Drains over time. At 0: -10 HP immediately, then every 30 seconds.",
         "💧 Thirst  — Drains over time. At 0: continuous HP loss.",
         "⚡ Energy  — Powers every action. Does NOT passively regenerate!",
         "            Eat food to recover energy.", "",
         "😴 Fatigue — NEW! Drains slowly over time. At 0: cannot gather,",
         "            craft, or perform most actions. You MUST rest to recover.",
         "            Coffee (☕) also restores +25 Fatigue instantly.", "",
         "⚠️  Unfiltered water (-5 HP!) quenches thirst but harms you.",
         "   Craft a water_filter station to make safe filtered_water."],
        ["⬆️ MOVEMENT", "═" * TERM_WIDTH, "",
         "Use ARROW KEYS (↑ ↓ ← →) to move one tile at a time.",
         "Each step costs 0.5⚡ Energy and slightly drains Hunger/Thirst.", "",
         "Auto-walk to a resource:",
         "  walk to mushrooms     walk to spider     walk to water", "",
         "Moving while resting cancels your rest automatically.", "",
         "⚠️  You CANNOT move while crafting! Wait for the craft to finish, or use the cancel command.",
         "⚠️  You CANNOT gather while crafting or at 0 Fatigue!", "",
         "⏸️  Type 'pause' to freeze the game while you read help or plan your next move."],
        ["👁️ THE SCAN VIEW", "═" * TERM_WIDTH, "",
         "The main screen lists nearby resources in this format:",
         "  [icon] Name              | Type               | Qty | Dist | Pos", "",
         "🔒 = Needs a tool (axe/advanced_axe for wood, pickaxe for rock)",
         "🔓 = Tool equipped, ready to gather",
         "❓ = Unknown item — inspect it to identify", "",
         "The status bar at the bottom shows what's active:",
         "  🔨 Crafting in progress",
         "  🔥 Campfire rest / 😴 Floor rest",
         "  🪤 Traps setting or caught"],
        ["🫐 BERRIES & DANGERS", "═" * TERM_WIDTH, "",
         "Berries look the same until identified. Types include:",
         "  🫐 Wild Berries    🍬 Sweet Berries   🍋 Sour Berries",
         "  ✨ Glowing Berries  ☠️  Poisonous Berry  (-20 HP!)", "",
         "Always inspect unknown berries before eating!",
         "Use 'inspect berries' or buy an ID Lens from the shop.",
         "Poisonous Berry has a 20% chance of appearing in berry bushes."],
        ["🔍 UNKNOWN ITEMS & IDENTIFICATION", "═" * TERM_WIDTH, "",
         "Mushrooms, Berries, Moss, and Spider items are UNKNOWN on pickup.",
         "They stack by category: Unknown Mushrooms x4, Unknown Berries x2, etc.", "",
         "To identify:  inspect mushrooms   OR   identify berries",
         "Cost: 5⚡ per attempt. Max 5 tries. Takes 3 seconds.", "",
         "Success rate: Berries/Mushrooms 25%, Moss 10%, Spider/Bugs 50%.",
         "📚 Textbook boosts by +10% each (buy up to 3 from shop).",
         "🔍 ID Lens: instant identification, one use (buy from shop for 50🪙).", "",
         "⚠️  Eating unknown items is RISKY. Effects are unpredictable."],
        ["🔨 CRAFTING", "═" * TERM_WIDTH, "",
         "Type:  craft <item>    Example:  craft axe",
         "Type:  recipes         to browse all recipes by category.", "",
         "Crafting needs: materials + energy + time + the right station.", "",
         "New recipes include jerky, moss salve, antidote tea, frost tonic, glowing jam,",
         "honey root tea, insulated wrap, compressed fuel, and ash poultice.",
         "You start with a 🪵 Woodworking Station.",
         "Recommended early game order:",
         "  1. craft axe           (8 wood + 2 plank)",
         "  2. craft plank         (3 wood, Woodworking Station)",
         "  3. craft furnace       (cook food, brew coffee)",
         "  4. craft fabric        (5 fibergrass → 1 fabric)",
         "  5. craft sewing_station",
         "  6. craft fire_fuel     (1 oil + 50 wood) → then 'craft campfire'"],
        ["🏪 SHOP & ECONOMY", "═" * TERM_WIDTH, "",
         "You start with 1000🪙 Coins.",
         "Type: shop              to browse items by category",
         "Type: buy <item>        to purchase",
         "Type: sell <item>       to sell", "",
         "Buy price = 1.5× base price. Sell price = base price.", "",
         "Useful early purchases:",
         "  buy id_lens      (50🪙)  — instantly identifies one unknown item",
         "  buy textbook    (300🪙) — +10% identify chance per attempt (max 3)",
         "  buy coffee_beans (45🪙) — brew into ☕ coffee (+25 Fatigue!) at furnace",
         "  buy coffee       (52🪙) — instant +25 Fatigue, no crafting needed"],
        ["🏆 ACHIEVEMENTS", "═" * TERM_WIDTH, "",
         "Track your progress with achievements! Earn points and coins for goals.",
         "Type: achievements   to view unlocked rewards and active goals.",
         "Common achievement types: survive days, hunt animals, craft stations,", 
         "collect rare items, and complete milestones.",
         "Use achievements to prioritize your next move and earn extra coins."],
        ["🌤️ WEATHER & HAZARDS", "═" * TERM_WIDTH, "",
         "Weather changes every 5 real-time minutes:", "",
         "🌦️ Light Rain:   Fills water patches, stops evaporation.",
         "⛈️ Medium Storm: Lightning strikes (~80 dmg if it hits you!)",
         "                 ⚡ The screen flashes RED when lightning hits!",
         "🌪️ Heavy Storm:  Lightning + Tornadoes. Screen flashes RED on hit!",
         "🏜️ Drought:      After 3 dry days — resources start withering",
         "💧 No rain:      Water clusters lose 35% qty every 30 real seconds.", "",
         "🛡️ Medium armor blocks spider/bee damage.",
         "🛡️ Heavy armor gives full immunity to all hazards (but -30% speed)."],
        ["🪤 TRAPS & ☕ COFFEE", "═" * TERM_WIDTH, "",
         "TRAPS — Passive food collection while you explore:",
         "  craft trap       (10 spider_silk, sewing_station)",
         "  craft poison_trap (1 trap + 1 poison)",
         "  trap set         — place trap at current tile (uses from inventory)",
         "  trap check       — collect caught animals (1-3 Raw Game, +1 Bone for poison)",
         "  trap remove      — retrieve trap back into inventory",
         "  trap list  / traps — list all active traps with status & distance", "",
         "Traps check for catches every ~60s. Night has better odds (65% vs 45%).",
         "Poison traps also yield 1 Bone per catch.", "",
         "COFFEE — Quick Fatigue boost:",
         "  buy coffee_beans → craft coffee (furnace + 1 water) → drink coffee",
         "  OR: buy coffee directly from the shop",
         "  ☕ Drinking coffee: +25 Fatigue instantly"],
        ["🔥 CAMPFIRE & 😴 REST", "═" * TERM_WIDTH, "",
         "FIRE FUEL — craft at Woodworking Station:",
         "  craft fire_fuel  (1 oil + 50 wood)  →  gives 50 fuel parts (50 hrs)", "",
         "CAMPFIRE — instantly lit from fire_fuel:",
         "  craft campfire   (uses 1 fire_fuel from inventory)  →  50 parts loaded", "",
         "REST — type 'rest' to toggle resting on/off:",
         "  🔥 Campfire rest:  +30😴 +15❤️ +5⚡ per game-hour  (30 real seconds)",
         "                     burns 1 fuel part per game-hour",
         "  😴 Floor rest:     +30😴 per game-hour, BUT -10❤️/hr (risky!)", "",
         "Moving cancels rest automatically.",
         "When Fatigue hits 0: gathering and most actions are BLOCKED.",
         "  ✅ YOU'RE READY!  Good luck, Survivor! 🌍  Press Enter to begin."],
    ]
    for i, page in enumerate(pages):
        out = "\r\n".join(vfit(str(l), TERM_WIDTH) for l in page)
        footer = f"\r\n\r\n  Page {i+1}/{len(pages)}   [Enter] Next   [S] Skip tutorial\r\n"
        sys.stdout.write("\033[2J\033[H" + out + footer); sys.stdout.flush()
        wait_started = time.time()
        while True:
            k = term.get_key_no_flush(0.5)
            if k in ('\r', '\n'):
                freeze_blocking_time(getattr(term, "pause_context_player", None), getattr(term, "pause_context_world", None), getattr(term, "pause_context_weather", None), time.time() - wait_started)
                break
            if k and k.lower() == 's':
                freeze_blocking_time(getattr(term, "pause_context_player", None), getattr(term, "pause_context_world", None), getattr(term, "pause_context_weather", None), time.time() - wait_started)
                sys.stdout.write("\033[2J"); sys.stdout.flush(); return
    sys.stdout.write("\033[2J"); sys.stdout.flush()

# ==================== WEATHER ENGINE ====================
class WeatherSystem:
    def __init__(self):
        self.current = "☀️ clear"
        self.intensity = 0
        self.dry_streak = 0
        self.is_drought = False
        self.tornado_active = False
        self.tornado_type = "none"
        self.tornado_timer = 0
        self.tornado_x = 0
        self.tornado_y = 0
        self.rain_hours = 0
        self.last_lightning = 0
        self.lightning_hit = False   # flag for main loop to trigger red flash
        self.tornado_hit = False     # flag for main loop to trigger red flash
        self.last_evap = time.time() # for 30s water evaporation check
        self.firestorm_active = False

    def is_raining(self):
        c = self.current.lower()
        return "rain" in c or "storm" in c or "clearing" in c

    def _update_arctic(self, world, player):
        """Arctic-specific hourly weather update."""
        now = time.time()
        roll = random.random()
        if   roll < 0.10: wx = "blizzard"
        elif roll < 0.18: wx = "heavy_snow"
        elif roll < 0.30: wx = "medium_snow"
        elif roll < 0.44: wx = "light_snow"
        elif roll < 0.60: wx = "very_cold"
        elif roll < 0.70: wx = "hot"
        else:             wx = "neutral"
        world.arctic_weather_type = wx

        # Helper: gather Arctic clusters by type
        arc = [(k,c) for k,c in world.clusters.items() if biome_at(k[0],k[1]) == "Arctic"]
        snow_c = [(k,c) for k,c in arc if c.get("real_item") == "snow"]
        ice_c  = [(k,c) for k,c in arc if c.get("real_item") == "ice_chunk"]
        fw_c   = [(k,c) for k,c in arc if c.get("real_item") in ("freezing_water","freezing_dirty_water","arctic_water")]

        def scale_qty(clusters, mult):
            for k,c in clusters:
                c["qty"] = max(1, int(c["qty"] * mult))

        def remove_fraction(clusters, frac):
            """Remove frac fraction of clusters (randomly)."""
            random.shuffle(clusters)
            cut = int(len(clusters) * frac)
            for k,c in clusters[:cut]:
                if k in world.clusters: del world.clusters[k]

        if wx == "neutral":
            scale_qty(snow_c, 0.65); remove_fraction(snow_c, 0.35)
            scale_qty(ice_c, 1.35)
            player.arctic_insulation_req = max(ARCTIC_INSULATION_BASE,
                                               player.arctic_insulation_req - 1.0)
            world.arctic_weather_mods = {
                "snow":      {"cluster_rate_mult": 0.65, "qty_mult": 0.65},
                "ice_chunk": {"cluster_rate_mult": 1.35, "qty_mult": 1.35},
            }
            self.current = "☀️ Arctic Calm"
            return f"❄️ Calm arctic. Ice growing, snow thinning. Insulation req: {player.arctic_insulation_req:.0f}"

        elif wx == "hot":
            for k,c in snow_c:
                c["real_item"] = "freezing_water"; c["name"] = "❄️ Snow Melt"
                c["category"] = "drinkable"; c["is_identified"] = True
            scale_qty(ice_c, 0.65); remove_fraction(list(ice_c), 0.35)
            scale_qty(fw_c, 1.35)
            world.arctic_weather_mods = {
                "snow":         {"cluster_rate_mult": 0.65, "qty_mult": 0.65},
                "ice_chunk":    {"cluster_rate_mult": 0.65, "qty_mult": 0.65},
                "arctic_water": {"cluster_rate_mult": 1.35, "qty_mult": 1.35},
            }
            self.current = "🌡️ Arctic Thaw"
            return "🌡️ Warm front! Snow melting into water. Ice retreating."

        elif wx == "very_cold":
            scale_qty(fw_c, 0.65); remove_fraction(list(fw_c), 0.35)
            scale_qty(snow_c, 1.35); scale_qty(ice_c, 1.35)
            if now - player.last_very_cold_tick >= GAME_HOUR:
                player.last_very_cold_tick = now
                player.arctic_insulation_req = min(ARCTIC_INSULATION_MAX,
                                                   player.arctic_insulation_req + 1.0)
            world.arctic_weather_mods = {
                "snow":         {"cluster_rate_mult": 1.35, "qty_mult": 1.35},
                "ice_chunk":    {"cluster_rate_mult": 1.35, "qty_mult": 1.35},
                "arctic_water": {"cluster_rate_mult": 0.65, "qty_mult": 0.65},
            }
            self.current = "🥶 Very Cold"
            return (f"🥶 Extreme cold! Water freezing. Insulation demand: "
                    f"{player.arctic_insulation_req:.0f}/{ARCTIC_INSULATION_MAX:.0f}")

        elif wx in ("light_snow","medium_snow","heavy_snow"):
            mult = {"light_snow":1.25, "medium_snow":1.45, "heavy_snow":1.60}[wx]
            scale_qty(snow_c, mult)
            world.arctic_weather_mods = {"snow": {"cluster_rate_mult": mult, "qty_mult": mult}}
            labels = {"light_snow":"🌨️ Light Snow","medium_snow":"❄️ Medium Snow","heavy_snow":"❄️❄️ Heavy Snow"}
            self.current = labels[wx]
            return f"{labels[wx]}: Snowfall covering the tundra."

        elif wx == "blizzard":
            player.arctic_insulation_req = ARCTIC_INSULATION_MAX
            player.temp = max(0.0, player.temp - 20.0)  # immediate temp shock
            scale_qty(snow_c, 1.75); scale_qty(ice_c, 1.75)
            world.arctic_weather_mods = {
                "snow":      {"cluster_rate_mult": 1.75, "qty_mult": 1.75},
                "ice_chunk": {"cluster_rate_mult": 1.75, "qty_mult": 1.75},
            }
            self.current = "🌪️ Blizzard"
            return (f"🌪️ BLIZZARD! Insulation demand at MAX ({ARCTIC_INSULATION_MAX:.0f})! "
                    f"Seek shelter! -20°C temp shock!")

        return None

    def update_hourly(self, world, player):
        self.lightning_hit = False
        self.tornado_hit = False
        # Branch to Arctic-specific weather when player is in Arctic
        if biome_at(player.x, player.y) == "Arctic":
            return self._update_arctic(world, player)
        if self.is_drought:
            for c in world.clusters.values():
                if c.get("real_item") not in ["rock","dirt"]:
                    if random.random() < 0.85: c["qty"] = max(0, int(c["qty"] * 0.8))
            return "🏜️ DROUGHT: Resources withering..."
        if self.rain_hours > 5 and random.random() < 0.3:
            self.current = "☀️ clear"; self.intensity = 0; self.rain_hours = 0
            return "🌤️ Weather clearing up."
        roll = random.random()
        if roll < 0.15:
            self.current = "🏜️ dry"; self.dry_streak += 1
            if self.dry_streak > 3: self.is_drought = True
            # Firestorm: 10% chance in dry Forest weather
            if not self.firestorm_active and biome_at(player.x, player.y) == "Forest" and dist_to_border(player.x, player.y) > 200 and random.random() < 0.10:
                self.firestorm_active = True
                water_items = {"water", "fresh_water", "dirty_water", "freezing_water", "freezing_dirty_water", "arctic_water"}
                cluster_keys = [k for k in world.clusters.keys() if world.clusters[k].get("real_item") not in water_items]
                random.shuffle(cluster_keys)
                burn_count = max(1, int(len(cluster_keys) * 0.20)) if cluster_keys else 0
                for k in cluster_keys[:burn_count]:
                    cx, cy = k
                    world.clusters[k] = {
                        "name": "🔥 Fire", "real_item": "fire", "category": "hazard",
                        "is_identified": True, "inspection_attempts": 0,
                        "pos": [cx, cy], "qty": 1,
                        "meta": {"regrows": False, "hazard_key": None, "is_burning": True}
                    }
                for k in cluster_keys[burn_count:]:
                    c = world.clusters.get(k)
                    if c:
                        c["qty"] = max(1, int(c.get("qty", 1) * 0.20))
                if biome_at(player.x, player.y) == "Forest":
                    player.note_damage_cause("Burned by firestorm")
                    player.health -= 10; player.on_fire = True; player.fire_start = time.time()
                    player.temp = 100.0
                return "🔥🌲 FIRESTORM! The forest is burning! -10 HP! Move to water to extinguish!"
            return "🔥 Dry heat today."
        self.dry_streak = 0; self.is_drought = False
        choices = [("heavy_storm",15),("medium_storm",25),("light_storm",35),("light_rain",45)]
        total = sum(w for _,w in choices); r = random.uniform(0, total); upto = 0; chosen = "clear"
        for weather, weight in choices:
            if upto + weight >= r: chosen = weather; break
            upto += weight
        if chosen == "clear": self.current = "☀️ clear"; self.intensity = 0; return "☀️ Clear skies."
        self.current = chosen
        self.intensity = 4 if chosen=="heavy_storm" else (3 if chosen=="medium_storm" else (2 if chosen=="light_storm" else 1))
        self.rain_hours += 1
        rate = 0.10 if self.intensity==2 else (0.15 if self.intensity==3 else 0.30)
        if rate > 0:
            keys = [k for k,v in world.clusters.items() if v.get("real_item") != "water"]
            random.shuffle(keys)
            for k in keys[:int(len(world.clusters)*rate)]: del world.clusters[k]
        add = 15 if self.intensity==2 else (25 if self.intensity==3 else 40)
        for c in world.clusters.values():
            if c.get("real_item") == "water": c["qty"] += add
        msg = self._handle_tornado(player, world)
        if msg: return msg
        if self.intensity >= 2: return self._handle_lightning(player, world)
        return f"🌧️ {chosen.replace('_',' ').title()}"

    def _handle_lightning(self, player, world):
        now = time.time(); freq = 60 if self.intensity==2 else 30
        if now - self.last_lightning < freq: return None
        self.last_lightning = now
        radius = math.sqrt(100 if self.intensity==4 else (144 if self.intensity==3 else 900))
        lx = player.x + random.uniform(-radius, radius)
        ly = player.y + random.uniform(-radius, radius)
        lightning_dist = math.hypot(player.x-lx, player.y-ly)
        if lightning_dist <= 10:
            self.lightning_hit = True
        if lightning_dist <= 1:
            dmg = 80
            multiplier = player.armor_damage_multiplier()
            dmg = int(round(dmg * multiplier))
            if dmg > 0:
                player.note_damage_cause("Lightning strike")
                if player.wearing:
                    player.armor_dur -= dmg
                    if player.armor_dur <= 0:
                        player.wearing = None
                        player.armor_dur = 0
                        msg = "💥 Armor broke!"
                    else:
                        msg = None
                else:
                    msg = None
                player.health -= dmg
            else:
                msg = "🛡️ Attack blocked by armor!" if player.wearing else None
            return f"⚡ LIGHTNING STRUCK YOU! (-{dmg:.0f} HP){' ' + msg if msg else ''}"
        destroyed = [k for k,c in list(world.clusters.items()) if math.hypot(k[0]-lx, k[1]-ly)<=1]
        # Convert destroyed clusters into ash piles rather than simply deleting them
        for k in destroyed:
            cx, cy = k
            world.clusters[k] = {
                "name": "💨 Ash Pile", "real_item": "ash", "category": "material",
                "is_identified": True, "inspection_attempts": 0,
                "pos": [cx, cy], "qty": max(1, int(world.clusters.get(k, {}).get("qty", 1))),
                "meta": {"regrows": False, "hazard_key": None, "is_ash": True}
            }
        return f"⚡ Lightning nearby! Converted {len(destroyed)} cluster(s) to ash." if destroyed else None

    def _handle_tornado(self, player, world):
        if self.tornado_active:
            self.tornado_timer -= 1
            t_data = TORNADO_TYPES[self.tornado_type]
            self.current = f"🌪️ TORNADO ({self.tornado_type.upper()})"

            # Move tornado each turn — persistent direction with drift
            if not hasattr(self, '_tornado_dir'):
                self._tornado_dir = random.random() * math.tau
            # 50% chance to drift the direction significantly
            if random.random() < 0.50:
                self._tornado_dir += random.uniform(-1.2, 1.2)
            self._tornado_dir %= math.tau
            step = random.uniform(8, 18)
            self.tornado_x += math.cos(self._tornado_dir) * step
            self.tornado_y += math.sin(self._tornado_dir) * step

            # Only damage if player is within tornado radius
            dist_to_player = math.hypot(player.x - self.tornado_x, player.y - self.tornado_y)
            dmg = 0
            hit = False
            if dist_to_player <= t_data["radius"]:
                if random.random() < 0.3:
                    dmg = t_data["dmg_hit"]; hit = True
                elif random.random() < 0.1:
                    dmg = t_data["dmg_near"]

            animal_msg = ""
            if dmg > 0:
                player.note_damage_cause("Tornado strike")
                multiplier = player.armor_damage_multiplier()
                dmg = int(round(dmg * multiplier))
                if dmg > 0:
                    if player.wearing:
                        player.armor_dur -= dmg
                        if player.armor_dur <= 0:
                            player.wearing = None
                            player.armor_dur = 0
                            animal_msg = "💥 Armor broke!"
                    player.health -= dmg
                else:
                    animal_msg = "🛡️ Attack blocked by armor!"
                if hit:
                    self.tornado_hit = True
                killed = []
                for a in list(world.animals):
                    if math.hypot(a["x"]-self.tornado_x, a["y"]-self.tornado_y) <= t_data["radius"]:
                        killed.append(a)
                        world.animals.remove(a)
                if killed:
                    for a in killed:
                        meat_qty = ANIMAL_DEFS.get(a["type"], {}).get("loot", {}).get("meat", 1)
                        drop_pos = (int(a["x"]), int(a["y"]))
                        existing = world.clusters.get(drop_pos)
                        if existing and existing.get("real_item") != "raw_game":
                            drop_pos = (drop_pos[0] + 1, drop_pos[1])
                            existing = world.clusters.get(drop_pos)
                        if existing and existing.get("real_item") == "raw_game":
                            existing["qty"] = existing.get("qty", 0) + meat_qty
                        else:
                            world.clusters[drop_pos] = {
                                "name": "Raw Game",
                                "real_item": "raw_game",
                                "category": "food",
                                "is_identified": True,
                                "inspection_attempts": 0,
                                "pos": [drop_pos[0], drop_pos[1]],
                                "qty": meat_qty,
                                "meta": {"item": "raw_game", "regrows": False},
                            }
                    animal_msg = f" 🌪️ The tornado killed {len(killed)} animal(s) and left raw game behind."

            # Destroy clusters only near tornado
            if "destroy_pct" in t_data:
                for k in list(world.clusters.keys()):
                    cx, cy = k
                    if math.hypot(cx - self.tornado_x, cy - self.tornado_y) <= t_data["radius"]:
                        if random.random() < t_data["destroy_pct"]:
                            world.clusters[k] = {
                                "name": "💨 Ash Pile", "real_item": "ash", "category": "material",
                                "is_identified": True, "inspection_attempts": 0,
                                "pos": [cx, cy], "qty": max(1, int(world.clusters.get(k, {}).get("qty", 1))),
                                "meta": {"regrows": False, "hazard_key": None, "is_ash": True}
                            }
            else:
                destroyed = 0
                for k in list(world.clusters.keys()):
                    cx, cy = k
                    if destroyed >= t_data.get("destroy", 0):
                        break
                    if math.hypot(cx - self.tornado_x, cy - self.tornado_y) <= t_data["radius"]:
                        world.clusters[k] = {
                            "name": "💨 Ash Pile", "real_item": "ash", "category": "material",
                            "is_identified": True, "inspection_attempts": 0,
                            "pos": [cx, cy], "qty": max(1, int(world.clusters.get(k, {}).get("qty", 1))),
                            "meta": {"regrows": False, "hazard_key": None, "is_ash": True}
                        }
                        destroyed += 1

            if self.tornado_timer <= 0:
                self.tornado_active = False; self.current = "🌦️ CLEARING"
            tx = int(self.tornado_x)
            ty = int(self.tornado_y)
            base = f"🌪️ {t_data['name']} active at @({tx},{ty})! ({self.tornado_timer} mins left)"
            if hit and dmg > 0:
                return f"🌪️ YOU WERE HIT BY A TORNADO at @({tx},{ty})! (-{int(dmg)} HP) {self.tornado_timer} mins left{animal_msg}"
            return base + animal_msg
        roll = random.random(); spawn = "none"
        if self.intensity==4 and roll<0.05: spawn="huge"
        elif self.intensity>=2 and roll<0.35: spawn="medium"
        elif roll < 0.35: spawn="light"
        if spawn != "none":
            self.tornado_x, self.tornado_y = 0, 0
            t_data = TORNADO_TYPES[spawn]
            angle = random.random() * math.tau
            dist = random.uniform(0, max(50, t_data.get("radius", 50) * 1.5))
            self.tornado_x = player.x + math.cos(angle) * dist
            self.tornado_y = player.y + math.sin(angle) * dist
            self.tornado_active = True; self.tornado_type = spawn
            self.tornado_timer = TORNADO_TYPES[spawn]["duration_mins"]
            self.current = f"🌪️ TORNADO ({spawn.upper()})"
            return f"⚠️ TORNADO WARNING: {TORNADO_TYPES[spawn]['name']} detected at @({int(self.tornado_x)},{int(self.tornado_y)})!"
        return None


# ==================== DISEASES ====================
# Each disease declares its source category, tick effects, optional lifespan in
# days, and recovery rolls keyed by the item the player consumes.
DISEASES = {
    "cholera":           {"cat":"water",      "phases":("day","night"),
                          "effects":{"thirst":-20,"health":-15}, "days":None,
                          "recover":{"moss_healing":0.90,"sweet_berries":0.25,
                                     "fresh_water":0.20,"filtered_water":0.45}},
    "dysentery":         {"cat":"water",      "phases":("day","night"),
                          "effects":{"hunger":-10,"health":-15}, "days":None,
                          "recover":{"water":0.30,"fresh_water":0.50,
                                     "filtered_water":0.75,"moss_healing":0.75}},
    "typhoid_fever":     {"cat":"water",      "phases":("day","night"),
                          "effects":{"health":-15}, "days":None,
                          "recover":{"moss_healing":0.50}},
    "cryptosporidiosis": {"cat":"water",      "phases":("day",),
                          "effects":{"health":-10,"thirst":-20},
                          "days":(3,6), "recover":{}},
    "hepatitis_a":       {"cat":"water_food", "phases":("day",),
                          "effects":{"health":-3,"energy":-15},
                          "days":5, "recover":{}},
    "toxoplasmosis":     {"cat":"water_food", "phases":("day",),
                          "effects":{"health":-10}, "days":5,
                          "recover":{"mystery_mushroom":1.0,"moss_mystery":1.0},
                          "chronic_chance":0.05},
    "giardiasis":        {"cat":"water_food", "phases":("day",),
                          "effects":{"health":-5}, "days":3, "recover":{}},
    "salmonellosis":     {"cat":"food",       "phases":("day",),
                          "effects":{"health":-5,"thirst":-20},
                          "days":3, "recover":{"moss_healing":0.85}},
    "norovirus":         {"cat":"food",       "phases":("day",),
                          "effects":{"health":-10,"thirst":-20,"fatigue":-20,"energy":-30},
                          "days":1, "recover":{"moss_healing":0.10}},
    "e_coli":            {"cat":"food",       "phases":("day",),
                          "effects":{"health":-5,"thirst":-10,"fatigue":-25,"energy":-40},
                          "days":5, "recover":{"moss_healing":0.50}},
    "campylobacter":     {"cat":"food",       "phases":("day",),
                          "effects":{"thirst":-30,"energy":-40,"fatigue":-25},
                          "days":3, "recover":{}},
    "listeria":          {"cat":"food",       "phases":("day",),
                          "effects":{"health":-5}, "days":None, "recover":{},
                          "daily_resolve":0.10, "ramp":1.1},
    "clostridium":       {"cat":"food",       "phases":("day",),
                          "effects":{"health":-25}, "days":15,
                          "recover":{"moss_healing":0.20}, "instant":-30, "rare":True},
}
DISEASE_DISPLAY = {
    "cholera":"Cholera","dysentery":"Dysentery","typhoid_fever":"Typhoid Fever",
    "cryptosporidiosis":"Cryptosporidiosis","hepatitis_a":"Hepatitis A",
    "toxoplasmosis":"Toxoplasmosis","giardiasis":"Giardiasis",
    "salmonellosis":"Salmonellosis","norovirus":"Norovirus","e_coli":"E. Coli",
    "campylobacter":"Campylobacter","listeria":"Listeria",
    "clostridium":"Clostridium Botulinum",
}
WATER_DISEASES = [d for d,v in DISEASES.items() if v["cat"]=="water"]
FOOD_DISEASES  = [d for d,v in DISEASES.items() if v["cat"]=="food" and not v.get("rare")]
WATER_OR_FOOD  = [d for d,v in DISEASES.items() if v["cat"]=="water_food"]
RARE_FOOD      = [d for d,v in DISEASES.items() if v.get("rare")]

def _pick_disease(pool):
    if not pool: return None
    return random.choice(pool)

def _cascade_count():
    """Returns the number of diseases contracted at once.
    1 → standard, 2 → 10%, 3 → 3%, 4 → 1%, 5 → 0.3%, ..."""
    n = 1
    p = 0.10
    while random.random() < p:
        n += 1
        p = p / 3.0
    return n

def _infect_player(player, source, msg):
    """Source is one of: 'water', 'food', 'water_food', 'daily', 'mystery'."""
    if source == "water":
        pool = WATER_DISEASES + WATER_OR_FOOD
    elif source == "food":
        pool = FOOD_DISEASES + WATER_OR_FOOD
        # Rare clostridium roll (0.5% per food infection event)
        if random.random() < 0.005:
            pool = ["clostridium"]
    elif source == "water_food":
        pool = WATER_DISEASES + FOOD_DISEASES + WATER_OR_FOOD
    elif source == "mystery":
        pool = list(DISEASES.keys())
    else:  # daily
        pool = list(DISEASES.keys())
    if not pool: return
    count = 1 if source != "daily" else 1
    if source in ("water","food","water_food"):
        count = _cascade_count()
    diseases = getattr(player, "diseases", None)
    if diseases is None:
        player.diseases = {}; diseases = player.diseases
    first_infection = not diseases
    for _ in range(count):
        did = _pick_disease(pool)
        if not did: continue
        if did in diseases:
            diseases[did]["stacks"] = diseases[did].get("stacks",1) + 1
            msg.append(f"☣️ Worsened: {DISEASE_DISPLAY[did]} (x{diseases[did]['stacks']})")
        else:
            d = DISEASES[did]
            days_left = None
            dd = d.get("days")
            if isinstance(dd, tuple): days_left = random.randint(dd[0], dd[1])
            elif isinstance(dd, int): days_left = dd
            chronic = False
            if did == "toxoplasmosis" and random.random() < d.get("chronic_chance",0):
                chronic = True; days_left = None
            diseases[did] = {"stacks":1, "days_left":days_left,
                             "chronic":chronic, "ramp_mult":1.0}
            if d.get("instant"):
                player.health = max(0, player.health + d["instant"])
            msg.append(f"☣️ You contracted {DISEASE_DISPLAY[did]}!")
    msg[:] = msg[-3:]
    # Unlock disease tutorial on first infection
    if first_infection:
        _unlock_and_show_tutorial(None, player, "disease")
    # Activate disease recovery quest on first infection
    if first_infection and player.quests.get("disease_recovery") == "pending":
        activate("disease_recovery", "🧓 Old Man: You got sick! That's what happens when you drink dirty water or eat raw food. Get some antidote tea or moss healing to cure it!")
    if player.quests.get("disease_recovery") == "active" and not diseases:
        complete("disease_recovery", "✅ QUEST COMPLETE: You recovered from your disease! 30 points and 25 coins.")

def _apply_disease_recovery(player, item_key, msg):
    """When the player consumes item_key, roll recovery for each active disease
    whose recover dict references it."""
    diseases = getattr(player, "diseases", None) or {}
    cured = []
    for did, st in list(diseases.items()):
        d = DISEASES.get(did, {})
        chance = d.get("recover", {}).get(item_key, 0.0)
        if chance > 0 and random.random() < chance:
            cured.append(did)
    for did in cured:
        del player.diseases[did]
        msg.append(f"💊 Recovered from {DISEASE_DISPLAY[did]}!")
    msg[:] = msg[-3:]

def _remove_one_disease(player, msg):
    diseases = getattr(player, "diseases", None) or {}
    if not diseases: return False
    did = random.choice(list(diseases.keys()))
    del player.diseases[did]
    msg.append(f"💊 The mystery cured your {DISEASE_DISPLAY[did]}!")
    msg[:] = msg[-3:]
    return True

def disease_daily_tick(player, msg, phase):
    """Phase is 'day' or 'night' — called each time time_of_day changes."""
    diseases = getattr(player, "diseases", None) or {}
    if not diseases and phase != "day":
        return
    to_remove = []
    for did, st in list(diseases.items()):
        d = DISEASES.get(did, {})
        if phase not in d.get("phases", ()):
            continue
        stacks = st.get("stacks", 1)
        eff_mult = 3 ** (stacks - 1) if stacks > 1 else 1
        ramp = st.get("ramp_mult", 1.0)
        for stat, delta in d.get("effects", {}).items():
            scaled = delta * eff_mult * ramp
            cur = getattr(player, stat, None)
            if cur is None: continue
            setattr(player, stat, max(0, min(MAX_STAT_CAP, cur + scaled)))
        # Listeria ramp
        if d.get("ramp"):
            st["ramp_mult"] = ramp * d["ramp"]
        # Listeria daily resolve
        if d.get("daily_resolve") and random.random() < d["daily_resolve"]:
            to_remove.append(did); continue
        # Day-counted diseases
        if phase == "day" and st.get("days_left") is not None and not st.get("chronic"):
            st["days_left"] -= 1
            if st["days_left"] <= 0:
                to_remove.append(did)
    for did in to_remove:
        del player.diseases[did]
        msg.append(f"💊 {DISEASE_DISPLAY[did]} cleared.")
    # Daily random infection chance (only on day transitions, beginner skip)
    if phase == "day":
        beginner = getattr(player, "difficulty_mult", NORMAL_HUNGER_MULT) <= BEGINNER_HUNGER_MULT
        if not beginner and random.random() < 0.05:
            _infect_player(player, "daily", msg)
    msg[:] = msg[-3:]

# ==================== PETS / LOYALTY ====================
CAT_PET_NEAR_RADIUS = 2.5

def _nearest_followed_or_close_cat(player, world, radius=CAT_PET_NEAR_RADIUS):
    """Prefer a bonded/following cat anywhere; else closest cat within radius."""
    if not world: return None
    following = next((a for a in world.animals
                      if a.get("type")=="cat" and a.get("hp",1)>0
                      and a.get("_following_player")), None)
    if following:
        d = math.hypot(following["x"]-player.x, following["y"]-player.y)
        if d <= max(radius, 4.0):
            return following
    best = None; best_d = radius
    for a in world.animals:
        if a.get("type") != "cat" or a.get("hp",1) <= 0: continue
        d = math.hypot(a["x"]-player.x, a["y"]-player.y)
        if d <= best_d:
            best_d = d; best = a
    return best

def _curve_pet_target():
    """Triangular curve from 0..10, peak at 5, symmetric (4=6, 3=7, etc.)."""
    return int(round(random.triangular(0.0, 10.0, 5.0)))

def pet_cat(player, world, msg, with_meat=False):
    cat = _nearest_followed_or_close_cat(player, world)
    if cat is None:
        msg.append("🐾 No cat nearby to pet."); msg[:] = msg[-3:]; return False
    cat.setdefault("loyalty", 0)
    cat.setdefault("_pet_count", 0)
    if "_pet_curve_target" not in cat:
        cat["_pet_curve_target"] = _curve_pet_target()
    if with_meat:
        cat["loyalty"] += 4
        # Meat / catnip immediately makes the cat willing to be petted
        cat["_pet_ok"] = True
        cat["_pet_ok_at"] = getattr(player, "unpaused_clock", 0.0) + random.uniform(240.0, 480.0)
        meow = random.choice(CAT_MEOWS)
        msg.append(f"🐈 You give the cat meat. It rolls over contentedly. «{meow}»  (loyalty {cat['loyalty']:+d})")
    else:
        if not cat.get("_pet_ok", False):
            cat["loyalty"] = max(-20, cat.get("loyalty", 0) - 1)
            cat["_pet_ok_at"] = getattr(player, "unpaused_clock", 0.0) + random.uniform(180.0, 300.0)
            meow = random.choice(CAT_MEOWS)
            msg.append(f"🐈 The cat turns away from your hand. Try again later or give it meat. «{meow}»")
            msg[:] = msg[-3:]
            return False
        cat["_pet_count"] += 1
        cat["_pet_ok"] = False
        cat["_pet_ok_at"] = getattr(player, "unpaused_clock", 0.0) + random.uniform(240.0, 480.0)
        if cat["_pet_count"] <= cat["_pet_curve_target"]:
            cat["loyalty"] += 1
            change = "+1"
        else:
            cat["loyalty"] -= 3
            change = "-3"
        meow = random.choice(CAT_MEOWS)
        msg.append(f"🐈 You pet the cat. «{meow}»  (loyalty {change} → {cat['loyalty']})")
    msg[:] = msg[-3:]
    return True


# ==================== PLAYER ====================
class Player:
    def __init__(self):
        self.x, self.y = 0, 0
        self.health = 100.0; self.max_health = 100.0
        self.hunger = 100.0; self.thirst = 100.0
        self.energy = 100.0; self.max_energy = 100.0
        self.fatigue = 100.0
        self.coins = 1000.0; self.time_of_day = "day"
        self.debug_mode = False    # password-protected cheat mode (set from menu)
        self.total_travel_mins = 0.0
        self.last_passive = time.time(); self.last_day = time.time()
        self.last_weather_check = time.time()
        self.last_starvation_tick = 0.0
        self.last_hunger_tick = 0.0
        self.last_thirst_tick = 0.0
        self.last_damage_cause = ""
        self.traps = []; self.active_tasks = []
        self.auto_walk_target = None
        self.campfire_fuel = 0      # remaining fuel parts in active campfire
        self.resting = False
        self.rest_mode = None       # "campfire" or "floor"
        self.rest_last = 0.0
        self.axe_dur = TOOL_DUR; self.pickaxe_dur = 0
        self.armor_dur = 0; self.wearing = None
        self.station_hp = {"woodworking_station":500.0,"furnace":0.0,"water_filter":0.0,"sewing_station":0.0,"smelter":0.0,"liquifier":0.0}
        self.inventory = {k:0 for k in ITEM_PRICES.keys()}
        self.inventory.update({"id_lens":0,"textbook":0,"woodworking_station":1,"furnace":0,"water_filter":0,"liquifier":0,"poison_trap":0,"sewing_station":0,"smelter":0,"axe":1,"advanced_axe":0,"poisonous_berry":0,"fire_fuel":0,"coffee_beans":0,"coffee":0,"pants":0,"shirt":0,"medium_pants":0,"medium_shirt":0,"heavy_pants":0,"heavy_shirt":0,"snow":0})
        self.auto_walk_target = None
        self.detour_until = 0.0
        self.pause_started = 0.0
        self.quests = {qid: "pending" for qid in QUESTS}
        self.quest_announced = {qid: False for qid in QUESTS}
        self.quest_clock_started_at = None
        self.berries_gathered = 0
        self.mushrooms_gathered = 0
        self.hidden_xp = 0
        self.grace_period_over = False
        self.grot_kills = 0
        self.used_campfire = False
        self.berry_types_eaten = []
        self.mushroom_types_eaten = []
        self.spider_silk_gathered = 0
        self.bee_hives_collected = 0
        self.quest11_ready_at = None
        self.quest22_ready_at = None
        self.quest23_ready_at = None
        self.quest24_ready_at = None
        self.quest28_ready_at = None
        self.quest29_ready_at = None
        self.quest31_ready_at = None
        self.filtered_water_drank = False
        self.bandages_made = 0
        self.traps_set = 0
        self.trap_successes = 0
        self.poison_traps_crafted = 0
        self.oil_made = 0
        self.fire_fuel_crafted = 0
        self.campfire_rested = False
        self.textbooks_bought = 0
        self.id_lens_bought = 0
        self.smelter_crafted = False
        self.poison_kills = 0
        self.rabbit_kills = 0
        self.squirrel_kills = 0
        self.deer_kills = 0
        self.antelope_kills = 0
        self.arctic_items_sold = 0
        self.arctic_reached_at = None
        self.trap_challenge_started = False
        self.arctic_hunt_started = False
        self.arctic_items_brought = 0
        self.planks_made = 0
        self.first_trap_set = False
        # Achievement & stats tracking
        self.earned_achievements = []
        self.points = 0
        self.days_survived = 0
        self.arctic_visited = False
        self.total_hunts = 0
        self.trap_meat_total = 0
        self.penguin_kills = 0
        self.seal_kills = 0
        self.fish_kills = 0
        self.wood_gathered = 0
        self.total_playtime = 0.0
        self.session_start = time.time()
        self.difficulty_mult = NORMAL_HUNGER_MULT
        self.light_mode = bool(LIGHT_MODE.get("on"))
        self.fast_mode = False    # Fast Mode: Arctic at 1000, 3x faster crafting
        self.terminal_theme = "dark"
        self.graphics_mode = False
        self.graphics_adaptive = False   # True = fit terminal; False = classic 20×20
        self.show_commands = False       # False = hide commands panel in graphics mode (tab still cycles); frees space for stats
        self.last_move_time = 0.0        # real-time stamp of last player movement
        self.mode = "quest"
        # Spear
        self.spear_type = None
        self.spear_dur = 0
        # Shield
        self.shield_type = None      # equipped shield name or None
        self.shield_dur_blocks = 0   # blocks remaining
        self.shield_dur_absorb = 0   # HP absorption remaining
        # Turn-based combat state
        self.in_combat = False
        self.combat = None   # dict: {"enemies": [...], "player_ap": int, "player_turns": int, "blocking": False}
        self.flee_until = 0.0
        # Poison coating on spear: 1 application = 4 strikes OR 1 throw
        self.spear_poison_strikes = 0  # remaining doubled-damage strikes
        self.spear_poison_throw   = False  # next throw is doubled
        # Tutorial: shown once when the player throws their first spear
        self.spear_tutorial_shown = False  # legacy; superseded by tutorials_unlocked
        # Re-readable tutorial registry: list of unlocked tutorial keys (see TUTORIALS)
        self.tutorials_unlocked = []
        # Tutorial keys queued by non-UI code to be shown by the main loop.
        self.pending_tutorials = []
        # First-spear-craft flag (for the first-spear tutorial).
        self.first_spear_crafted = False
        # Tracks previous weather.current so main loop can detect changes.
        self._prev_weather_for_tutorial = None
        # Major-goals tracker
        self.goals_intro_shown = False
        self.goals_completed_keys = []
        self.house_built = False
        self.lore_intro_shown = False
        # Cat companion
        self.cat_following = False   # True when a cat is following the player
        self.last_meow = 0.0         # real timestamp of last meow
        self.last_cat_action = 0.0   # timestamp of last cat "sitting on X" message
        self.cat_hunt_return = 0.0   # timestamp when cat will return after fleeing
        self.cat_approach_announced = False  # old-man popup shown once for cat approach
        # Unpaused playtime clock (advances only while not paused)
        self.unpaused_clock = 0.0
        self._last_uc = time.time()
        # Dropped items in the world (list of {item, qty, x, y, dropped_at})
        self.dropped_items = []
        # Fire
        self.on_fire = False
        self.fire_start = 0.0
        # Temperature (0=freezing, 50=comfortable, 100=burning)
        self.temp = TEMP_NEUTRAL
        # Clothing (slot holds item name string or None)
        self.wearing_pants = None
        self.wearing_shirt = None
        # Arctic insulation requirement (base 6, modified by weather)
        self.arctic_insulation_req = ARCTIC_INSULATION_BASE
        self.last_very_cold_tick = 0.0
        # Housing
        self.inside_house_id = None  # id of house player is currently inside, or None
        self.house_pos = [0, 0]      # player tile position within house interior
        # Active diseases: {disease_id: {stacks, days_left, chronic, ramp_mult}}
        self.diseases = {}
        # Cumulative failed inspects (triggers old man tip at 10)
        self.total_inspect_failures = 0
        # True once the 100-wood delivery quest popup has fired and been acknowledged
        self.wood_quest_delivered = False
        # Audio preference (True = audio enabled for this save)
        self.audio_enabled = True

    @property
    def health(self):
        return getattr(self, "_health", 100.0)

    @health.setter
    def health(self, value):
        old = getattr(self, "_health", None)
        new = float(value)
        self._health = new
        if old is not None and new < old:
            self._damage_flash_pending = True

    def armor_defense(self):
        return {"light_armor": 2, "medium_armor": 5, "heavy_armor": 10}.get(self.wearing, 0)

    def armor_damage_multiplier(self):
        return {"light_armor": 0.80, "medium_armor": 0.60, "heavy_armor": 0.30}.get(self.wearing, 1.0)

    def armor_hazard_reduction(self, hazard_key):
        """Per-hazard flat damage reduction by armor type (stacks with multiplier for monsters/weather).
        Returns flat HP reduction to subtract from final_dmg for gather hazards."""
        w = self.wearing
        reductions = {
            "spider nest":     {"light_armor": 5,  "medium_armor": 8,  "heavy_armor": 8},
            "venomous spider": {"light_armor": 5,  "medium_armor": 10, "heavy_armor": 10},
            "bee hive":        {"light_armor": 5,  "medium_armor": 10, "heavy_armor": 20},
        }
        return reductions.get(hazard_key, {}).get(w, 0)

    def note_damage_cause(self, cause):
        self.last_damage_cause = cause

    def apply_debug_mode(self):
        """Cheat mode: max everything, all materials, indestructible stations."""
        self.health = self.max_health
        self.hunger = 100.0; self.thirst = 100.0
        self.energy = self.max_energy; self.fatigue = 100.0
        self.coins = 999999.0
        self.on_fire = False
        # All stations present with effectively infinite HP.
        for st in list(self.station_hp.keys()):
            self.station_hp[st] = 1e9
        # All known items stocked generously; tools maxed.
        for k in list(self.inventory.keys()):
            cur = self.inventory.get(k)
            if isinstance(cur, (int, float)):
                self.inventory[k] = max(cur, 9999)
        for st in ("woodworking_station","furnace","water_filter","liquifier",
                   "sewing_station","smelter","poison_trap"):
            self.inventory[st] = max(self.inventory.get(st, 0) or 0, 9)
        self.inventory["axe"] = max(self.inventory.get("axe", 0) or 0, 1)
        self.axe_dur = TOOL_DUR
        try:
            self.pickaxe_dur = max(self.pickaxe_dur, TOOL_DUR)
        except Exception:
            pass

    def update_passive(self):
        now = time.time()
        is_debug = getattr(self, "debug_mode", False)
        if is_debug:
            self.apply_debug_mode()
        dt = now - self.last_passive
        # Time-flow rule for read-only menus (inventory / recipes / help):
        #  - When IDLE, those menus block the loop, so we clamp the elapsed
        #    time to effectively pause the world while you read.
        #  - When BUSY (crafting / gather-all / resting), time keeps flowing so
        #    the action you started actually progresses while you read.
        _busy = bool(self.active_tasks) or bool(getattr(self, "gather_all", None)) or self.resting
        if dt > 2.0:
            dt = min(dt, 120.0) if _busy else 0.5
        due_task = any(now >= t["end"] and "paused_remaining" not in t for t in self.active_tasks)
        if dt >= 0.5 or due_task:
            self.last_passive = now
            if not is_debug:
                self.hunger = max(0, self.hunger - dt * HUNGER_IDLE_RATE)
                if is_light(self):
                    # Light mode: no thirst, no fatigue, and energy regenerates
                    self.thirst = 100.0
                    self.fatigue = 100.0
                    self.energy = min(self.max_energy,
                                      self.energy + dt * PASSIVE_ENERGY_RATE * LIGHT_ENERGY_REGEN_MULT)
                else:
                    self.thirst = max(0, self.thirst - dt * THIRST_IDLE_RATE)
                    self.energy = max(0, self.energy - dt * PASSIVE_ENERGY_RATE)
                    self.fatigue = max(0, self.fatigue - dt * FATIGUE_PASSIVE_RATE)
            # Fatigue floor popup — fire once each time it crosses to 0
            if self.fatigue <= 0 and not getattr(self, "_fatigue_zero_flagged", False):
                self._fatigue_zero_flagged = True
                self._fatigue_zero_popup = True
            elif self.fatigue > 5:
                self._fatigue_zero_flagged = False
            if self.hunger <= 0:
                if self.last_hunger_tick == 0.0 or (now - self.last_hunger_tick) >= 30.0:
                    self.last_hunger_tick = now
                    self.note_damage_cause("Starvation")
                    self.health = max(0, self.health - 10)
                    self._starvation_flash = True
            else:
                self.last_hunger_tick = 0.0
                if hasattr(self, '_starvation_flash'): self._starvation_flash = False
            if self.thirst <= 0:
                if self.last_thirst_tick == 0.0 or (now - self.last_thirst_tick) >= 30.0:
                    self.last_thirst_tick = now
                    self.note_damage_cause("Dehydration")
                    self.health = max(0, self.health - 10)
                    self._thirst_flash = True
            else:
                self.last_thirst_tick = 0.0
                if hasattr(self, '_thirst_flash'): self._thirst_flash = False
            if self.on_fire:
                self.note_damage_cause("Burned alive")
                self.health = max(0, self.health - dt * 2.5)
            # ---- Insulation & temperature ----
            player_insulation = (CLOTHING_INSULATION.get(self.wearing_pants, 0) +
                                 CLOTHING_INSULATION.get(self.wearing_shirt, 0))
            both_worn = bool(self.wearing_pants and self.wearing_shirt)
            cur_biome_t = biome_at(self.x, self.y)
            # Temperature dynamics (drives display + heat damage)
            if self.on_fire:
                self.temp = 100.0
            elif self.resting and self.rest_mode == "campfire" and self.campfire_fuel > 0:
                if biome_at(self.x, self.y) == "Arctic":
                    # In Arctic: campfire warms you toward body temp (neutral), not to burning
                    self.temp = min(37.0, self.temp + TEMP_CAMPFIRE_RISE * 0.3 * dt)
                else:
                    self.temp = min(70.0, self.temp + TEMP_CAMPFIRE_RISE * 0.5 * dt)
            elif cur_biome_t == "Arctic":
                # Gradient: within 200 coords of border, arctic cold is reduced
                arctic_depth = max(0.0, -dist_to_border(self.x, self.y))  # 0 at border
                GRADIENT_DEPTH = 200.0
                gradient_frac = min(1.0, arctic_depth / GRADIENT_DEPTH)  # 0 at border, 1 at full arctic
                # Effective insulation requirement scales with how deep into Arctic you are
                effective_req = self.arctic_insulation_req * gradient_frac
                deficit = max(0.0, effective_req - player_insulation)
                if effective_req > 0:
                    drop_frac = deficit / max(1.0, effective_req)
                else:
                    drop_frac = 0.0
                if deficit > 0:
                    self.temp = max(0.0, self.temp - TEMP_ARCTIC_DROP * drop_frac * gradient_frac * dt)
                else:
                    warm_rate = TEMP_FOREST_DRIFT * 0.5 + 0.5 * gradient_frac
                    self.temp = min(TEMP_NEUTRAL, self.temp + warm_rate * dt)
            else:
                # Gradient: within 200 coords of border in Forest, drift toward colder.
                forest_dist = dist_to_border(self.x, self.y)  # positive in forest
                GRADIENT_DEPTH = 200.0
                if forest_dist <= GRADIENT_DEPTH:
                    gradient_frac = forest_dist / GRADIENT_DEPTH  # 0 at border, 1 far in forest
                    target = TEMP_NEUTRAL * gradient_frac  # cooler near border
                else:
                    target = TEMP_NEUTRAL
                if self.temp < target:
                    self.temp = min(target, self.temp + TEMP_FOREST_DRIFT * dt)
                elif self.temp > target:
                    self.temp = max(target, self.temp - TEMP_FOREST_DRIFT * dt)
                # Cold damage near the Arctic border even while in Forest, if under-insulated.
                if forest_dist <= GRADIENT_DEPTH:
                    grad = 1.0 - (forest_dist / GRADIENT_DEPTH)  # 1 at border, 0 deep in forest
                    effective_req = self.arctic_insulation_req * grad
                    deficit = max(0.0, effective_req - player_insulation)
                    if deficit > 0 and not (self.resting and self.rest_mode == "campfire" and self.campfire_fuel > 0):
                        self._cold_damaging = True
                        self.note_damage_cause("Hypothermia")
                        cold_rate = (TEMP_COLD_DMG_FULL / GAME_HOUR) * (deficit / max(1.0, effective_req)) * grad
                        self.health = max(0, self.health - cold_rate * dt)
            # Arctic cold damage — insulation-level system (campfire overrides)
            self._cold_damaging = False
            if cur_biome_t == "Arctic" and not (self.resting and self.rest_mode == "campfire" and self.campfire_fuel > 0):
                base_req = self.arctic_insulation_req
                # Gradient: within 200 coords of border, insulation requirement is reduced
                arctic_depth = max(0.0, -dist_to_border(self.x, self.y))
                GRADIENT_DEPTH = 200.0
                gradient_frac = min(1.0, arctic_depth / GRADIENT_DEPTH)
                # Apply gradient to insulation requirement (lower requirement near border)
                effective_req = base_req * gradient_frac
                deficit = max(0.0, effective_req - player_insulation)
                if deficit > 0:
                    self._cold_damaging = True
                    self.note_damage_cause("Hypothermia")
                    cold_rate = (TEMP_COLD_DMG_FULL / GAME_HOUR) * (deficit / max(1.0, effective_req)) * gradient_frac
                    self.health = max(0, self.health - cold_rate * dt)
            # Heat damage (from environment temp, not direct fire) - only in Forest, not Arctic
            if self.temp > TEMP_HOT_THRESH and not self.on_fire and cur_biome_t != "Arctic":
                self.note_damage_cause("Heat stroke")
                hot_frac = (self.temp - TEMP_HOT_THRESH) / (100.0 - TEMP_HOT_THRESH)
                multiplier = 2.0 if both_worn else 1.0
                hot_rate = TEMP_HOT_DMG_FULL / GAME_HOUR * multiplier
                self.health = max(0, self.health - hot_rate * hot_frac * dt)
            # Frostberry transformation: 5 real minutes in warm temp (>= TEMP_NEUTRAL) -> normal berries
            FROSTBERRY_THAW_TIME = 300.0  # 5 minutes
            if self.inventory.get("frostberry", 0) > 0 and self.temp >= 36.0:
                if self.frostberry_warm_since == 0.0:
                    self.frostberry_warm_since = now
                elif (now - self.frostberry_warm_since) >= FROSTBERRY_THAW_TIME:
                    qty = self.inventory.pop("frostberry", 0)
                    self.inventory["wild_berries"] = self.inventory.get("wild_berries", 0) + qty
                    self.frostberry_warm_since = 0.0
                    # (message shown on next render)
                    self._frostberry_thaw_msg = qty
            else:
                self.frostberry_warm_since = 0.0
            # Freezing water transformation: 5 real seconds in warm temp (>= 36°) -> fresh_water
            FREEZING_WATER_THAW_TIME = 5.0  # 5 seconds
            if self.inventory.get("freezing_water", 0) > 0 and self.temp >= 36.0:
                if self.freezing_water_warm_since == 0.0:
                    self.freezing_water_warm_since = now
                elif (now - self.freezing_water_warm_since) >= FREEZING_WATER_THAW_TIME:
                    qty = self.inventory.pop("freezing_water", 0)
                    self.inventory["fresh_water"] = self.inventory.get("fresh_water", 0) + qty
                    self.freezing_water_warm_since = 0.0
                    self._freezing_water_thaw_msg = qty
            else:
                self.freezing_water_warm_since = 0.0
            if self.health <= 0: return "dead"
            # Rest ticking: fires once per GAME_HOUR of real time while resting
            if self.resting and self.rest_last > 0 and (now - self.rest_last) >= GAME_HOUR:
                self.rest_last = now
                self.fatigue = min(MAX_STAT_CAP, self.fatigue + REST_FATIGUE_RATE)
                if self.rest_mode == "campfire" and self.campfire_fuel > 0:
                    self.health = min(self.max_health, self.health + REST_CAMPFIRE_HP)
                    self.energy = min(self.max_energy, self.energy + REST_CAMPFIRE_ENERGY)
                    self.campfire_fuel -= 1
                    if self.campfire_fuel <= 0:
                        self.resting = False; self.rest_mode = None
                        _resume_paused_crafting(self)
                        return "🔥 Campfire fuel exhausted! Resting stopped."
                elif self.rest_mode == "floor":
                    self.health = max(0, self.health - REST_FLOOR_DMG)
                    if self.health <= 0: self.resting = False; return "dead"
                elif self.rest_mode == "house_floor":
                    pass  # Safe floor rest inside house: no damage, just fatigue recovery
                elif self.rest_mode == "house_bed":
                    self.health = min(self.max_health, self.health + int(REST_CAMPFIRE_HP * 1.3))
                    self.energy = min(self.max_energy, self.energy + int(REST_CAMPFIRE_ENERGY * 1.3))
            # Trap ticking: transition setting → caught
            for trap in self.traps:
                if trap.get("status") == "setting" and now >= trap.get("catch_time", 0):
                    catch_chance = 0.65 if self.time_of_day == "night" else 0.45
                    if random.random() < catch_chance:
                        trap["status"] = "caught"
                        self.trap_meat_total += TRAP_MEAT
                    else:
                        # Missed — reset catch window for another attempt
                        trap["catch_time"] = now + TRAP_CATCH_TIME
            for t in list(self.active_tasks):
                if "paused_remaining" in t:
                    continue
                if now >= t["end"]:
                    self.inventory[t["item"]] = self.inventory.get(t["item"], 0) + 1
                    if t["item"] == "plank":
                        self.planks_made = getattr(self, "planks_made", 0) + 1
                    if t["item"] == "poison_trap":
                        self.poison_traps_crafted = getattr(self, "poison_traps_crafted", 0) + 1
                    if t["item"] == "bandages":
                        self.bandages_made = getattr(self, "bandages_made", 0) + 1
                    if t["item"] == "water_filter":
                        self.filtered_water_drank = False
                    if t["item"] == "fire_fuel":
                        self.fire_fuel_crafted = getattr(self, "fire_fuel_crafted", 0) + 1
                    if t["item"] == "oil":
                        self.oil_made = getattr(self, "oil_made", 0) + 1
                    if t["item"] == "smelter":
                        self.smelter_crafted = True
                    self.active_tasks.remove(t)
                    # Set tool durability when crafted
                    if t["item"] == "axe":
                        self.axe_dur = TOOL_DUR
                    elif t["item"] == "advanced_axe":
                        self.axe_dur = TOOL_DUR_ADV
                    elif t["item"] == "pickaxe":
                        self.pickaxe_dur = TOOL_DUR
                    elif t["item"] in SPEAR_DEFS:
                        self.spear_type = t["item"]
                        self.spear_dur = SPEAR_DEFS[t["item"]]["dur"]
                        self.grace_period_over = True
                        # First-spear-craft tutorial trigger
                        if not getattr(self, "first_spear_crafted", False):
                            self.first_spear_crafted = True
                            if not hasattr(self, "pending_tutorials") or self.pending_tutorials is None:
                                self.pending_tutorials = []
                            self.pending_tutorials.append("first_spear")
                    # Set station HP when crafted
                    if t["item"] in self.station_hp:
                        self.station_hp[t["item"]] = STATION_MAX_HP
                    if t.get("yield"):
                        for i, q in t["yield"].items(): self.inventory[i] = self.inventory.get(i,0) + q
                    if t.get("wear"):
                        for st, amt in t["wear"].items():
                            if st in self.station_hp:
                                self.station_hp[st] -= amt
                                if self.station_hp[st] <= 0:
                                    self.inventory[st] = 0
                                    return f"💥 {st.replace('_',' ')} collapsed!"
                    elif t.get("station"):
                        for st in ([t["station"]] if isinstance(t["station"],str) else t["station"]):
                            if st and st in self.station_hp:
                                self.station_hp[st] -= t["igm"]
                                if self.station_hp[st] <= 0:
                                    self.inventory[st] = 0
                                    return f"💥 {st.replace('_',' ')} collapsed!"
                    self.qt_last_finished = t["item"]
                    return f"✅ Finished: {t['item'].replace('_',' ').title()}"

        if now - self.last_day >= DAY_NIGHT_CYCLE:
            self.last_day = now
            self.time_of_day = "night" if self.time_of_day == "day" else "day"
            self.hunger = max(0, self.hunger - DAY_NIGHT_HUNGER_LOSS * getattr(self, "difficulty_mult", NORMAL_HUNGER_MULT))
            # Disease daily/nightly tick
            try:
                _dmsg = []
                disease_daily_tick(self, _dmsg, self.time_of_day)
                if _dmsg:
                    if not hasattr(self, "pending_disease_msgs"):
                        self.pending_disease_msgs = []
                    self.pending_disease_msgs.extend(_dmsg)
            except Exception:
                pass
            return "time_shift"
        return None

    def travel_to(self, dx, dy):
        dist = math.hypot(dx, dy)
        if dist == 0: return 0.0, 0.0
        cost = dist * 0.5
        if self.energy < cost: return 0.0, -1
        spd = SPD_NIGHT if self.time_of_day == "night" else SPD_DAY
        if self.wearing == "heavy_armor": spd *= 0.7
        self.x += dx; self.y += dy
        self.total_travel_mins += (dist * spd) / 60.0
        self.hunger = max(0, self.hunger - dist * HUNGER_TRAVEL_RATE)
        if not is_light(self):
            self.thirst = max(0, self.thirst - dist * THIRST_TRAVEL_RATE)
        self.energy = max(0, self.energy - cost)
        return (dist * spd) / 60.0, dist

    def start_auto_walk(self, tx, ty, world, msg=None):
        self.auto_walk_target = (tx, ty)
        self._detour_count = 0  # Reset detour count for new walk
        if msg is not None:
            msg.append("🚶 Auto-walking...")
            while len(msg) > 3: msg.pop(0)
        return None

    def auto_walk_step(self, world):
        if not self.auto_walk_target:
            return None
        tx, ty = self.auto_walk_target
        dist = math.hypot(tx - self.x, ty - self.y)
        if dist < 0.5:
            self.auto_walk_target = None
            return f"🎯 Arrived at ({tx},{ty})!"
        if self.energy < 0.5:
            self.auto_walk_target = None
            return "⚠️ Stopped: Not enough energy!"
        dx = 1 if tx > self.x else (-1 if tx < self.x else 0)
        dy = 1 if ty > self.y else (-1 if ty < self.y else 0)
        res = self.update_passive()
        # Only cancel autowalk for serious issues, not time_shift
        if res and res not in ("time_shift",):
            self.auto_walk_target = None
            return f"⚠️ Walk interrupted: {res}"
        if res == "time_shift": world.time_of_day = self.time_of_day
        # Note: detour adds *game-time* cost only — never blocks real-time walking,
        # otherwise the player never arrives.
        self.detour_until = 0.0

        cl = world.clusters.get((int(self.x), int(self.y)))
        detour_msg = None
        detour_count = getattr(self, '_detour_count', 0)  # Track detours for this autowalk

        # Skip hazard check if this cluster was recently snoozed
        if cl and cl.get("meta", {}).get("hazard"):
            snooze = cl.get("meta", {}).get("hazard_snooze", 0)
            if snooze and time.time() < snooze:
                cl = None
        if cl and cl.get("meta", {}).get("hazard") and detour_count < 1:
            hk = cl["meta"].get("hazard_key")
            h = HAZARDS.get(hk, {})
            if h and random.random() < h.get("chance", 0.5):
                detour_secs = h.get("detour", 3.0)
                detour_msg = f"🛡️ Hazard detour (+{detour_secs:.1f}s game time)."
                self.total_travel_mins += detour_secs / 60.0
                cl_meta = cl.setdefault("meta", {})
                cl_meta["hazard_snooze"] = time.time() + 6.0
                self._detour_count = detour_count + 1
                # Don't return — keep moving so we actually arrive.


        _, d = self.travel_to(dx, dy)
        if hasattr(self, 'sound') and self.sound and d > 0.01:
            self.sound.play_walk()
        # Finish the walk in the same tick that reaches the destination.  Waiting
        # until the next loop allowed a queued keypress to cancel auto-walk before
        # the guided tutorial received its "arrived_walk" event.
        if math.hypot(tx - self.x, ty - self.y) < 0.5:
            self.auto_walk_target = None
            return f"🎯 Arrived at ({tx},{ty})!"
        return detour_msg

    def has_axe(self):
        return (self.inventory.get("axe", 0) > 0 and self.axe_dur > 0) or \
               (self.inventory.get("advanced_axe", 0) > 0 and self.axe_dur > 0)

    def use_axe(self, items_count=2):
        """Returns (used, break_message_or_None). Deducts durability based on items gathered."""
        dur_cost = 0.5 if items_count == 1 else 1  # 1.65% if 1 item, 3.3% if 2
        if self.inventory.get("advanced_axe", 0) > 0 and self.axe_dur > 0:
            self.axe_dur -= dur_cost
            if self.axe_dur <= 0:
                self.axe_dur = 0; self.inventory["advanced_axe"] = 0
                return True, "💥 Your advanced axe broke!"
            return True, None
        if self.inventory.get("axe", 0) > 0 and self.axe_dur > 0:
            self.axe_dur -= dur_cost
            if self.axe_dur <= 0:
                self.axe_dur = 0; self.inventory["axe"] = 0
                return True, "💥 Your axe broke!"
            return True, None
        return False, None

    def use_pickaxe(self, items_count=2):
        """Returns (used, break_message_or_None). Deducts durability based on items gathered."""
        dur_cost = 0.5 if items_count == 1 else 1  # 1.65% if 1 item, 3.3% if 2
        if self.inventory.get("pickaxe", 0) <= 0 or self.pickaxe_dur <= 0:
            return False, None
        self.pickaxe_dur -= dur_cost
        if self.pickaxe_dur <= 0:
            self.pickaxe_dur = 0; self.inventory["pickaxe"] = 0
            return True, "💥 Your pickaxe broke!"
        return True, None

    def get_unknown_entry(self, category):
        key = f"unknown_{category}"
        if key not in self.inventory or not isinstance(self.inventory.get(key), dict):
            self.inventory[key] = {"qty":0,"items":[],"inspect_tries":0}
        return key, self.inventory[key]

    def count_any_berry(self):
        """Total berry items of any type in inventory (including unknown berries)."""
        known = sum(self.inventory.get(b, 0) for b in BERRY_ITEMS)
        unknown_b = self.inventory.get("unknown_berries", {})
        unk = unknown_b.get("qty", 0) if isinstance(unknown_b, dict) else 0
        return known + unk

    def deduct_any_berry(self, qty):
        """Deduct qty berries from inventory (any type, prioritizing cheapest)."""
        remaining = qty
        # Deduct unknown berries last (they are risky)
        for b in BERRY_ITEMS:
            have = self.inventory.get(b, 0)
            take = min(have, remaining)
            if take > 0:
                self.inventory[b] -= take
                remaining -= take
            if remaining <= 0: break
        if remaining > 0:
            unk_key = "unknown_berries"
            if unk_key in self.inventory and isinstance(self.inventory[unk_key], dict):
                have = self.inventory[unk_key].get("qty", 0)
                take = min(have, remaining)
                if take > 0:
                    self.inventory[unk_key]["qty"] -= take
                    if self.inventory[unk_key]["qty"] <= 0:
                        del self.inventory[unk_key]

    def start_task(self, item, recipe):
        """
        Validate and begin a crafting task.
        Returns (ok: bool, message: str).
        """
        # Queue additional crafts instead of blocking the player behind a single task.
        # The task list already supports multiple concurrent crafts.

        # Station check
        station = recipe.get("station")
        if station:
            stations = [station] if isinstance(station, str) else station
            for st in stations:
                if st and self.inventory.get(st, 0) <= 0:
                    return False, f"❌ Need a {st.replace('_',' ')} station to craft this."

        # Material check — allow filtered_water to substitute for fresh_water
        mat = recipe.get("mat", {})
        # Build effective mat dict with water substitution
        eff_mat = {}
        for k, v in mat.items():
            if k == "fresh_water":
                # Use fresh_water first, then filtered_water if short
                have_fresh = self.inventory.get("fresh_water", 0)
                have_filt  = self.inventory.get("filtered_water", 0)
                if have_fresh >= v:
                    eff_mat["fresh_water"] = v
                elif have_fresh + have_filt >= v:
                    eff_mat["fresh_water"] = have_fresh
                    eff_mat["filtered_water"] = eff_mat.get("filtered_water", 0) + (v - have_fresh)
                else:
                    eff_mat[k] = v  # will trigger missing error
            else:
                eff_mat[k] = v
        missing = []
        for k, v in eff_mat.items():
            have = self.inventory.get(k, 0)
            if have < v:
                display_k = "fresh water or filtered water" if k == "fresh_water" else k.replace("_"," ")
                missing.append(f"{v} {display_k} (have {have})")
        if missing:
            return False, f"❌ Missing: need {', '.join(missing)}."

        # Energy check
        energy_cost = recipe.get("energy", 0)
        if self.energy < energy_cost:
            return False, f"⚡ Need {energy_cost} energy to craft this (have {int(self.energy)})."

        # Deduct materials and energy
        for k, v in eff_mat.items():
            self.inventory[k] = self.inventory.get(k, 0) - v
        self.energy = max(0, self.energy - energy_cost)

        # Schedule task (igm is used as real-time seconds for crafting duration)
        igm = recipe.get("igm", 10)
        # Fast Mode: everything crafts 3x faster.
        igm = max(1, int(round(igm * _CRAFT_TIME_MULT)))
        # Apply half-finished item discount
        prog = getattr(self, 'craft_progress', {}).get(item)
        if prog:
            igm = max(1, igm - int(prog['elapsed']))
            del self.craft_progress[item]
            # Also consume the half-finished item
            half_key = 'half_' + item
            if self.inventory.get(half_key, 0) > 0:
                self.inventory[half_key] -= 1
                if self.inventory[half_key] <= 0:
                    del self.inventory[half_key]
        task = {
            "item": item,
            "end": time.time() + igm,
            "igm": igm,
            "station": station,
            "mat_used": dict(eff_mat),
        }
        if recipe.get("yield"):
            task["yield"] = recipe["yield"]
        if recipe.get("wear"):
            task["wear"] = recipe["wear"]
        self.active_tasks.append(task)
        snd = getattr(self, "sound", None)
        if snd and getattr(snd, "enabled", False):
            snd.play_craft(station if isinstance(station, str) else (station[0] if station else None))
        return True, f"🔨 Crafting {item.replace('_',' ').title()}... ({igm}s)"

# ==================== BIOME GEOGRAPHY ====================
def biome_at(x, y):
    """Return the biome name for world coordinates (x, y).
    Forest is a disc of radius FOREST_RADIUS centred on the origin.
    Arctic covers everything outside that disc.
    """
    return "Forest" if math.hypot(x, y) < FOREST_RADIUS else "Arctic"


def dist_to_border(x, y):
    """Signed distance to the Forest/Arctic border (positive = still in Forest)."""
    return FOREST_RADIUS - math.hypot(x, y)


# ==================== WORLD ====================
# ==================== DISTANT-WORLD SQLITE COLD STORAGE ====================
# Anything farther than OFFLOAD_RADIUS tiles from the player is written out to a
# local SQLite database together with the wall-clock timestamp it was stored at,
# then dropped from memory.  This keeps every per-tick loop (regen, animal AI,
# rendering, fire, evaporation...) working on a small nearby set instead of the
# whole explored world, which is where the lag came from.  When the player walks
# back into range the rows are read back and "lazily simulated" forward using the
# stored timestamp, so nothing feels frozen in time while it was offloaded.

OFFLOAD_RADIUS = 100.0        # farther than this -> to SQLite
RELOAD_RADIUS = 92.0          # closer than this -> back into memory (hysteresis)
OFFLOAD_INTERVAL = 2.0        # seconds between sweeps

class WorldStore:
    """SQLite-backed cold storage for far-away clusters and animals."""

    def __init__(self, path=None):
        self.conn = None
        self.path = None
        try:
            import sqlite3
            base = os.path.join(os.path.expanduser("~"), ".9planets")
            os.makedirs(base, exist_ok=True)
            self.path = path or os.path.join(base, "world_cache.db")
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=OFF")
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS clusters ("
                " x INTEGER, y INTEGER, data TEXT, stored_at REAL,"
                " PRIMARY KEY (x, y))")
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS animals ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " x REAL, y REAL, data TEXT, stored_at REAL)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_animals_xy ON animals(x, y)")
            self.conn.commit()
        except Exception:
            self.conn = None

    # -- lifecycle ---------------------------------------------------------
    def reset(self):
        """Wipe the cache (called when a fresh world/session starts)."""
        if not self.conn: return
        try:
            self.conn.execute("DELETE FROM clusters")
            self.conn.execute("DELETE FROM animals")
            self.conn.commit()
        except Exception:
            pass

    def close(self):
        if not self.conn: return
        try: self.conn.commit(); self.conn.close()
        except Exception: pass
        self.conn = None

    # -- clusters ----------------------------------------------------------
    def put_clusters(self, rows, now):
        """rows: iterable of ((x, y), cluster_dict)"""
        if not self.conn: return
        payload = []
        for (x, y), cl in rows:
            try:
                payload.append((int(x), int(y), json.dumps(cl), now))
            except Exception:
                continue
        if not payload: return
        try:
            self.conn.executemany(
                "INSERT OR REPLACE INTO clusters (x, y, data, stored_at) VALUES (?,?,?,?)",
                payload)
            self.conn.commit()
        except Exception:
            pass

    def pop_cluster(self, x, y):
        """Take one cluster back out of cold storage. Returns (cluster, stored_at)."""
        if not self.conn: return None, 0.0
        try:
            cur = self.conn.execute(
                "SELECT data, stored_at FROM clusters WHERE x=? AND y=?", (int(x), int(y)))
            row = cur.fetchone()
            if not row: return None, 0.0
            self.conn.execute("DELETE FROM clusters WHERE x=? AND y=?", (int(x), int(y)))
            self.conn.commit()
            return json.loads(row[0]), float(row[1] or 0.0)
        except Exception:
            return None, 0.0

    def pop_clusters_near(self, px, py, radius):
        """Take every cluster inside the box back out. Returns [((x,y), cl, stored_at)]."""
        if not self.conn: return []
        r = int(radius) + 1
        try:
            cur = self.conn.execute(
                "SELECT x, y, data, stored_at FROM clusters"
                " WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ?",
                (int(px) - r, int(px) + r, int(py) - r, int(py) + r))
            rows = cur.fetchall()
            out = []
            keys = []
            for x, y, data, stored_at in rows:
                if math.hypot(x - px, y - py) > radius:
                    continue
                try:
                    out.append(((int(x), int(y)), json.loads(data), float(stored_at or 0.0)))
                    keys.append((int(x), int(y)))
                except Exception:
                    continue
            if keys:
                self.conn.executemany("DELETE FROM clusters WHERE x=? AND y=?", keys)
                self.conn.commit()
            return out
        except Exception:
            return []

    def all_clusters(self):
        """Every cold cluster, for saving the game. Returns {(x,y): cluster}."""
        if not self.conn: return {}
        out = {}
        try:
            for x, y, data in self.conn.execute("SELECT x, y, data FROM clusters"):
                try: out[(int(x), int(y))] = json.loads(data)
                except Exception: pass
        except Exception:
            pass
        return out

    # -- animals -----------------------------------------------------------
    def put_animals(self, animals, now):
        if not self.conn or not animals: return
        payload = []
        for a in animals:
            try:
                payload.append((float(a.get("x", 0.0)), float(a.get("y", 0.0)),
                                json.dumps(a), now))
            except Exception:
                continue
        if not payload: return
        try:
            self.conn.executemany(
                "INSERT INTO animals (x, y, data, stored_at) VALUES (?,?,?,?)", payload)
            self.conn.commit()
        except Exception:
            pass

    def pop_animals_near(self, px, py, radius):
        """Returns [(animal_dict, stored_at)] for animals back inside range."""
        if not self.conn: return []
        r = float(radius) + 1.0
        try:
            cur = self.conn.execute(
                "SELECT id, data, stored_at FROM animals"
                " WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ?",
                (px - r, px + r, py - r, py + r))
            rows = cur.fetchall()
            out, ids = [], []
            for rid, data, stored_at in rows:
                try:
                    a = json.loads(data)
                except Exception:
                    ids.append((rid,)); continue
                if math.hypot(a.get("x", 0.0) - px, a.get("y", 0.0) - py) > radius:
                    continue
                out.append((a, float(stored_at or 0.0)))
                ids.append((rid,))
            if ids:
                self.conn.executemany("DELETE FROM animals WHERE id=?", ids)
                self.conn.commit()
            return out
        except Exception:
            return []

    def all_animals(self):
        if not self.conn: return []
        out = []
        try:
            for (data,) in self.conn.execute("SELECT data FROM animals"):
                try: out.append(json.loads(data))
                except Exception: pass
        except Exception:
            pass
        return out

    def counts(self):
        if not self.conn: return (0, 0)
        try:
            c = self.conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0]
            a = self.conn.execute("SELECT COUNT(*) FROM animals").fetchone()[0]
            return (int(c), int(a))
        except Exception:
            return (0, 0)


class World:
    def __init__(self, biome, time_of_day):
        self.biome = biome; self.time_of_day = time_of_day
        self.clusters = {}; self.depleted = set()
        self.last_regen = time.time()
        self.last_fire_tick = 0.0
        self.animals = []
        self.last_spawn = 0.0
        self.last_young_spawn = 0.0
        self.arctic_weather_mods = {}  # item → {cluster_rate_mult, qty_mult}
        self.houses = []              # list of placed house dicts
        self.game_start_real_time = time.time()   # for lazy weather history simulation
        # Distant world data (>100 tiles away) lives in SQLite instead of RAM.
        self.store = WorldStore()
        self.store.reset()
        self._last_offload = 0.0

    # ---------- SQLite cold storage for distant world data ----------
    def _simulate_cluster_offline(self, cl, stored_at):
        """Lazy simulation: fast-forward a cluster by the time it spent in SQLite."""
        now = time.time()
        elapsed = max(0.0, now - (stored_at or now))
        if elapsed <= 0:
            return cl
        try:
            meta = cl.get("meta", {}) or {}
            # Regrowing resources keep growing while offloaded (1 unit / game-hour).
            if meta.get("regrows", False):
                grow = int(elapsed // max(1.0, GAME_HOUR))
                if grow > 0:
                    cl["qty"] = min(50, int(cl.get("qty", 1)) + grow)
            # Fires burn out while nobody is watching.
            if meta.get("is_burning") and elapsed > GAME_HOUR:
                meta["is_burning"] = False
                meta["is_ash"] = True
                cl["meta"] = meta
                cl["display"] = "🌫️ Ash"
            # Shift any absolute timestamps so they stay relative to "now".
            for key in ("last_regen", "last_move", "birth_time", "planted_at", "end"):
                if isinstance(cl.get(key), (int, float)) and cl[key] > 0:
                    cl[key] = cl[key] + elapsed
        except Exception:
            pass
        return cl

    def _simulate_animal_offline(self, a, stored_at):
        """Lazy simulation: animals drift, heal and age while stored in SQLite."""
        now = time.time()
        elapsed = max(0.0, now - (stored_at or now))
        a["last_move"] = now
        if elapsed <= 0:
            return a
        try:
            # Wander: random drift that grows with time, capped so they stay in the area.
            drift = min(20.0, math.sqrt(elapsed) * 0.5)
            ang = random.uniform(0, 2 * math.pi)
            a["x"] = a.get("x", 0.0) + drift * math.cos(ang)
            a["y"] = a.get("y", 0.0) + drift * math.sin(ang)
            # Heal roughly 1 HP per game-hour spent away.
            mx = a.get("max_hp", a.get("hp", 1))
            heal = elapsed / max(1.0, GAME_HOUR)
            a["hp"] = min(mx, a.get("hp", mx) + heal)
            a["fleeing"] = False
            for key in ("birth_time", "last_attack", "interest_until", "flee_until"):
                if isinstance(a.get(key), (int, float)) and a[key] > 0:
                    a[key] = a[key] + elapsed
        except Exception:
            pass
        return a

    def offload_distant(self, player, force=False):
        """Move everything farther than OFFLOAD_RADIUS into SQLite, and bring
        anything back that is within RELOAD_RADIUS again."""
        store = getattr(self, "store", None)
        if not store or not store.conn:
            return
        now = time.time()
        if not force and now - getattr(self, "_last_offload", 0.0) < OFFLOAD_INTERVAL:
            return
        self._last_offload = now
        px, py = player.x, player.y

        # --- push far clusters out of RAM ---
        far = [(k, c) for k, c in self.clusters.items()
               if math.hypot(k[0] - px, k[1] - py) > OFFLOAD_RADIUS]
        if far:
            store.put_clusters(far, now)
            for k, _ in far:
                self.clusters.pop(k, None)

        # --- push far animals out of RAM ---
        near_animals, far_animals = [], []
        for a in self.animals:
            if math.hypot(a.get("x", 0.0) - px, a.get("y", 0.0) - py) > OFFLOAD_RADIUS:
                far_animals.append(a)
            else:
                near_animals.append(a)
        if far_animals:
            store.put_animals(far_animals, now)
            self.animals = near_animals

        # --- pull anything back that is in range again (with lazy simulation) ---
        for key, cl, stored_at in store.pop_clusters_near(px, py, RELOAD_RADIUS):
            if key in self.depleted or key in self.clusters:
                continue
            self.clusters[key] = self._simulate_cluster_offline(cl, stored_at)
        for a, stored_at in store.pop_animals_near(px, py, RELOAD_RADIUS):
            self.animals.append(self._simulate_animal_offline(a, stored_at))

    def all_clusters_for_save(self):
        """In-memory + cold-stored clusters, merged for the save file."""
        merged = {}
        store = getattr(self, "store", None)
        if store:
            merged.update(store.all_clusters())
        merged.update(self.clusters)
        return merged

    def all_animals_for_save(self):
        store = getattr(self, "store", None)
        cold = store.all_animals() if store else []
        return list(self.animals) + cold

    def seed_initial_animals(self, player, radius=FOG_RADIUS*2):
        if biome_at(player.x, player.y) != "Forest":
            return
        now = time.time()
        def add_animal(animal_type, min_r, max_r, birth_time=None):
            for _attempt in range(8):
                angle = random.uniform(0, 2 * math.pi)
                r = random.uniform(min_r, max_r)
                x = player.x + r * math.cos(angle)
                y = player.y + r * math.sin(angle)
                if biome_at(x, y) != "Forest":
                    continue
                # Don't stack animals on top of each other
                if any(math.hypot(a["x"]-x, a["y"]-y) < 2.0 for a in self.animals):
                    continue
                adef = ANIMAL_DEFS[animal_type]
                entry = {
                    "type": animal_type,
                    "x": x,
                    "y": y,
                    "hp": adef["hp"],
                    "max_hp": adef["hp"],
                    "fleeing": False,
                    "last_move": now,
                }
                if birth_time is not None:
                    entry["birth_time"] = birth_time
                self.animals.append(entry)
                return True
            return False

        # Seed many animals so they're spread throughout the world from day 1.
        # Animals are spread over a wide radius so the player encounters them
        # while exploring, not just sitting at spawn.
        for _ in range(8):
            add_animal("rabbit", 4, min(radius, 60))
        for _ in range(6):
            add_animal("squirrel", 4, min(radius, 60))
        for _ in range(4):
            add_animal("deer", 8, min(radius, 80))
        for _ in range(3):
            add_animal("antelope", 10, min(radius, 100))
        # A couple of cats spread out
        for _ in range(2):
            add_animal("cat", 6, min(radius, 50))
        # Seed baby animals alongside adults — use a fresh birth_time so they mature
        for _ in range(4):
            add_animal("young_rabbit", 4, min(radius, 60), birth_time=now)
        for _ in range(3):
            add_animal("young_squirrel", 4, min(radius, 60), birth_time=now)
        for _ in range(2):
            add_animal("young_deer", 8, min(radius, 80), birth_time=now)
        for _ in range(1):
            add_animal("young_antelope", 10, min(radius, 100), birth_time=now)

    def spawn_young_animals(self, player):
        now = time.time()
        # Check much more frequently: every 60 s instead of 360 s
        if now - self.last_young_spawn < 60.0:
            return
        self.last_young_spawn = now
        if biome_at(player.x, player.y) != "Forest":
            return
        def count_animals(animal_type):
            """Count ALL animals of this type in the world (not just near player)."""
            return sum(1 for a in self.animals if a["type"] == animal_type)

        adult_pairs = [
            ("rabbit", "young_rabbit"),
            ("squirrel", "young_squirrel"),
            ("deer", "young_deer"),
            ("antelope", "young_antelope"),
        ]

        for adult_type, young_type in adult_pairs:
            adults = count_animals(adult_type)
            existing_young = count_animals(young_type)
            # Each adult has a strong chance to produce a baby every cycle.
            # Target: at least as many babies as adults (1:1 ratio).
            target_young = adults
            spawn_needed = max(0, target_young - existing_young)
            for _ in range(spawn_needed):
                # Roll a high per-adult chance so babies appear quickly
                if random.random() > 0.85:
                    continue
                # Spread babies anywhere in a wide radius (not just near player)
                angle = random.uniform(0, 2 * math.pi)
                r = random.uniform(3, FOG_RADIUS * 2)
                gx = player.x + r * math.cos(angle)
                gy = player.y + r * math.sin(angle)
                if biome_at(gx, gy) != "Forest":
                    continue
                adef = ANIMAL_DEFS[young_type]
                self.animals.append({
                    "type": young_type,
                    "x": gx + random.uniform(-2, 2),
                    "y": gy + random.uniform(-2, 2),
                    "hp": adef["hp"],
                    "max_hp": adef["hp"],
                    "fleeing": False,
                    "last_move": now,
                    "birth_time": now,
                })
        self.arctic_weather_type = "neutral"

    def _hash(self, x, y, pos_biome=None):
        import zlib
        b = pos_biome or biome_at(x, y)
        return zlib.crc32(f"{b}_{self.time_of_day}_{x}_{y}".encode()) & 0xFFFFFFFF

    def _determine_type(self, meta):
        item = meta["item"]
        if item.startswith("moss"):
            r = random.random(); acc = 0
            for m in MOSS_TYPES:
                acc += m["chance"]
                if r <= acc: return m["id"], "moss"
            return "moss_harmful", "moss"
        if item in ["mushrooms","mushroom_death_cap","mystery_mushroom","black_trumpets","spotted_mushrooms"]:
            r = random.random(); acc = 0
            for m in MUSHROOM_TYPES:
                acc += m["chance"]
                if r <= acc: return m["id"], "mushrooms"
            return "mushrooms", "mushrooms"
        if item in ["berries","wild_berries","sweet_berries","sour_berries","glowing_berries","frostberry","shimmer_frostberry","poisonous_berry"]:
            r = random.random(); acc = 0
            for b in BERRY_TYPES:
                acc += b["chance"]
                if r <= acc: return b["id"], "berries"
            return "wild_berries", "berries"
        if item == "water":
            if random.random() < 0.10:
                return "fresh_water", "water"
            return "dirty_water", "water"
        if item == "arctic_water":
            return ("freezing_water","water") if random.random() < 0.60 else ("freezing_dirty_water","water")
        if item == "snow":      return "snow", "material"
        if item == "ice_chunk": return "ice_chunk", "material"
        if item == "ash":       return "ash", "material"
        if item == "spider_silk": return item, "spider_silk"
        if item == "venom_sac":   return item, "venom_sac"
        if item == "night_bug":   return item, "bugs"
        return item, "standard"

    def _simulate_history(self, x, y, cluster):
        """Apply retroactive weather simulation for all real-time elapsed since game start."""
        elapsed = time.time() - self.game_start_real_time
        if elapsed < 3600:
            return   # Less than 1 real hour — skip
        hours = min(int(elapsed / 3600), 168)  # cap at 1 week to avoid massive swings
        pos_biome = biome_at(x, y)
        hrng = random.Random(self._hash(x, y, "hist"))
        for h in range(hours):
            hrng.seed(self._hash(x, y, "hist") + h * 9973)
            roll = hrng.random()
            ri = cluster["real_item"]
            meta = cluster.get("meta", {})
            if pos_biome == "Forest":
                if roll < 0.12:   # rain: berries/mushrooms/water grow
                    if ri in ("berries", "mushrooms", "water", "fresh_water", "dirty_water"):
                        cluster["qty"] = min(50, cluster["qty"] + hrng.randint(1, 3))
                elif roll < 0.22: # drought: water clusters thin
                    if ri in ("water", "fresh_water", "dirty_water"):
                        cluster["qty"] = max(1, cluster["qty"] - hrng.randint(1, 2))
                elif roll < 0.32: # windfall: wood grows
                    if ri == "wood":
                        cluster["qty"] = min(50, cluster["qty"] + hrng.randint(1, 4))
                elif roll < 0.40: # natural growth (regrows items)
                    if meta.get("regrows"):
                        cluster["qty"] = min(50, cluster["qty"] + 1)
            else:  # Arctic
                if roll < 0.20:   # snowfall: snow/ice grows
                    if ri in ("snow", "ice_chunk"):
                        cluster["qty"] = min(50, cluster["qty"] + hrng.randint(1, 3))
                elif roll < 0.30: # warmth: snow thins
                    if ri == "snow":
                        cluster["qty"] = max(1, cluster["qty"] - hrng.randint(1, 2))
                elif roll < 0.38: # frost: arctic_water freezes / thickens
                    if ri in ("arctic_water", "snow"):
                        cluster["qty"] = min(50, cluster["qty"] + 1)

    def _load(self, x, y):
        if (x,y) in self.depleted: return None
        if (x,y) in self.clusters: return self.clusters[(x,y)]
        # It may have been offloaded to SQLite while the player was far away.
        _cold, _stored_at = self.store.pop_cluster(x, y)
        if _cold is not None:
            self._simulate_cluster_offline(_cold, _stored_at)
            self.clusters[(x,y)] = _cold
            return _cold
        pos_biome = biome_at(x, y)
        rng = random.Random(self._hash(x, y, pos_biome))
        base_pool = list(BIOME_RESOURCES.get(pos_biome, {}).items())
        if self.time_of_day == "night": base_pool.extend(NIGHT_RESOURCES[pos_biome].items())
        candidates = []
        for name, meta in base_pool:
            # Reduced spawn chances for more even distribution (sparse, not dense)
            chance = 0.45
            if meta["item"] in ["wood","water","fibergrass","rock"]: chance = 0.55
            elif meta["item"] == "bee_hive": chance = 0.20
            elif meta["item"] == "ironroot": chance = 0.35
            elif meta["item"] in ["berries","mushrooms"]: chance = 0.50
            # Trees are very rare in Arctic (wood not in Arctic BIOME_RESOURCES so this applies to any stray spawns)
            if pos_biome == "Arctic" and meta["item"] == "wood": chance = 0.03
            # Apply arctic weather modifiers to spawn chance
            if pos_biome == "Arctic" and self.arctic_weather_mods:
                rate_m = self.arctic_weather_mods.get(meta["item"], {}).get("cluster_rate_mult", 1.0)
                chance *= rate_m
            if rng.random() < chance: candidates.append((name, meta))
        if not candidates: return None
        name, meta = rng.choice(candidates)
        real_item, category = self._determine_type(meta)
        is_identified = real_item in ALWAYS_IDENTIFIED
        if is_identified:
            display_name = DISPLAY_ITEM_NAME_MAP.get(real_item, name)
        else:
            display_name = UNKNOWN_NAME_MAP.get(real_item, f"❓ Unknown {category.title()}")
        qty = 1 if meta["item"] == "bee_hive" else min(50, rng.randint(4, 12))
        # Apply arctic weather qty modifier
        if pos_biome == "Arctic" and self.arctic_weather_mods:
            qty_m = self.arctic_weather_mods.get(meta["item"], {}).get("qty_mult", 1.0)
            qty = max(1, int(qty * qty_m))
        cl = {
            "name": display_name, "real_item": real_item, "category": category,
            "is_identified": is_identified, "inspection_attempts": 0,
            "pos": [x,y], "qty": qty, "meta": meta,
            "dominant": True,   # this cluster occupies the tile
            "sub_cluster": None,
        }
        # ~20% chance: generate a hidden sub_cluster competing beneath this one
        if rng.random() < 0.20 and len(candidates) > 1:
            sub_candidates = [(n, m) for n, m in candidates if m is not meta]
            if sub_candidates:
                sub_name, sub_meta = rng.choice(sub_candidates)
                sub_real, sub_cat = self._determine_type(sub_meta)
                sub_identified = sub_real in ALWAYS_IDENTIFIED
                sub_display = DISPLAY_ITEM_NAME_MAP.get(sub_real, sub_name) if sub_identified \
                              else UNKNOWN_NAME_MAP.get(sub_real, f"❓ Unknown {sub_cat.title()}")
                sub_qty = max(1, rng.randint(2, max(2, qty // 2)))
                cl["sub_cluster"] = {
                    "name": sub_display, "real_item": sub_real, "category": sub_cat,
                    "is_identified": sub_identified, "inspection_attempts": 0,
                    "pos": [x, y], "qty": sub_qty, "meta": sub_meta,
                    "dominant": False, "sub_cluster": None,
                }
        self.clusters[(x,y)] = cl
        # Lazy history simulation: apply retroactive weather to this newly explored tile
        self._simulate_history(x, y, cl)
        if cl.get("sub_cluster"):
            self._simulate_history(x, y, cl["sub_cluster"])
        # Add sand next to water sources
        if real_item in ("water", "fresh_water", "dirty_water"):
            sand_qty = int(qty * (1.5 if real_item == "fresh_water" else 0.5))
            if sand_qty > 0:
                sand_pos = (x + 1, y)
                if sand_pos not in self.clusters and sand_pos not in self.depleted:
                    self.clusters[sand_pos] = {
                        "name": "Sand Pile", "real_item": "sand", "category": "material",
                        "is_identified": True, "inspection_attempts": 0,
                        "pos": [sand_pos[0], sand_pos[1]], "qty": sand_qty,
                        "meta": {"item": "sand", "regrows": False},
                        "dominant": True, "sub_cluster": None,
                    }
        return self.clusters[(x,y)]

    def inspect_cluster(self, player, cl):
        if cl["is_identified"]: return False, "✅ Already identified."
        if cl["inspection_attempts"] >= MAX_INSPECTIONS:
            return False, f"⚠️ Max inspections reached ({MAX_INSPECTIONS})."
        if player.inventory.get("id_lens",0) > 0:
            player.inventory["id_lens"] -= 1
            cl["is_identified"] = True
            cl["name"] = display_item_name(cl["real_item"])
            return True, f"🔍 Lens used! Identified as {cl['name']}."
        if player.energy < INSPECT_COST: return False, "⚡ Not enough energy (need 5)."
        player.energy -= INSPECT_COST
        cl["inspection_attempts"] += 1
        chance = min(1.0, IDENTIFY_CHANCES.get(cl["real_item"],0.0) + player.inventory.get("textbook",0)*0.1)
        if random.random() <= chance:
            cl["is_identified"] = True
            cl["name"] = display_item_name(cl["real_item"])
            return True, f"✅ Identified as {cl['name']}! ({cl['inspection_attempts']}/{MAX_INSPECTIONS})"
        return False, f"❌ Failed. ({cl['inspection_attempts']}/{MAX_INSPECTIONS} attempts used)"

    def scan(self, px, py):
        results = []; r2 = FOG_RADIUS**2; to_remove = []
        seen_pos = set()
        for dx in range(-FOG_RADIUS, FOG_RADIUS+1):
            for dy in range(-FOG_RADIUS, FOG_RADIUS+1):
                if dx*dx+dy*dy > r2: continue
                pos = (px+dx, py+dy)
                if pos in seen_pos: continue
                seen_pos.add(pos)
                c = self._load(pos[0], pos[1])
                if not c or c.get("qty",0) <= 0:
                    if c:
                        self.depleted.add(pos)
                        to_remove.append(pos)
                    continue
                # Ensure cluster always has a "pos" entry (some code paths
                # create clusters without it, which used to raise KeyError).
                if "pos" not in c:
                    c["pos"] = [pos[0], pos[1]]
                d = math.hypot(pos[0]-px, pos[1]-py)
                results.append((c, d))
        for pos in to_remove:
            self.clusters.pop(pos, None)
        return sorted(results, key=lambda x: x[1])

    def regen(self):
        now = time.time()
        if now - self.last_regen >= 30:
            self.last_regen = now
            # Remove fibergrass from Arctic (misplaced at border)
            for pos in [p for p, c in list(self.clusters.items()) if c.get("real_item") == "fibergrass" and biome_at(p[0], p[1]) == "Arctic"]:
                del self.clusters[pos]
            # Remove forest-only animals from Arctic
            _arctic_forest_only = ("rabbit","young_rabbit","squirrel","young_squirrel","deer","young_deer","antelope","young_antelope")
            self.animals = [a for a in self.animals if not (a["type"] in _arctic_forest_only and biome_at(a["x"], a["y"]) == "Arctic")]
            new_spillovers = {}
            for pos, c in list(self.clusters.items()):
                if c.get("qty",0) <= 0:
                    sub = c.get("sub_cluster")
                    if sub and sub.get("qty", 0) > 0:
                        # Promote sub_cluster to dominant
                        sub["dominant"] = True; sub["pos"] = list(pos)
                        self.clusters[pos] = sub
                        self.depleted.discard(pos)
                    else:
                        self.depleted.add(pos)
                        del self.clusters[pos]
                    continue
                if c.get("meta",{}).get("regrows") and c["qty"] < 100 and random.random() < 0.3:
                    c["qty"] += 1
                # --- Cluster competition logic ---
                sub = c.get("sub_cluster")
                if sub and sub.get("qty", 0) > 0:
                    pos_biome = biome_at(pos[0], pos[1])
                    # Weather favorability for each cluster
                    wx_mods = self.arctic_weather_mods if pos_biome == "Arctic" else {}
                    dom_rate = wx_mods.get(c["real_item"], {}).get("cluster_rate_mult", 1.0)
                    sub_rate = wx_mods.get(sub["real_item"], {}).get("cluster_rate_mult", 1.0)
                    # Dominant grows if weather favors it; recessive suppressed unless weather favors it
                    if dom_rate >= 1.0:
                        c["qty"] = min(50, c["qty"] + 1)
                    if sub_rate > 1.0:
                        sub["qty"] = min(50, sub["qty"] + 1)
                    elif dom_rate >= 1.0 and random.random() < 0.4:
                        # Dominant suppresses sub
                        sub["qty"] = max(0, sub["qty"] - 1)
                    # If sub outgrows dominant, they swap
                    if sub["qty"] > c["qty"]:
                        c["dominant"], sub["dominant"] = False, True
                        self.clusters[pos], c["sub_cluster"] = sub, c
                        c["sub_cluster"]["sub_cluster"] = c
                # Spillover: if > 50, split excess to adjacent coord
                if c.get("qty", 0) > 50:
                    excess = c["qty"] - 50
                    c["qty"] = 50
                    for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                        npos = (pos[0]+dx, pos[1]+dy)
                        if npos not in self.clusters and npos not in new_spillovers:
                            import copy
                            nc = copy.copy(c)
                            nc["qty"] = min(excess, 25)
                            nc["pos"] = [npos[0], npos[1]]
                            nc["sub_cluster"] = None  # spillovers start fresh
                            new_spillovers[npos] = nc
                            break
            self.clusters.update(new_spillovers)

    def update_fire(self, weather, player):
        now = time.time()
        if now - self.last_fire_tick < 2.0:
            return
        self.last_fire_tick = now
        if not weather.firestorm_active:
            return

        water_items = {"water", "fresh_water", "dirty_water", "freezing_water", "freezing_dirty_water", "arctic_water"}
        burning = [pos for pos,c in self.clusters.items() if c.get("meta",{}).get("is_burning")]
        if not burning:
            weather.firestorm_active = False
            return

        water_clusters = [(pos,c) for pos,c in self.clusters.items() if c.get("real_item") in water_items]

        def extinguished_by_water(pos):
            for wpos,wcl in water_clusters:
                radius = wcl.get("qty", 0) / 2.0
                if radius > 0 and math.hypot(pos[0]-wpos[0], pos[1]-wpos[1]) <= radius:
                    return True
            return False

        def convert_to_ash(pos):
            if pos not in self.clusters:
                return
            self.clusters[pos] = {
                "name": "💨 Ash Pile", "real_item": "ash", "category": "material",
                "is_identified": True, "inspection_attempts": 0,
                "pos": [pos[0], pos[1]], "qty": max(1, int(self.clusters[pos].get("qty", 1))),
                "meta": {"regrows": False, "hazard_key": None, "is_ash": True}
            }

        new_ignites = []
        to_ash = []
        for pos in burning:
            if extinguished_by_water(pos):
                to_ash.append(pos)
                continue
            if random.random() < 0.20:
                to_ash.append(pos)
                continue
            if random.random() >= 0.60:
                continue

            candidates = []
            for qpos,qcl in self.clusters.items():
                if qpos == pos: continue
                if qcl.get("meta",{}).get("is_burning"): continue
                if qcl.get("real_item") in ("ash", "fire") or qcl.get("real_item") in water_items:
                    continue
                if math.hypot(qpos[0]-pos[0], qpos[1]-pos[1]) > 3:
                    continue
                candidates.append(qpos)
            if not candidates:
                continue

            target = random.choice(candidates)
            if extinguished_by_water(target):
                to_ash.append(target)
            else:
                new_ignites.append(target)

        for pos in set(to_ash):
            convert_to_ash(pos)
        for pos in set(new_ignites):
            if pos in self.clusters and not self.clusters[pos].get("meta",{}).get("is_burning"):
                self.clusters[pos] = {
                    "name": "🔥 Fire", "real_item": "fire", "category": "hazard",
                    "is_identified": True, "inspection_attempts": 0,
                    "pos": [pos[0], pos[1]], "qty": 1,
                    "meta": {"regrows": False, "hazard_key": None, "is_burning": True}
                }

        if not any(c.get("meta",{}).get("is_burning") for c in self.clusters.values()):
            weather.firestorm_active = False

    def spawn_animals(self, player):
        now = time.time()
        if now - self.last_spawn < 30.0: return
        self.last_spawn = now
        beginner_mode = getattr(player, "difficulty_mult", NORMAL_HUNGER_MULT) <= BEGINNER_HUNGER_MULT
        if beginner_mode:
            self.animals = [a for a in self.animals if a.get("type") not in ("grot", "grot_leader")]
        cur_biome = biome_at(player.x, player.y)
        spawned = False
        counts = {}
        for a in self.animals:
            if abs(a["x"] - player.x) <= FOG_RADIUS * 2 and abs(a["y"] - player.y) <= FOG_RADIUS * 2:
                counts[a["type"]] = counts.get(a["type"],0) + 1

        def can_spawn_here(x, y):
            if math.hypot(x - player.x, y - player.y) < 2.5:
                return False
            return all(math.hypot(a.get("x", 0.0) - x, a.get("y", 0.0) - y) >= 3.0 for a in self.animals)

        # Forest animals (rabbit, squirrel, deer, antelope, cat) are seeded at
        # game start only — no mid-game spawning, so the player must explore to
        # find them.  Grots + Arctic animals still spawn on their existing logic.

        # Handle other animal types (salmon, seal, penguin in Arctic; these keep old spawn_rate logic)
        for atype, adef in ANIMAL_DEFS.items():
            if adef["biome"] == "Forest": continue  # Forest animals are handled above
            if beginner_mode and atype in ("grot", "grot_leader"):
                continue
            if not biome_matches(adef, cur_biome): continue
            max_count = 3 if atype == "grot" else 2
            if counts.get(atype,0) >= max_count: continue
            if atype == "grot_leader":
                continue  # grot_leaders are promoted from grots at spawn time (20% chance)
            if atype == "grot":
                if player.hidden_xp < 10:
                    continue
                if player.hidden_xp < 40:
                    grot_chance = 0.04
                elif player.hidden_xp < 100:
                    grot_chance = 0.08
                elif player.hidden_xp < 140:
                    grot_chance = 0.12
                else:
                    grot_chance = 0.16
                if getattr(player, 'mode', 'quest') in ("combat", "explorer_combat"):
                    grot_chance = min(0.95, grot_chance * 2.0)
                if random.random() > grot_chance:
                    continue
            elif random.random() > adef["spawn_rate"]:
                continue
            gmin, gmax = adef["group"]
            group_size = random.randint(gmin, gmax)
            angle = random.uniform(0, 2*math.pi)
            r = random.uniform(3, FOG_RADIUS-2)
            gx = player.x + r * math.cos(angle)
            gy = player.y + r * math.sin(angle)
            grot_stats_data = None
            if atype == "grot":
                # In 'combat' mode, remove the grace period so grots are always full-strength
                if getattr(player, 'mode', 'quest') in ('combat', 'explorer_combat'):
                    grace_flag = False
                else:
                    grace_flag = not player.grace_period_over
                grot_stats_data = grot_stats(player.hidden_xp, grace=grace_flag)
            if not can_spawn_here(gx, gy):
                continue
            for _ in range(group_size):
                ax = gx + random.uniform(-2, 2)
                ay = gy + random.uniform(-2, 2)
                if not can_spawn_here(ax, ay):
                    continue
                animal_entry = {
                    "type": atype, "x": ax, "y": ay,
                    "fleeing": False, "last_move": now,
                }
                if atype == "grot":
                    # 1-in-5 chance to promote a grot to grot_leader
                    if random.random() < 0.20:
                        animal_entry["type"] = "grot_leader"
                        ldr_def = ANIMAL_DEFS["grot_leader"]
                        animal_entry.update({
                            "hp": ldr_def["hp"], "max_hp": ldr_def["hp"],
                            "atk": grot_stats_data.get("atk", 2) + 1,
                            "def": grot_stats_data.get("def", 0) + 1,
                            "speed_cpm": ldr_def["speed_cpm"],
                            "vision_max": ldr_def["vision_max"],
                            "vision_peak": ldr_def["vision_peak"],
                        })
                    else:
                        animal_entry.update({
                            "hp": grot_stats_data["hp"], "max_hp": grot_stats_data["hp"],
                            "atk": grot_stats_data["atk"], "def": grot_stats_data["def"],
                            "speed_cpm": grot_stats_data["speed_cpm"],
                            "vision_max": grot_stats_data["vision_max"],
                            "vision_peak": grot_stats_data["vision_peak"],
                        })
                else:
                    animal_entry.update({
                        "hp": adef["hp"], "max_hp": adef["hp"],
                    })
                self.animals.append(animal_entry)
                spawned = True

        if hasattr(self, 'sound') and self.sound and spawned:
            self.sound.play_animal()
        self.spawn_young_animals(player)

    def mature_animals(self):
        now = time.time()
        for a in self.animals:
            if a["type"] == "young_rabbit" and now - a.get("birth_time", now) >= 18 * 60:
                a["type"] = "rabbit"
                a["hp"] = ANIMAL_DEFS["rabbit"]["hp"]
                a["max_hp"] = ANIMAL_DEFS["rabbit"]["hp"]
            elif a["type"] == "young_squirrel" and now - a.get("birth_time", now) >= 18 * 60:
                a["type"] = "squirrel"
                a["hp"] = ANIMAL_DEFS["squirrel"]["hp"]
                a["max_hp"] = ANIMAL_DEFS["squirrel"]["hp"]
            elif a["type"] == "young_deer" and now - a.get("birth_time", now) >= 24 * 60:
                a["type"] = "deer"
                a["hp"] = ANIMAL_DEFS["deer"]["hp"]
                a["max_hp"] = ANIMAL_DEFS["deer"]["hp"]
            elif a["type"] == "young_antelope" and now - a.get("birth_time", now) >= 24 * 60:
                a["type"] = "antelope"
                a["hp"] = ANIMAL_DEFS["antelope"]["hp"]
                a["max_hp"] = ANIMAL_DEFS["antelope"]["hp"]

    def move_animals(self, player):
        now = time.time()
        to_remove = []
        for i, a in enumerate(self.animals):
            adef = ANIMAL_DEFS.get(a["type"], {})
            dt = now - a.get("last_move", now)
            dist_to_player = math.hypot(a["x"]-player.x, a["y"]-player.y)
            # When an animal is on-screen (near the player) update it very
            # frequently and move it in small ~0.1-tile fractions so it glides
            # smoothly instead of teleporting/"jumping" between renders.
            near_player = dist_to_player <= FOG_RADIUS
            step_thresh = 0.08 if near_player else 0.5
            if dt < step_thresh: continue
            a["last_move"] = now
            # Cap dt so a long modal screen (tutorial, menu, spear-throw lesson)
            # can't translate into a giant teleport "jump" when control returns —
            # e.g. the deer should not bolt across the map while you read a tutorial.
            dt = min(dt, 0.6)
            speed_cpm = a.get("speed_cpm", adef.get("speed_cpm", 10))
            real_speed = speed_cpm * dt / 30.0
            if near_player:
                real_speed = min(real_speed, 0.1)   # smooth fractional movement

            # Grots: aggressor behavior — approach player, hunt animals, flee at 50% HP in small groups
            if a["type"] in ("grot", "grot_leader"):
                nearby_grots = sum(1 for b in self.animals if b["type"] in ("grot", "grot_leader") and math.hypot(b["x"]-a["x"],b["y"]-a["y"]) <= 5)
                max_hp = a.get("max_hp", 5)
                # Lone grot below half HP: flee outright (no retaliation), with grace period.
                if nearby_grots <= 1 and a["hp"] <= max_hp * 0.5:
                    a["fleeing"] = True
                    if not a.get("flee_grace_until"):
                        a["flee_grace_until"] = now + 10.0
                # Small group (<= 3): also flee at half HP
                elif nearby_grots <= 3 and a["hp"] <= max_hp * 0.5:
                    a["fleeing"] = True
                # Grots may hunt nearby prey if it is closer than the player
                if not a.get("fleeing"):
                    prey = None
                    prey_dist = float('inf')
                    for b in self.animals:
                        if b is a or b.get("type") in ("grot", "grot_leader"):
                            continue
                        if b.get("hp", 1) <= 0:
                            continue
                        pd = math.hypot(b["x"]-a["x"], b["y"]-a["y"])
                        if pd <= 8.0 and pd < prey_dist:
                            prey = b
                            prey_dist = pd
                    if prey and (prey.get("type") in ("cat", "young_cat") or prey_dist < dist_to_player):
                        # Spook the prey
                        prey["fleeing"] = True
                        prey["_threat_pos"] = (a["x"], a["y"])
                        if prey_dist <= 1.2:
                            # Grot strikes prey using its atk stat (weapon damage per tick)
                            grot_atk = a.get("atk", 2)
                            prey["hp"] = prey.get("hp", 1) - grot_atk
                            if prey.get("hp", 0) <= 0:
                                prey_def = ANIMAL_DEFS.get(prey.get("type"), {})
                                carried = a.setdefault("_carried_loot", {})
                                for k, v in (prey_def.get("loot") or {}).items():
                                    carried[k] = carried.get(k, 0) + v
                                prey["hp"] = 0
                                try:
                                    idx_p = self.animals.index(prey)
                                    if idx_p not in to_remove:
                                        to_remove.append(idx_p)
                                except ValueError:
                                    pass
                            continue
                        dx = (prey["x"] - a["x"]) / prey_dist
                        dy = (prey["y"] - a["y"]) / prey_dist
                        a["x"] += dx * real_speed
                        a["y"] += dy * real_speed
                        continue
                # Grots approach player if within vision range
                vm = a.get("vision_max", adef.get("vision_max", 10))
                if dist_to_player < vm and not a.get("fleeing") and dist_to_player > 0.5:
                    # Move TOWARD player
                    dx = (player.x - a["x"]) / dist_to_player
                    dy = (player.y - a["y"]) / dist_to_player
                    a["x"] += dx * real_speed
                    a["y"] += dy * real_speed
                elif a.get("fleeing"):
                    if dist_to_player > FOG_RADIUS * 2:
                        to_remove.append(i); continue
                    if dist_to_player > 0.1:
                        dx = (a["x"]-player.x)/dist_to_player
                        dy = (a["y"]-player.y)/dist_to_player
                        a["x"] += dx * real_speed
                        a["y"] += dy * real_speed
                else:
                    a["x"] += random.uniform(-1,1) * real_speed * 0.1
                    a["y"] += random.uniform(-1,1) * real_speed * 0.1
                continue  # Skip the generic flee/wander logic below for grots
            # ---- Cat AI ----
            if a["type"] in ("cat", "young_cat"):
                is_young = a["type"] == "young_cat"
                # Cats flee grots on sight
                nearest_grot_cat = None; ng_dist = float('inf')
                for g in self.animals:
                    if g.get("type") not in ("grot","grot_leader") or g.get("hp",0)<=0: continue
                    gd = math.hypot(g["x"]-a["x"], g["y"]-a["y"])
                    if gd < ng_dist: ng_dist = gd; nearest_grot_cat = g
                if nearest_grot_cat and ng_dist <= max(12.0, float(nearest_grot_cat.get("vision_max", 8))):
                    a["fleeing"] = True
                    a["_threat_pos"] = (nearest_grot_cat["x"], nearest_grot_cat["y"])
                # Cats flee large herbivores (deer/antelope/moose) within 8 tiles
                nearest_big = None; nb_dist = float('inf')
                for h in self.animals:
                    if h.get("type") not in ("deer","antelope","moose","young_deer","young_antelope","young_moose") or h.get("hp",0)<=0: continue
                    hd = math.hypot(h["x"]-a["x"], h["y"]-a["y"])
                    if hd < nb_dist: nb_dist = hd; nearest_big = h
                if nearest_big and nb_dist < 8.0 and not a.get("_following_player"):
                    a["fleeing"] = True
                    a["_threat_pos"] = (nearest_big["x"], nearest_big["y"])
                # Cat following player: stay close — UNLESS tasty prey is near.
                if a.get("_following_player") and not a.get("fleeing"):
                    # A bonded adult cat that spots prey within 8 coords breaks
                    # off to hunt it (falls through to the hunt/kill block below).
                    if not is_young:
                        _prey_near = None; _pn_d = float('inf')
                        for _b in self.animals:
                            if _b is a or _b.get("type") not in ("rabbit","young_rabbit","squirrel","young_squirrel"): continue
                            if _b.get("hp",1) <= 0: continue
                            _bd = math.hypot(_b["x"]-a["x"], _b["y"]-a["y"])
                            if _bd < 8.0 and _bd < _pn_d: _pn_d = _bd; _prey_near = _b
                        if _prey_near is not None:
                            if not a.get("_hunting_prey"):
                                a["_hunting_prey"] = True
                                a["_announce_hunt"] = _prey_near.get("type","prey")
                            # do NOT continue: fall through so the cat chases/kills it
                            pass
                        else:
                            if a.get("_hunting_prey"):
                                a["_hunting_prey"] = False
                                a["_announce_return"] = True
                            a["_hunting_prey"] = False
                    if not a.get("_hunting_prey"):
                        # A disgruntled cat (loyalty ≤ -10) still follows, but keeps
                        # its distance (~5 tiles) instead of staying right at your heel.
                        follow_dist = 5.0 if a.get("loyalty", 0) <= -10 else 2.5
                        if dist_to_player > follow_dist and dist_to_player > 0.1:
                            dx = (player.x - a["x"]) / dist_to_player
                            dy = (player.y - a["y"]) / dist_to_player
                            a["x"] += dx * real_speed
                            a["y"] += dy * real_speed
                        elif dist_to_player < 1.0:  # don't crowd player
                            dx = (a["x"]-player.x)/dist_to_player if dist_to_player>0.1 else random.uniform(-1,1)
                            dy = (a["y"]-player.y)/dist_to_player if dist_to_player>0.1 else random.uniform(-1,1)
                            a["x"] += dx * real_speed * 0.5
                            a["y"] += dy * real_speed * 0.5
                        continue
                    # else: hunting prey — fall through to the hunt/kill block below
                if a.get("fleeing"):
                    if dist_to_player > FOG_RADIUS * 2 and ng_dist > FOG_RADIUS * 2:
                        to_remove.append(i); continue
                    tp = a.get("_threat_pos")
                    if tp:
                        td = math.hypot(a["x"]-tp[0], a["y"]-tp[1])
                        if td > 0.1:
                            a["x"] += (a["x"]-tp[0])/td * real_speed
                            a["y"] += (a["y"]-tp[1])/td * real_speed
                    else:
                        a["x"] += random.uniform(-1,1) * real_speed
                        a["y"] += random.uniform(-1,1) * real_speed
                    continue
                # Check catnip attraction (dropped or in world)
                catnip_target = None; catnip_dist = float('inf')
                for di in player.dropped_items:
                    if di["item"] == "catnip":
                        cd = math.hypot(di["x"]-a["x"], di["y"]-a["y"])
                        if cd < 30.0 and cd < catnip_dist:
                            catnip_dist = cd; catnip_target = di
                if catnip_target and catnip_dist > 0.5:
                    dx = (catnip_target["x"]-a["x"]) / catnip_dist
                    dy = (catnip_target["y"]-a["y"]) / catnip_dist
                    a["x"] += dx * real_speed; a["y"] += dy * real_speed
                    # On first arrival at the catnip, the cat gets a loyalty boost.
                    if catnip_dist <= 0.5:
                        if not a.get("_catnip_arrived"):
                            a["_catnip_arrived"] = now
                            a.setdefault("loyalty", 0); a["loyalty"] += 3
                        elif now - a["_catnip_arrived"] > GAME_HOUR * 3:
                            a.pop("_catnip_arrived", None)
                            a["fleeing"] = True  # wander off
                    continue
                # If following the player, check for tasty prey nearby and temporarily abandon to hunt
                if a.get("_following_player") and not is_young:
                    prey_scan = None; ps_d = float('inf')
                    for b in self.animals:
                        if b.get("type") not in ("rabbit","young_rabbit","squirrel","young_squirrel"): continue
                        if b.get("hp",1) <= 0: continue
                        pd = math.hypot(b["x"]-a["x"], b["y"]-a["y"])
                        if pd < 8.0 and pd < ps_d: ps_d = pd; prey_scan = b
                    if prey_scan:
                        if not a.get("_hunting_prey"):
                            a["_hunting_prey"] = True
                            a["_announce_hunt"] = prey_scan.get("type","prey")
                        # skip friendly-approach so the hunt block below runs
                    elif a.get("_hunting_prey"):
                        a["_hunting_prey"] = False
                        a["_announce_return"] = True
                # Wild (unbonded) cat: approach player out of curiosity, but lose interest if no meat
                if not is_young and not a.get("_following_player") and not a.get("_hunting_prey") and dist_to_player < 8.0:
                    if not a.get("_approach_start"):
                        a["_approach_start"] = now
                    if now - a["_approach_start"] > GAME_HOUR * 2:
                        # Lost interest — calmly walk away rather than vanishing.
                        a["_lost_interest"] = True
                        wx = random.uniform(-1, 1); wy = random.uniform(-1, 1)
                        # Bias the wander slightly away from the player so it
                        # visibly strolls off instead of popping out of existence.
                        if dist_to_player > 0.1:
                            wx += (a["x"]-player.x)/dist_to_player * 0.6
                            wy += (a["y"]-player.y)/dist_to_player * 0.6
                        a["x"] += wx * real_speed
                        a["y"] += wy * real_speed
                        # Only despawn once it has clearly walked well off-screen.
                        if dist_to_player > FOG_RADIUS * 2.5:
                            to_remove.append(i)
                        continue

                    if dist_to_player > 1.5:
                        dx = (player.x-a["x"])/dist_to_player
                        dy = (player.y-a["y"])/dist_to_player
                        a["x"] += dx * real_speed * 0.4
                        a["y"] += dy * real_speed * 0.4
                        continue
                elif a.get("_approach_start") and dist_to_player >= 8.0 and not a.get("_following_player"):
                    # Out of range, reset approach timer
                    a.pop("_approach_start", None)

                # Cat hunts rodents (if not young)
                if not is_young:
                    prey_cat = None; prey_cd = float('inf')
                    for b in self.animals:
                        if b is a or b.get("type") not in ("rabbit","young_rabbit","squirrel","young_squirrel"): continue
                        if b.get("hp",1)<=0: continue
                        pd = math.hypot(b["x"]-a["x"], b["y"]-a["y"])
                        if pd < 8.0 and pd < prey_cd: prey_cd = pd; prey_cat = b
                    if prey_cat:
                        prey_cat["fleeing"] = True
                        prey_cat["_threat_pos"] = (a["x"], a["y"])
                        if prey_cd <= 0.8:
                            # Cat strikes with its atk stat
                            prey_cat["hp"] = prey_cat.get("hp",1) - a.get("atk",2)
                            if prey_cat.get("hp",0) <= 0:
                                prey_cat["hp"] = 0
                                a["_last_hunt_kill"] = now
                                try:
                                    self.animals.index(prey_cat)
                                    to_remove.append(self.animals.index(prey_cat))
                                except (ValueError, Exception):
                                    pass
                        elif prey_cd > 0.1:
                            dx=(prey_cat["x"]-a["x"])/prey_cd; dy=(prey_cat["y"]-a["y"])/prey_cd
                            a["x"]+=dx*real_speed; a["y"]+=dy*real_speed
                        continue
                # Mating: two adult cats within 20x20 → spawn young_cat
                if not is_young and not a.get("_last_mated"):
                    for b in self.animals:
                        if b is a or b.get("type") != "cat" or b.get("hp",0)<=0: continue
                        if abs(b["x"]-a["x"])<=10 and abs(b["y"]-a["y"])<=10:
                            if not a.get("_last_mated") or now - a.get("_last_mated",0) > GAME_HOUR*6:
                                a["_last_mated"] = now
                                kit = {"type":"young_cat","x":a["x"]+random.uniform(-1,1),"y":a["y"]+random.uniform(-1,1),
                                       "hp":1,"max_hp":1,"speed_cpm":20,"last_move":now,"fleeing":False}
                                self.animals.append(kit)
                                break
                # Wander
                a["x"] += random.uniform(-1,1) * real_speed * 0.15
                a["y"] += random.uniform(-1,1) * real_speed * 0.15
                continue
            # ---- Non-grot animal (prey) AI ----
            # Find nearest grot threat; prey are afraid of grots too.
            nearest_grot = None
            nearest_grot_dist = float('inf')
            for g in self.animals:
                if g.get("type") not in ("grot", "grot_leader") or g.get("hp", 0) <= 0:
                    continue
                gd = math.hypot(g["x"]-a["x"], g["y"]-a["y"])
                if gd < nearest_grot_dist:
                    nearest_grot_dist = gd
                    nearest_grot = g
            if not a.get("fleeing"):
                vm = a.get("vision_max", adef.get("vision_max", 5))
                vp = a.get("vision_peak", adef.get("vision_peak", 3))
                vision = random.triangular(0, vm, vp)
                if dist_to_player < vision and dist_to_player > 0.1:
                    a["fleeing"] = True
                elif nearest_grot is not None and nearest_grot_dist < max(vm, 6.0):
                    a["fleeing"] = True
                    a["_threat_pos"] = (nearest_grot["x"], nearest_grot["y"])
            if a.get("fleeing"):
                # Flee from whichever threat is closer: player or known grot threat
                threat_x, threat_y = player.x, player.y
                threat_d = dist_to_player
                threat_is_grot = False
                tp = a.get("_threat_pos")
                if tp is not None:
                    td = math.hypot(a["x"]-tp[0], a["y"]-tp[1])
                    if td < threat_d:
                        threat_x, threat_y = tp
                        threat_d = td
                        threat_is_grot = True
                if nearest_grot is not None and nearest_grot_dist < threat_d:
                    threat_x, threat_y = nearest_grot["x"], nearest_grot["y"]
                    threat_d = nearest_grot_dist
                    threat_is_grot = True
                if threat_d > FOG_RADIUS * 2 and dist_to_player > FOG_RADIUS * 2:
                    to_remove.append(i); continue
                if threat_d > 0.1:
                    dx = (a["x"]-threat_x)/threat_d
                    dy = (a["y"]-threat_y)/threat_d
                    boost = 1.6 if threat_is_grot else 1.0
                    a["x"] += dx * real_speed * boost
                    a["y"] += dy * real_speed * boost
            else:
                a["x"] += random.uniform(-1,1) * real_speed * 0.1
                a["y"] += random.uniform(-1,1) * real_speed * 0.1
        for i in reversed(to_remove): self.animals.pop(i)

    def update_animal_survival(self):
        """Check for overpopulation and starvation in 3x3 grid cells.
        - If >3 animals in a 3x3 cell: 50% die per 30 game minutes
        - If avg cluster qty <10 in a 3x3 cell: 50% die per 30 game minutes
        """
        now = time.time()
        if not hasattr(self, 'last_survival_check'):
            self.last_survival_check = now
        if now - self.last_survival_check < 30.0: return
        self.last_survival_check = now

        # Calculate survival rate: 25% die per 30 game minutes
        # GAME_HOUR is real seconds for 1 game hour, so 30 game minutes = 0.5 * GAME_HOUR real seconds
        # We check every 30 real seconds, so cycles_per_30_min = 30 / (0.5 * GAME_HOUR) = 60 / GAME_HOUR
        # Survival rate per check = 0.75 ^ (1 / cycles_per_30_min) = 0.75 ^ (GAME_HOUR / 60)
        survival_rate = 0.75 ** (GAME_HOUR / 60.0)

        # Group rabbits and squirrels by 3x3 grid cells
        grid_cells = {}
        for animal in self.animals:
            if animal["type"] not in ("rabbit", "squirrel"):
                continue
            grid_x = int(animal["x"]) // ANIMAL_GRID_SIZE
            grid_y = int(animal["y"]) // ANIMAL_GRID_SIZE
            cell_key = (grid_x, grid_y)
            if cell_key not in grid_cells:
                grid_cells[cell_key] = []
            grid_cells[cell_key].append(animal)

        # Check survival conditions for each cell
        animals_to_remove = []
        for cell_key, animals_in_cell in grid_cells.items():
            grid_x, grid_y = cell_key
            cell_min_x = grid_x * ANIMAL_GRID_SIZE
            cell_min_y = grid_y * ANIMAL_GRID_SIZE
            cell_max_x = cell_min_x + ANIMAL_GRID_SIZE
            cell_max_y = cell_min_y + ANIMAL_GRID_SIZE

            # Count animals in this 3x3 cell
            animal_count = len(animals_in_cell)

            # Count clusters in this cell (excluding bee hives)
            clusters_in_cell = []
            for pos, cluster in self.clusters.items():
                cx, cy = pos
                if cell_min_x <= cx < cell_max_x and cell_min_y <= cy < cell_max_y:
                    if cluster.get("real_item") != "bee_hive" and cluster.get("qty", 0) > 0:
                        clusters_in_cell.append(cluster)

            avg_qty = sum(c.get("qty", 0) for c in clusters_in_cell) / len(clusters_in_cell) if clusters_in_cell else 0

            # Apply death mechanics
            overpopulated = animal_count > 5
            starving = avg_qty < 5

            if overpopulated or starving:
                for animal in animals_in_cell:
                    if random.random() > survival_rate:
                        animals_to_remove.append(animal)

        # Remove dead animals — drop meat/loot on the ground
        for animal in animals_to_remove:
            try:
                self.animals.remove(animal)
                loot = ANIMAL_DEFS.get(animal.get('type',''), {}).get('loot', {})
                meat_qty = loot.get('meat', 0) + loot.get('bone', 0) // 2
                if meat_qty > 0:
                    drop_x = int(round(animal['x'])); drop_y = int(round(animal['y']))
                    drop_pos = (drop_x, drop_y)
                    existing = self.clusters.get(drop_pos)
                    if existing and existing.get('real_item') in ('meat', 'raw_game'):
                        existing['qty'] = existing.get('qty', 0) + meat_qty
                    else:
                        self.clusters[drop_pos] = {
                            'name': 'Raw Game', 'real_item': 'meat', 'category': 'food',
                            'is_identified': True, 'inspection_attempts': 0,
                            'pos': [drop_x, drop_y], 'qty': meat_qty,
                            'meta': {'item': 'meat', 'regrows': False}
                        }
            except ValueError:
                pass

    def deplete_resources_by_animals(self):
        """Reduce nearby clusters based on animal pressure in each 3x3 cell."""
        now = time.time()
        if not hasattr(self, 'last_resource_depletion'):
            self.last_resource_depletion = now
        if now - self.last_resource_depletion < 30.0: return
        self.last_resource_depletion = now

        # Group animals by 3x3 grid cells
        grid_counts = {}
        for animal in self.animals:
            grid_x = int(animal["x"]) // ANIMAL_GRID_SIZE
            grid_y = int(animal["y"]) // ANIMAL_GRID_SIZE
            cell_key = (grid_x, grid_y)
            grid_counts[cell_key] = grid_counts.get(cell_key, 0) + 1

        for cell_key, animal_count in grid_counts.items():
            if animal_count < 3:
                continue
            grid_x, grid_y = cell_key
            cell_min_x = grid_x * ANIMAL_GRID_SIZE
            cell_min_y = grid_y * ANIMAL_GRID_SIZE
            cell_max_x = cell_min_x + ANIMAL_GRID_SIZE
            cell_max_y = cell_min_y + ANIMAL_GRID_SIZE

            cluster_positions = [pos for pos,c in self.clusters.items()
                                 if cell_min_x <= pos[0] < cell_max_x and cell_min_y <= pos[1] < cell_max_y
                                 and c.get("real_item") != "bee_hive" and c.get("qty", 0) > 0]
            if not cluster_positions:
                continue

            if animal_count == 3:
                qty_mult = 0.85
                remove_frac = 0.0
            elif animal_count == 4:
                qty_mult = 0.70
                remove_frac = 0.0
            elif animal_count == 5:
                qty_mult = 0.55
                remove_frac = 0.0
            elif animal_count == 6:
                qty_mult = 0.40
                remove_frac = 0.05
            else:
                qty_mult = 0.25
                remove_frac = 0.15

            if remove_frac > 0 and cluster_positions:
                random.shuffle(cluster_positions)
                remove_count = int(len(cluster_positions) * remove_frac)
                for pos in cluster_positions[:remove_count]:
                    self.depleted.add(pos)
                    del self.clusters[pos]
                cluster_positions = cluster_positions[remove_count:]

            for pos in list(cluster_positions):
                cluster = self.clusters.get(pos)
                if not cluster:
                    continue
                cluster["qty"] = max(0, int(cluster["qty"] * qty_mult))
                if cluster["qty"] <= 0:
                    self.depleted.add(pos)
                    del self.clusters[pos]

    def check_flood(self):
        """If majority of water clusters have qty > 35, destroy half of non-water clusters."""
        water_cls = [c for c in self.clusters.values() if c.get("real_item") == "water"]
        if not water_cls: return None
        over_35 = sum(1 for c in water_cls if c["qty"] > 35)
        if over_35 > len(water_cls) / 2:
            non_water = [k for k,c in list(self.clusters.items()) if c.get("real_item") != "water"]
            random.shuffle(non_water)
            kill = non_water[:len(non_water)//2]
            for k in kill:
                self.depleted.add(k); del self.clusters[k]
            if kill:
                return f"🌊 FLOOD! Water levels critical — {len(kill)} resource clusters swept away!"
        return None

    def check_overpopulation(self):
        """Overpopulation is handled by animal pressure in local 6x6 cells."""
        return None

    def apply_evaporation(self):
        """Reduce each water cluster qty by 35% (called every 30s without rain)."""
        for c in self.clusters.values():
            if c.get("real_item") == "water":
                c["qty"] = max(0, int(c["qty"] * 0.65))

# ==================== HELPERS ====================
def find_unknown_inv_key(player, target):
    target = target.lower().strip()
    for k in list(player.inventory.keys()):
        if not k.startswith("unknown_") or not isinstance(player.inventory[k], dict): continue
        cat = k[len("unknown_"):]
        display = UNKNOWN_DISPLAY_MAP.get(cat, f"unknown {cat}").lower()
        if target in display or target in cat or target.replace(" ","_") in k:
            return k
    return None

def roll_mystery_mushroom():
    return {
        "risk_pct": random.triangular(0.0, 100.0, 50.0),
        "damage":  int(round(random.triangular(10.0, 50.0, 25.0))),
        "health":  int(round(random.triangular(0.0, 25.0, 12.5))),
        "hunger":  int(round(random.triangular(0.0, 50.0, 25.0))),
        "thirst":  int(round(random.triangular(0.0, 25.0, 12.5))),
        "energy":  int(round(random.triangular(0.0, 50.0, 25.0))),
        "fatigue": int(round(random.triangular(0.0, 10.0, 5.0))),
    }


def resolve_animal_kill(player, world, target, msg):
    # Grots that caught prey drop the carried loot too
    try:
        if target.get("type") == "grot":
            carried = target.get("_carried_loot") or {}
            for k, v in carried.items():
                player.inventory[k] = player.inventory.get(k, 0) + v
                msg.append(f"➕ {v} {display_item_name(k)} (from slain grot's catch)")
    except Exception:
        pass
    hunt_type = target["type"]
    if hunt_type == "grot":
        loot_items = {}
        if player.hidden_xp < 40:
            if random.random() < 0.50: loot_items["meat"] = 2
            if random.random() < 0.50: loot_items["bone"] = 2
        elif player.hidden_xp < 100:
            if random.random() < 0.20: loot_items["grot_hide"] = 1
            if random.random() < 0.50: loot_items["meat"] = random.randint(2,3)
            if random.random() < 0.75: loot_items["bone"] = 2
        elif player.hidden_xp < 140:
            if random.random() < 0.35: loot_items["grot_hide"] = 1
            if random.random() < 0.65: loot_items["meat"] = random.randint(3,4)
            if random.random() < 0.75: loot_items["bone"] = random.randint(3,5)
            if random.random() < 0.15: loot_items["grot_tooth"] = 1
        else:
            if random.random() < 0.50: loot_items["grot_hide"] = 1
            if random.random() < 0.70: loot_items["meat"] = random.randint(4,6)
            if random.random() < 0.80: loot_items["bone"] = 5
            if random.random() < 0.30: loot_items["grot_tooth"] = 1
        for item, qty in loot_items.items():
            player.inventory[item] = player.inventory.get(item, 0) + qty
        loot_str = ", ".join(f"{q}x {k}" for k, q in loot_items.items()) if loot_items else "nothing"
    else:
        loot = ANIMAL_DEFS.get(hunt_type, {}).get("loot", {})
        for item, qty in loot.items():
            player.inventory[item] = player.inventory.get(item, 0) + qty
        loot_str = ", ".join(f"{q}x {k}" for k, q in loot.items()) or "no loot"
    # Animal kill creates a mini-cluster at the nearest empty spot
    try:
        ax, ay = int(target.get("x",0)), int(target.get("y",0))
        _kpos_done = False
        for _kr in range(0,4):
            for _kdx in range(-_kr,_kr+1):
                for _kdy in range(-_kr,_kr+1):
                    _kc=(ax+_kdx,ay+_kdy)
                    if _kc not in world.clusters and _kc not in world.depleted:
                        loot_item = list(ANIMAL_DEFS.get(target.get("type","")or"",{}).get("loot",{"meat":1}).keys())[0]
                        world.clusters[_kc]={"qty":2,"real_item":loot_item,"is_identified":True,"meta":{"regrows":False,"hazard":False,"hazard_key":None,"tool_req":"","locked":False,"is_ash":False},"display":f"🩸 {loot_item.replace('_',' ').title()}"}
                        _kpos_done=True; break
                if _kpos_done: break
            if _kpos_done: break
    except Exception:
        pass
    try:
        world.animals.remove(target)
    except ValueError:
        pass
    msg.append(f"💀 {hunt_type.replace('_',' ').title()} killed! +{loot_str}")
    player.total_hunts += 1
    if hunt_type == "salmon":
        player.fish_kills += 1
    elif hunt_type == "seal":
        player.seal_kills += 1
    elif hunt_type == "penguin":
        player.penguin_kills += 1
        if ANIMAL_DEFS.get("penguin", {}).get("panic"):
            for other in world.animals:
                if other["type"] == "penguin":
                    other["fleeing"] = True
    if hunt_type == "grot":
        player.grot_kills += 1
    player.hidden_xp += ANIMAL_XP.get(hunt_type, 0)


def animal_retaliation(player, world, target, msg):
    # Any non-fatal hit causes the prey to flee
    try:
        if target.get("hp", 0) > 0:
            target["fleeing"] = True
    except Exception:
        pass
    if target["hp"] <= 0 or target.get("atk", 0) <= 0:
        return
    # Start turn-based combat when an animal with attack can retaliate
    if not player.in_combat:
        # gather nearby hostile animals (within 5 tiles) including the target
        attackers = [a for a in world.animals if a.get("atk",0) > 0 and math.hypot(a["x"]-player.x, a["y"]-player.y) <= 5]
        if attackers:
            start_turn_based_combat(player, world, attackers, msg)
            return
    # If already in combat, fallback to immediate damage (rare path)
    dmg = int(round(target.get("atk", 0) * player.armor_damage_multiplier()))
    if dmg > 0:
        if player.wearing:
            player.armor_dur -= dmg
            if player.armor_dur <= 0:
                player.wearing = None
                player.armor_dur = 0
                msg.append("💥 Armor broke!")
        player.note_damage_cause(f"{target['type'].replace('_',' ').title()} attack")
        player.health = max(0, player.health - dmg)
        msg.append(f"⚔️ {target['type'].replace('_',' ').title()} fights back! -{dmg} HP")
    elif target.get("atk", 0) > 0:
        msg.append("🛡️ Armor deflects the counterattack!")


# ==================== SPEAR THROW MINIGAME ====================

def compute_spear_hit(cur_pos, anim_center, silhouette):
    """Return hit zone: 'head','body','graze','near_miss','miss'.
    cur_pos: float, left edge of the 3-char |_| cursor on the bar.
    anim_center: float, center column of the silhouette string on the bar.
    silhouette: string built from █▓▒░ block chars (each 1 visual col wide).
    """
    aim = cur_pos + 1.0           # the _ character = aim point
    sil_len = len(silhouette)
    sil_start = anim_center - sil_len / 2.0
    idx = aim - sil_start
    if idx < 0 or idx >= sil_len:
        return "miss"
    ch = silhouette[int(idx)]
    return {"█": "head", "▓": "body", "▒": "graze", "░": "near_miss"}.get(ch, "miss")


# ==================== TUTORIALS REGISTRY ====================
# Re-readable tutorial pages. Each entry is { title, build(player)->lines }.
# `_unlock_and_show_tutorial` is called by the game when a tutorial fires for
# the first time. `_show_tutorial` is called by the `tutorials` command to
# replay an already-unlocked tutorial on demand.

def _paginate_for_terminal(lines, reserve=6):
    """Split a long list of lines into terminal-sized pages.
    Tries to break at blank lines so sections don't get chopped in half.
    `reserve` is rows we keep for header/footer/prompt.
    """
    try:
        _cols, rows = os.get_terminal_size()
    except Exception:
        rows = 24
    page_h = max(8, int(rows) - int(reserve))
    pages = []
    cur = []
    for ln in lines:
        cur.append(ln)
        if len(cur) >= page_h:
            # Prefer to back off to the most recent blank line for a clean split.
            split_at = len(cur)
            for j in range(len(cur) - 1, max(-1, len(cur) - 8), -1):
                if cur[j] == "":
                    split_at = j
                    break
            if split_at <= 0:
                split_at = len(cur)
            pages.append(cur[:split_at])
            # Drop the trailing blank we split on so it doesn't start the next page
            cur = cur[split_at + 1:] if split_at < len(cur) and cur[split_at] == "" else cur[split_at:]
    if cur:
        pages.append(cur)
    if not pages:
        pages = [lines]
    return pages


def _print_tutorial_paginated(term, lines):
    """Render a tutorial across as many pages as the terminal height needs."""
    if term is None:
        return
    pages = _paginate_for_terminal(lines, reserve=6)
    total = len(pages)
    for i, pg in enumerate(pages, 1):
        footer = ["", "  \U0001f4dc Page " + str(i) + "/" + str(total) + "  \u2014  [Enter] continues"]
        try:
            term.print_page(pg + footer)
        except Exception:
            pass


def _build_spear_tutorial_lines(player):
    spear_key = getattr(player, "spear_type", None)
    SPEAR_BLURBS = {
        "spear":                   "\U0001f5e1\ufe0f  Spear            \u2014 your trusty starter; balanced for any prey.",
        "advanced_spear":          "\u2694\ufe0f  Advanced Spear   \u2014 tougher than the basic spear; hits harder too.",
        "ice_spear":               "\U0001f9ca  Ice Spear        \u2014 frosty bite, but SHATTERS after one throw!",
        "advanced_ice_spear":      "\u2744\ufe0f\u2694\ufe0f Adv. Ice Spear  \u2014 hardened ice; doesn't shatter; cursor a touch easier.",
        "throwing_spear":          "\U0001f3af  Throwing Spear   \u2014 made for distance; slow, easy-to-aim cursor.",
        "advanced_throwing_spear": "\U0001f3af\u2694\ufe0f Adv. Throwing   \u2014 even more accurate and far more durable.",
        "heavy_spear":             "\u2692\ufe0f  Heavy Spear      \u2014 packs a wallop, but cursor wobbles fast \u2014 tricky!",
        "advanced_heavy_spear":    "\u2692\ufe0f\u2694\ufe0f Adv. Heavy      \u2014 same crushing blow, far tougher build.",
    }
    cur_key  = spear_key if spear_key in SPEAR_BLURBS else None
    cur_icon = SPEAR_DEFS.get(spear_key, {}).get("icon", "\U0001f5e1\ufe0f")
    cur_name = (spear_key or "(none equipped)").replace("_", " ").title()
    lines = [
        "\u2554" + "\u2550" * 56 + "\u2557",
        "   \U0001f5e1\ufe0f  FIRST SPEAR THROW \u2014 TUTORIAL  \U0001f3af",
        "\u255a" + "\u2550" * 56 + "\u255d",
        "",
        "You just raised your spear to throw! Here's how it works:",
        "",
        "\u25b6 AIMING",
        "  A cursor |_| slides LEFT across the bar.",
        "  The animal's silhouette stands near the middle.",
        "  Line the _ up with the part you want to hit, then press [SPACE].",
        "  Press [ENTER] or [ESC] to cancel \u2014 your spear stays in hand.",
        "",
        "\u25b6 HIT ZONES (read the silhouette block characters)",
        "  \u2588  =  Head      \u2014 best hit, lots more damage!",
        "  \u2593  =  Body      \u2014 solid, reliable damage.",
        "  \u2592  =  Graze     \u2014 clipped them; partial damage.",
        "  \u2591  =  Near Miss \u2014 barely tagged them.",
        "  -  =  Miss      \u2014 your spear hits only air.",
        "",
        "\u25b6 CYCLES",
        "  When the cursor reaches the left edge, it wraps back to the right.",
        "  You get three full passes. After that, the animal escapes!",
        "",
        "\u25b6 DISTANCE MATTERS",
        "  The farther away the animal is, the FASTER the cursor whips across",
        "  the bar \u2014 and the harder it is to line up a clean hit.",
        "  Close the gap when you can; throws are friendlier up close.",
        "",
        "\u25b6 SIZE MATTERS, TOO",
        "  Small critters (rabbits, squirrels, salmon) show a TINY silhouette",
        "  \u2014 much harder to land a head hit on. The flip side: they're easier",
        "  to scare off, so once you do hit them they tend to flee.",
        "  Big game (deer, seal, antelope) is a fat target you can hit reliably,",
        "  BUT they shrug off the shock and escape less easily \u2014 expect a fight!",
        "",
        "\u25b6 SPEAR TYPES YOU MAY WIELD",
    ]
    for k, blurb in SPEAR_BLURBS.items():
        prefix = "  \u25b6 " if k == cur_key else "    "
        suffix = "   \u2190 you have this one!" if k == cur_key else ""
        lines.append(prefix + blurb + suffix)
    lines += [
        "",
        "\u25b6 YOU'RE THROWING NOW:",
        "  " + cur_icon + "  " + cur_name,
        "",
        "Tips:",
        "  \u2022 Ice spears break instantly on throw \u2014 use them wisely.",
        "  \u2022 Type 'poison spear' to coat your tip; the next throw hits twice as hard.",
        "  \u2022 Closer shots are easier to land than far ones.",
        "  \u2022 Big silhouette = easy to clip, hard to escape. Tiny = the opposite.",
        "",
        "Good luck, hunter. Aim true!",
        "",
        "\U0001f4dc Tip: type 'tutorials' any time to re-read this page.",
    ]
    return lines


def _build_grot_combat_tutorial_lines(player):
    return [
        "\u2554" + "\u2550" * 56 + "\u2557",
        "   \U0001f479  GROT COMBAT \u2014 TUTORIAL  \u2694\ufe0f",
        "\u255a" + "\u2550" * 56 + "\u255d",
        "",
        "A grot has spotted you! When a grot sees you, the world",
        "snaps into GRID MODE \u2014 a turn-based standoff.",
        "",
        "\u25b6 WHAT TO EXPECT",
        "  \u2022 Grots hit HARD. A clean blow takes a serious chunk of HP.",
        "  \u2022 They travel in packs \u2014 expect company.",
        "  \u2022 Grot leaders hit even harder. Come prepared!",
        "",
        "\u25b6 COME PREPARED",
        "  \u2022 Wear armor \u2014 every tier blunts more of their swing.",
        "  \u2022 Bring a spear with durability left, and a shield if you can.",
        "  \u2022 Coat your spear in poison for doubled damage on the next hits.",
        "  \u2022 Keep food, water, and a campfire ready for after the fight.",
        "",
        "\u25b6 IN GRID MODE",
        "  \u2022 Move, attack, throw, block \u2014 each costs action points.",
        "  \u2022 Trees are walkable but cost 1.3x energy; rocks cost 1.5x.",
        "  \u2022 Entities only move once your turn ends (energy runs out / pass).",
        "  \u2022 You can try to flee, but turning your back is risky.",
        "  \u2022 Active crafting PAUSES while you fight, and resumes after.",
        "",
        "Stay sharp. A surprised hunter is a hurt hunter.",
        "",
        "\U0001f4dc Tip: type 'tutorials' any time to re-read this page.",
    ]


def _build_rest_tutorial_lines(player):
    return [
        "\u2554" + "\u2550" * 56 + "\u2557",
        "   \U0001f634  RESTING \u2014 TUTORIAL  \U0001f6cc\ufe0f",
        "\u255a" + "\u2550" * 56 + "\u255d",
        "",
        "Your fatigue is dipping low. Time to think about rest!",
        "",
        "\u25b6 WHY REST?",
        "  \u2022 Low fatigue slows you and weakens what you can do.",
        "  \u2022 If fatigue hits 0, you collapse \u2014 not a great look.",
        "  \u2022 A good rest brings fatigue back up fast.",
        "",
        "\u25b6 HOW TO REST",
        "  \u2022 Build a campfire and add fire fuel so it keeps burning.",
        "  \u2022 Type 'rest' near the fire to settle in.",
        "  \u2022 While resting you CAN'T move, craft, gather, or eat.",
        "  \u2022 Any active crafting PAUSES until you get back up.",
        "",
        "\u25b6 BE CAREFUL",
        "  \u2022 Don't rest in the open with grots nearby \u2014 you're a sitting target.",
        "  \u2022 Watch the weather: storms and cold can still bite while you sleep.",
        "  \u2022 Keep food and water handy for when you wake.",
        "",
        "Sweet dreams, traveller.",
        "",
        "\U0001f4dc Tip: type 'tutorials' any time to re-read this page.",
    ]


def _build_weather_tutorial_lines(player):
    return [
        "\u2554" + "\u2550" * 56 + "\u2557",
        "   \u26c8\ufe0f  WEATHER HAZARDS \u2014 TUTORIAL  \U0001f327\ufe0f",
        "\u255a" + "\u2550" * 56 + "\u255d",
        "",
        "The skies are changing! Different weather brings different danger.",
        "",
        "\u25b6 LIGHT RAIN & LIGHT STORMS",
        "  A little damage if you're caught out \u2014 but enough to notice!",
        "  Annoying, not deadly. Still, keep an eye on your HP.",
        "",
        "\u25b6 MEDIUM & HEAVY STORMS",
        "  Lightning can strike \u2014 lots of damage if it tags you! Come prepared",
        "  with medium or heavy armor, and stay off open ground.",
        "",
        "\u25b6 TORNADOES",
        "  Big damage and they fling you around. Find shelter, don't fight.",
        "",
        "\u25b6 DROUGHT & FIRESTORMS",
        "  Drought dries up water and food. Firestorms set the forest ablaze \u2014",
        "  serious damage if you're in the trees. Stock water, head to safer biomes.",
        "",
        "\u25b6 BLIZZARDS & ARCTIC COLD",
        "  Cold whittles you down steadily. Without insulation it's a LOT of",
        "  damage over time \u2014 come prepared with warm armor and a fire.",
        "",
        "\u25b6 GENERAL ADVICE",
        "  \u2022 Better armor = less weather damage of every kind.",
        "  \u2022 Watch the weather banner at the top of the screen.",
        "  \u2022 Shelter, fire, and full bellies turn most storms into a nap.",
        "",
        "\U0001f4dc Tip: type 'tutorials' any time to re-read this page.",
    ]


def _build_first_spear_tutorial_lines(player):
    return [
        "\u2554" + "\u2550" * 56 + "\u2557",
        "   \U0001f634  RESTING \u2014 TUTORIAL  \U0001f6cc\ufe0f",
        "\u255a" + "\u2550" * 56 + "\u255d",
        "",
        "You crafted your first spear! Here's the quick rundown.",
        "",
        "\u25b6 SPEAR TYPES (you'll unlock more later)",
        "  \U0001f5e1\ufe0f Spear            \u2014 your trusty starter; balanced for any prey.",
        "  \u2694\ufe0f Advanced Spear   \u2014 tougher, harder hitting.",
        "  \U0001f9ca Ice Spear        \u2014 cold bite, but SHATTERS after one throw.",
        "  \U0001f3af Throwing Spear   \u2014 made for distance; easier aim.",
        "  \u2692\ufe0f Heavy Spear      \u2014 huge damage; wobbly cursor, tricky.",
        "  Advanced versions of each are sturdier and sharper.",
        "",
        "\u25b6 WEAPON TYPES \u2014 HOW TO USE",
        "  \u2022 'strike' \u2014 jab nearby prey or enemies up close.",
        "  \u2022 'throw'  \u2014 fling at distant targets (aim minigame).",
        "  Each use wears your spear's durability. When it hits 0, it breaks.",
        "",
        "\u25b6 POISON \u2014 A LITTLE GOES A LONG WAY",
        "  Craft poison and type 'poison spear' to coat your tip.",
        "  \u2022 One coat doubles damage for your next 4 strikes OR 1 throw.",
        "  \u2022 A poisoned hit can drop tough animals (and grots!) much faster.",
        "  \u2022 Watch out \u2014 some animals (like poisonous spiders) can poison",
        "    YOU back. That's a little damage at first, but enough to notice!",
        "",
        "\u25b6 TIPS",
        "  \u2022 Save ice spears for sure-thing throws \u2014 they break instantly.",
        "  \u2022 Carry a backup spear if you can.",
        "  \u2022 Closer shots are easier than far ones; head hits hurt the most.",
        "",
        "Go hunt something. Aim true!",
        "",
        "\U0001f4dc Tip: type 'tutorials' any time to re-read this page.",
    ]
def _build_hunt_tutorial_lines(player):
    return [
        "\u2554" + "\u2550" * 56 + "\u2557",
        "   \U0001f3f9  HUNT \u2014 TUTORIAL  \U0001f43e",
        "\u255a" + "\u2550" * 56 + "\u255d",
        "",
        "You just tried hunting! Here's how the hunt command works.",
        "",
        "\u25b6 BASIC USAGE",
        "  hunt <animal>           \u2014 strike the nearest one up close.",
        "  hunt <animal> throw     \u2014 throw your spear at it (aim minigame).",
        "  hunt <animal> grid      \u2014 enter grid mode for a tactical fight.",
        "  Examples: 'hunt rabbit', 'hunt seal throw', 'hunt deer grid'.",
        "",
        "\u25b6 WHAT YOU NEED",
        "  \u2022 A spear in your inventory with durability left.",
        "  \u2022 To be in the right biome \u2014 seals live in Arctic, not Forest!",
        "  \u2022 At least one of that animal nearby. Explore to find them.",
        "",
        "\u25b6 SIGHT & FLEEING",
        "  Animals can spot you BEFORE you act. If they do, they may bolt",
        "  before your throw even lands. Get closer if you can sneak in.",
        "",
        "\u25b6 STRIKE vs THROW vs GRID",
        "  \u2022 Strike  \u2014 best at point blank, low durability cost.",
        "  \u2022 Throw   \u2014 great at range, but uses more durability and",
        "    a miss can mean a lost or broken spear. Ice spears shatter!",
        "  \u2022 Grid    \u2014 turn-based, multi-target. Use it for packs",
        "    (like grots or a herd of deer) or anything dangerous.",
        "",
        "\u25b6 BIG TIPS",
        "  \u2022 Big animals are easy to hit but hard to bring down \u2014 expect a fight!",
        "  \u2022 Small critters are hard to hit but flee easily once tagged.",
        "  \u2022 'poison spear' coats your tip: next 4 strikes OR 1 throw hit twice as hard.",
        "  \u2022 Carry a backup spear and watch your durability bar.",
        "",
        "Happy hunting!",
        "",
        "\U0001f4dc Tip: type 'tutorials' any time to re-read this page.",
    ]

def _build_house_tutorial_lines(player):
    return [
        "\u2554" + "\u2550" * 56 + "\u2557",
        "   \U0001f3e0  HOUSE BASICS \u2014 TUTORIAL  \U0001f3e0",
        "\u255a" + "\u2550" * 56 + "\u255d",
        "",
        "You can enter your house and move around the interior.",
        "",
        "\u25b6 MOVEMENT",
        "  Use arrow keys to walk around the room.",
        "  The room is shown as a grid; your position is 🧍.",
        "",
        "\u25b6 FURNITURE",
        "  Type 'place <item>' to place furniture from inventory.",
        "  Type 'move' to reposition furniture with arrow keys, then Enter.",
        "  Type 'rotate' to rotate furniture under you.",
        "  Furniture cannot overlap or extend beyond the room.",
        "",
        "\u25b6 SPECIAL ITEMS",
        "  A couch lets you set up a gaming console.",
        "  Type 'game' to use the console if it is present.",
        "  A bed or couch lets you rest safely indoors.",
        "",
        "\u25b6 COMMANDS",
        "  help     — show house controls",
        "  inv      — show inventory",
        "  rest     — sleep/stop resting",
        "  quit     — leave the house",
        "",
        "\U0001f4dc Tip: type 'tutorials' any time to re-read this page.",
    ]

def _build_disease_tutorial_lines(player):
    lines = [
        "\u2554" + "\u2550" * 56 + "\u2557",
        "   \u2623\ufe0f  DISEASES \u2014 TUTORIAL  \ud83c\udfe5",
        "\u255a" + "\u2550" * 56 + "\u255d",
        "",
        "Dirty water and bad food can make you sick. Here's how diseases work.",
        "",
        "\u25b6 HOW YOU GET INFECTED",
        "  \u2022 Drinking dirty water or unfiltered water",
        "  \u2022 Eating raw meat, certain mushrooms, or spoiled berries",
        "  \u2022 Mystery mushrooms and moss can carry rare infections",
        "  \u2022 After day 5, a small daily chance of random infection",
        "",
        "\u25b6 DISEASE EFFECTS",
        "  Each disease ticks every day or night (listed in its description).",
        "  They drain health, hunger, thirst, or energy over time.",
        "  Some diseases get WORSE with repeated exposure (stack!).",
        "",
        "\u25b6 HOW TO CURE THEM",
        "  \u2022 moss_healing    \u2014 cures Cholera (90%), Salmonellosis (85%)",
        "  \u2022 filtered_water \u2014 cures Cholera (45%), Dysentery (75%)",
        "  \u2022 fresh_water    \u2014 cures Cholera (20%), Dysentery (50%)",
        "  \u2022 mystery_mushroom / moss_mystery \u2014 cures Toxoplasmosis",
        "  \u2022 Some diseases clear on their own after a few days",
        "",
        "\u25b6 PREVENTION",
        "  \u2022 Always drink filtered_water when you can",
        "  \u2022 Cook meat before eating (use a furnace)",
        "  \u2022 Avoid risky mushrooms until you're prepared",
        "  \u2022 Keep antidote tea on hand for emergencies",
        "",
        "\u25b6 DISEASE LIST",
    ]
    for did, d in DISEASES.items():
        cat = {"water":"water","food":"food","water_food":"water/food"}.get(d["cat"], d["cat"])
        effects = ", ".join(f"{k}{v:+.0f}" for k,v in d.get("effects",{}).items())
        days = ""
        if d.get("days"):
            dd = d["days"]
            days = f"  {dd} day(s)" if isinstance(dd, int) else f"  {dd[0]}-{dd[1]} days"
        lines.append(f"  {DISEASE_DISPLAY[did]} ({cat}){days} \u2014 {effects}")
    lines += [
        "",
        "\U0001f4dc Tip: type 'tutorials' any time to re-read this page.",
    ]
    return lines

TUTORIALS = {
    "spear_throw": {
        "title":  "\U0001f5e1\ufe0f First Spear Throw",
        "build":  _build_spear_tutorial_lines,
    },
    "first_spear": {
        "title":  "\U0001f5e1\ufe0f Your First Spear",
        "build":  _build_first_spear_tutorial_lines,
    },
    "house": {
        "title":  "\U0001f3e0 House Basics",
        "build":  _build_house_tutorial_lines,
    },
    "grot_combat": {
        "title":  "\U0001f479 Grot Combat",
        "build":  _build_grot_combat_tutorial_lines,
    },
    "rest_fatigue": {
        "title":  "\U0001f634 Resting",
        "build":  _build_rest_tutorial_lines,
    },
    "weather_hazard": {
        "title":  "\u26c8\ufe0f Weather Hazards",
        "build":  _build_weather_tutorial_lines,
    },
    "hunt": {
        "title":  "\U0001f3f9 Hunting",
        "build":  _build_hunt_tutorial_lines,
    },
    "disease": {
        "title":  "\u2623\ufe0f Diseases",
        "build":  _build_disease_tutorial_lines,
    },
}


def _unlock_and_show_tutorial(term, player, key):
    """First-time trigger: unlock the tutorial and display it (paginated).
    If already unlocked, do nothing (player can replay it via `tutorials`).
    """
    if not hasattr(player, "tutorials_unlocked") or player.tutorials_unlocked is None:
        player.tutorials_unlocked = []
    if key in player.tutorials_unlocked:
        return
    if key not in TUTORIALS:
        return
    player.tutorials_unlocked.append(key)
    if term is None:
        return
    prev_player = getattr(term, "pause_context_player", None)
    term.pause_context_player = player
    _print_tutorial_paginated(term, TUTORIALS[key]["build"](player))
    term.pause_context_player = prev_player


def _show_tutorial(term, player, key):
    """Replay an already-unlocked tutorial (used by the `tutorials` command)."""
    if term is None or key not in TUTORIALS:
        return
    _print_tutorial_paginated(term, TUTORIALS[key]["build"](player))


# Backward-compat wrapper so existing trigger call sites need no changes.
def _show_spear_tutorial_if_first(term, player, spear_key):
    _unlock_and_show_tutorial(term, player, "spear_throw")


# ==================== QUICK INTERACTIVE TUTORIAL ====================
# A guided, popup-driven walkthrough for brand-new players. Triggered as an
# optional step during new-game setup. State machine progresses on specific
# player actions (walk arrival, inspect, gather, explain, eat, craft).

def _qt_popup(term, *lines):
    if term is None:
        return
    body = ["\U0001f9d3 Quick Tutorial", "\u2500" * TERM_WIDTH, ""]
    body.extend(lines)
    body.append("")
    term.print_page(body)

def _qt_ensure_cluster(world, player, real_item, display, qty=6, locked=False, tool_req="", regrows=True, identified=False, hazard_key=None):
    """Ensure at least one tutorial-safe cluster exists within scan range.

    This is intentionally heavy-handed: the quick tutorial must never get stuck
    because a naturally spawned cluster was closer, already identified, depleted,
    or not the exact berry type the tutorial text expects.
    """
    desired_meta = {
        "regrows": regrows,
        "hazard": bool(hazard_key),
        "hazard_key": hazard_key,
        "tool_req": tool_req,
        "locked": locked,
        "is_ash": False,
    }

    def make_cluster(pos):
        world.clusters[pos] = {
            "qty": max(qty, 6 if real_item in BERRY_ITEMS else qty),
            "real_item": real_item,
            "is_identified": identified,
            "inspection_attempts": 0,
            "name": display,
            "pos": pos,
            "display": display,
            "category": "food" if real_item in BERRY_ITEMS else "material",
            "meta": dict(desired_meta),
        }
        world.depleted.discard(pos)
        return pos

    # If the player is already standing on the lesson resource, normalize that
    # tile and use it. This fixes the common stuck state: the prompt says the
    # player is at berries, but the next tutorial popup never appears.
    here = (int(player.x), int(player.y))
    current = world.clusters.get(here)
    if current and (current.get("real_item") == real_item or _qt_cluster_looks_like_berries(current)):
        return make_cluster(here)

    # Reuse and normalize the nearest matching in-range cluster.
    candidates = []
    for pos, c in world.clusters.items():
        if c.get("qty", 0) <= 0:
            continue
        item = c.get("real_item")
        if item == real_item or (real_item in BERRY_ITEMS and _qt_cluster_looks_like_berries(c)):
            d = math.hypot(pos[0] - player.x, pos[1] - player.y)
            if d <= FOG_RADIUS:
                candidates.append((d, pos))
    if candidates:
        candidates.sort(key=lambda t: t[0])
        return make_cluster(candidates[0][1])

    # Place a guaranteed cluster within fog radius. Prefer a nearby empty tile.
    for r in range(1, FOG_RADIUS + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if dx * dx + dy * dy > FOG_RADIUS * FOG_RADIUS:
                    continue
                pos = (int(player.x) + dx, int(player.y) + dy)
                if pos == here:
                    continue
                if pos in world.clusters:
                    continue
                return make_cluster(pos)

    # Last resort: overwrite the current tile rather than letting the tutorial die.
    return make_cluster(here)


def _qt_cluster_looks_like_berries(cl):
    if not cl or cl.get("qty", 0) <= 0:
        return False
    real_item = str(cl.get("real_item", "")).lower()
    category = str(cl.get("category", "")).lower()
    name = str(cl.get("name", "")).lower()
    display = str(cl.get("display", "")).lower()
    meta_item = str(cl.get("meta", {}).get("item", "")).lower()
    return (
        real_item in BERRY_ITEMS or real_item in ("berries", "berry", "unknown_berries") or
        meta_item in BERRY_ITEMS or meta_item in ("berries", "berry", "unknown_berries") or
        "berr" in real_item or "berr" in meta_item or "berr" in category or
        "berr" in name or "berr" in display
    )


def _qt_is_berry_cluster(cl):
    return _qt_cluster_looks_like_berries(cl)


def _qt_normalize_berry_tile(world, player, pos):
    cl = world.clusters.get(pos)
    if not _qt_cluster_looks_like_berries(cl):
        return False
    cl["real_item"] = "wild_berries"
    cl["qty"] = max(1, int(cl.get("qty", 1)))
    cl["name"] = "🫐 Berry Bush"
    cl["display"] = "🫐 Berry Bush"
    cl["category"] = "food"
    cl["is_identified"] = bool(cl.get("is_identified", False))
    cl["inspection_attempts"] = int(cl.get("inspection_attempts", 0) or 0)
    cl["pos"] = pos
    cl.setdefault("meta", {})
    cl["meta"].update({"item": "wild_berries", "type": "food", "regrows": True, "hazard": False, "hazard_key": None, "tool_req": "", "locked": False, "is_ash": False})
    world.depleted.discard(pos)
    player.qt_berries_pos = pos
    return True


def _qt_normalize_berry_here(world, player):
    """Make the player's current berry tile match the tutorial's expected item."""
    return _qt_normalize_berry_tile(world, player, (int(player.x), int(player.y)))


def _qt_valid_berry_target(world, target):
    if target is None:
        return False
    try:
        pos = tuple(target)
    except Exception:
        return False
    return _qt_cluster_looks_like_berries(world.clusters.get(pos))



def _qt_trigger_berries_if_here(term, player, world):
    """Immediately advance the berry lesson whenever the player is on berries.

    Do not require a matching auto-walk target, an arrival message, or another
    main-loop tick. If the berry lesson has just started and all conditions are
    already true, fire the next popup now.
    """
    if not getattr(player, "qt_active", False) or getattr(player, "qt_step", "") != "find_berries":
        return False
    cl = world.clusters.get((int(player.x), int(player.y)))
    if not _qt_is_berry_cluster(cl):
        return False
    _qt_normalize_berry_here(world, player)
    _qt_popup(term,
              "Great! Now, type \"inspect\".",
              f"You get up to {MAX_INSPECTIONS} tries — type it again if it fails.",
              "Tip: you can also buy a textbook (type: buy textbook) to make",
              "identifying easier — it's optional.")
    player.qt_step = "inspect_berries"
    player.qt_inspect_tries = 0
    player.auto_walk_target = None
    return True

def qt_init(term, player, world):
    """Begin the quick interactive tutorial. Called once at new-game start."""
    player.qt_active = True
    player.qt_step = "intro_shown"
    player.quest_clock_started_at = None
    player.qt_wait_until = time.time() + 10.0
    player.qt_inspect_tries = 0
    player.qt_wood_before = player.inventory.get("wood", 0)
    # Make sure the player can actually do this lesson.
    if player.inventory.get("axe", 0) <= 0 or player.axe_dur <= 0:
        player.inventory["axe"] = 1
        player.axe_dur = TOOL_DUR
    _qt_popup(term, "Hi! I'm going to give you a tutorial.")

def qt_tick(term, player, world):
    """Called every main-loop iteration. Handles timed transitions."""
    if not getattr(player, "qt_active", False):
        return
    if player.qt_step == "intro_shown" and time.time() >= getattr(player, "qt_wait_until", 0):
        player.qt_berries_pos = _qt_ensure_cluster(world, player, "wild_berries", "🫐 Berry Bush", qty=6)
        player.qt_step = "find_berries"
        if _qt_trigger_berries_if_here(term, player, world):
            return
        _qt_popup(term,
                  "Did you take a look around?",
                  "I'm going to help you walk to berries, inspect them,",
                  "and also craft a plank.",
                  "",
                  "Type: walk to berries")
    elif player.qt_step == "find_berries":
        _qt_trigger_berries_if_here(term, player, world)
    elif player.qt_step == "inspect_berries":
        cl = world.clusters.get((int(player.x), int(player.y)))
        if _qt_is_berry_cluster(cl) and cl.get("is_identified"):
            _qt_popup(term,
                      "Great job! These berries are already identified.",
                      "",
                      "Now, type: gather")
            player.qt_step = "gather_one"
    elif player.qt_step == "find_wood":
        cl = world.clusters.get((int(player.x), int(player.y)))
        if cl and cl.get("real_item") == "wood":
            qt_on_event(term, player, world, "arrived_walk")

def qt_force_inspect_outcome(player):
    """Returns True if the inspect attempt should be forced to SUCCEED (5th try),
    False if it must FAIL, or None if no override."""
    if not getattr(player, "qt_active", False):
        return None
    if player.qt_step != "inspect_berries":
        return None
    # Let tutorial identification use the normal chance. qt_on_event moves on
    # after either a success or 3 failed attempts.
    return None

def qt_on_event(term, player, world, event, **kw):
    """Advance the quick tutorial when game events fire. Safe no-op if inactive."""
    if not getattr(player, "qt_active", False):
        return
    step = player.qt_step

    if event == "arrived_walk":
        cl = world.clusters.get((int(player.x), int(player.y)))
        berry_target = getattr(player, "qt_berries_pos", None)
        at_berry_target = berry_target is not None and (int(player.x), int(player.y)) == tuple(berry_target)
        if step == "find_berries" and _qt_is_berry_cluster(cl):
            _qt_trigger_berries_if_here(term, player, world)
        elif step == "find_wood" and cl and cl.get("real_item") == "wood":
            player.qt_wood_before = player.inventory.get("wood", 0)
            _qt_popup(term, "Now, type: gather")
            player.qt_step = "gather_wood_one"

    elif event == "inspect_result" and step == "inspect_berries":
        player.qt_inspect_tries += 1
        if kw.get("success"):
            spent = INSPECT_COST * player.qt_inspect_tries
            _qt_popup(term,
                      "Tip: buy a textbook (type: buy textbook) — it makes",
                      "identifying easier next time. You don't have to.",
                      "",
                      f"Great job! Notice that your energy went down by {spent}.",
                      "",
                      "Now, type 'gather' once to gather it.")
            player.qt_step = "gather_one"
        else:
            if player.qt_inspect_tries >= MAX_INSPECTIONS:
                cl = world.clusters.get((int(player.x), int(player.y)))
                if cl and not cl.get("is_identified"):
                    cl["is_identified"] = True
                    cl["name"] = cl["real_item"].replace("_", " ").title()
                _qt_popup(term,
                          "Out of tries — I'll identify it for you this once.",
                          "Tip: buy a textbook (type: buy textbook) to make",
                          "identifying easier next time. You don't have to.",
                          "",
                          "Now, type: gather")
                player.qt_step = "gather_one"
            else:
                remaining = max(0, MAX_INSPECTIONS - player.qt_inspect_tries)
                _qt_popup(term,
                          f"That's okay! You still have {remaining} tries!",
                          "Notice that your energy went down by 5!",
                          "",
                          "Tip: you can buy a textbook (type: buy textbook)",
                          "to make identifying easier — it's optional.")

    elif event == "gather_done":
        item = kw.get("item")
        if step == "gather_one" and item in BERRY_ITEMS:
            _qt_popup(term,
                      "Great! Now, to collect the whole cluster,",
                      "type 'gather all'")
            player.qt_step = "gather_all"
        elif step == "gather_wood_one" and item == "wood":
            _qt_popup(term,
                      "Notice the difference in the durability of your axe.",
                      "This will go down as you gather.",
                      "",
                      "Now, gather 3 wood, or type 'gather' once more.")
            player.qt_step = "gather_wood_three"
        elif step == "gather_wood_three" and item == "wood":
            wood = player.inventory.get("wood", 0)
            base = getattr(player, "qt_wood_before", 0)
            if wood - base >= 3:
                _qt_popup(term, "Great! Now, 'craft plank'")
                player.qt_step = "craft_plank"

    elif event == "gather_all_done" and step == "gather_all":
        item = kw.get("item")
        if item in BERRY_ITEMS:
            if player.inventory.get("wild_berries", 0) <= 0 and player.inventory.get(item, 0) > 0:
                player.inventory["wild_berries"] = player.inventory.get("wild_berries", 0) + player.inventory.get(item, 0)
                player.inventory[item] = 0
            _qt_popup(term,
                      "Great job inspecting and collecting, explorer!",
                      "",
                      "Now, find out what it is.",
                      "Type: explain wild berries")
            player.qt_step = "explain_berry"

    elif event == "explain_done" and step == "explain_berry":
        target = str(kw.get("target", "")).lower()
        if "berr" in target:
            _qt_popup(term, "Eat it. Type: eat wild berries")
            player.qt_step = "eat_berry"

    elif event == "eat_done" and step == "eat_berry":
        item = str(kw.get("item", ""))
        if "berr" in item:
            _qt_ensure_cluster(world, player, "wood", "\U0001f332 Fallen Trees",
                               qty=8, locked=True, tool_req="axe",
                               regrows=False, identified=True)
            _qt_popup(term,
                      "Did you notice the change in energy, hunger, and thirst?",
                      "",
                      "Now, let's craft a plank.",
                      "Type: walk to wood")
            player.qt_step = "find_wood"

    elif event == "craft_done" and step == "craft_plank":
        if kw.get("item") == "plank":
            player.energy = player.max_energy
            player.hunger = 100.0
            player.thirst = 100.0
            player.fatigue = 100.0
            player.health = player.max_health
            _qt_popup(term,
                      "Great! I've restocked your energy, hunger,",
                      "thirst, and health.",
                      "",
                      "Feel free to start exploring! And good luck!")
            player.qt_active = False
            player.qt_step = "done"
            player.quest_clock_started_at = player_playtime(player)
            # Now show the standard tutorial pages, then start the 5s playing-time lore delay.
            try:
                run_tutorial(term)
            except Exception:
                pass
            schedule_lore_intro(player, delay=5.0)

# ==================== END QUICK INTERACTIVE TUTORIAL ====================


# ==================== MAJOR GOALS / LORE ====================

MAJOR_GOALS = [
    ("arctic",       "Reach the Arctic"),
    ("all_quests",   "Complete all quests"),
    ("all_achievs",  "Complete all achievements"),
    ("house",        "Build a house"),
    ("survive_50",   "Survive for 50 days"),
]

def _goal_done(key, player):
    if key == "arctic":      return bool(getattr(player, "arctic_visited", False))
    if key == "all_quests":
        if not player.quests: return False
        return all(v == "completed" for v in player.quests.values()) and len(player.quests) >= len(QUESTS)
    if key == "all_achievs": return len(player.earned_achievements) >= len(ACHIEVEMENTS)
    if key == "house":       return bool(getattr(player, "house_built", False))
    if key == "survive_50":  return player.days_survived >= 50
    return False

def _show_goals_screen(term, player, newly=None):
    if term is None: return
    lines = ["\U0001f3af MAJOR GOALS", "\u2500" * TERM_WIDTH, "",
             "There are several major goals in 9 Planets.", ""]
    for key, label in MAJOR_GOALS:
        done = _goal_done(key, player)
        box = "\u2705" if done else "\u2b1c"
        mark = "  \u2728 NEW!" if (newly and key in newly) else ""
        lines.append(f"  {box}  {label}{mark}")
    lines.append("")
    lines.append("Press Enter to continue.")
    term.print_page(lines)

def check_major_goals(term, player):
    now = time.time()
    cur_pt = player.total_playtime + max(0.0, now - player.session_start)
    if not getattr(player, "goals_completed_keys", None):
        player.goals_completed_keys = []
    if not getattr(player, "goals_intro_shown", False) and cur_pt >= 60:
        player.goals_intro_shown = True
        player.goals_completed_keys = [k for k, _ in MAJOR_GOALS if _goal_done(k, player)]
        _show_goals_screen(term, player)
        return
    if not getattr(player, "goals_intro_shown", False):
        return
    newly = []
    for key, _ in MAJOR_GOALS:
        if _goal_done(key, player) and key not in player.goals_completed_keys:
            newly.append(key)
            player.goals_completed_keys.append(key)
    if newly:
        _show_goals_screen(term, player, newly=newly)

def show_lore_intro(term, player):
    """One-time creation-myth lore popup shown right after the tutorial."""
    if getattr(player, "lore_intro_shown", False) or term is None:
        return
    player.lore_intro_shown = True
    page1 = ["\U0001f4d6 Lore", "\u2500" * TERM_WIDTH, "",
             "All the gods are so ancient, that by now,",
             "nobody venerates them.",
             "",
             "That's why lore is here \u2014 to help gain knowledge",
             "about the gods, so that you may venerate them.",
             "",
             "There are 3 ways to gain lore:",
             "  \u2022 Listen to stories from the old \"man\"",
             "  \u2022 Gain items with special flavor text",
             "  \u2022 Fight bosses and see what their dialogue reveals",
             "",
             "Press Enter to continue."]
    try: term.print_page(page1)
    except Exception: pass
    page2 = ["\U0001f4d6 Lore \u2014 The Creator", "\u2500" * TERM_WIDTH, "",
             "Where shall we start? Ah yes, the creator of the universe.",
             "",
             "Once, there was nothing but two primordial forces.",
             "One destructive, and one creative.",
             "",
             "Now, do not mistake the two forces for evil and good,",
             "as both destruction and creation are needed in a stable",
             "universe.",
             "",
             "Then, from the clash of the two forces, a shining golden",
             "egg appeared. It split in two, from it emerging the creator.",
             "",
             "He calmed the two forces, and thus created the universe.",
             "",
             "Press Enter to continue."]
    try: term.print_page(page2)
    except Exception: pass

# ==================== END MAJOR GOALS / LORE ====================





def run_spear_minigame(term, player, animal_type, dist, spear_key):
    """Wrapper: play throw/combat music for the duration of the aiming minigame,
    then restore the previous BGM. Delegates to _run_spear_minigame_impl."""
    _snd = getattr(player, "sound", None)
    _started_bgm = False
    try:
        if _snd and getattr(_snd, "enabled", False) and not _snd.in_combat_bgm:
            _snd.start_combat_bgm(); _started_bgm = True
    except Exception:
        _started_bgm = False
    try:
        return _run_spear_minigame_impl(term, player, animal_type, dist, spear_key)
    finally:
        if _started_bgm:
            try: _snd.stop_combat_bgm()
            except Exception: pass


def _run_spear_minigame_impl(term, player, animal_type, dist, spear_key):
    """Interactive spear-throw aiming minigame.
    Returns (hit_zone, cancelled):
        hit_zone : 'head','body','graze','near_miss','miss'
        cancelled: True if player pressed Enter/Esc without throwing.
    Controls: SPACE = throw, ENTER/ESC = cancel.
    """
    import select as _sel
    import sys as _sys

    BAR_W = 68   # width of the aiming bar in chars (block chars are 1-wide)
    CURSOR = "|_|"

    adata = SPEAR_MINIGAME_ANIMALS.get(animal_type) or SPEAR_MINIGAME_ANIMALS.get("deer")
    if adata is None:
        return "miss", False

    # Distance tier
    tier = "very_far"
    for lo, hi, t in adata["dist_tiers"]:
        if lo <= dist < hi:
            tier = t; break

    # Night penalty: silhouette one size tier smaller (harder to see)
    if getattr(player, "time_of_day", "day") == "night":
        _tier_order = ["close","medium","far","very_far"]
        _ti = _tier_order.index(tier) if tier in _tier_order else 0
        tier = _tier_order[min(_ti + 1, len(_tier_order) - 1)]

    silhouette   = adata["silhouettes"][tier]
    sil_len      = len(silhouette)
    cursor_mult  = SPEAR_DEFS.get(spear_key, {}).get("cursor_mult", 1.0)
    cursor_speed = adata["cursor_speed"][tier] * cursor_mult   # cells/sec, leftward
    anim_speed   = adata["anim_speed"][tier]
    movement     = adata["movement"]

    total_cycles = 3
    cycles_done  = 0

    # Cursor starts at right edge, travels left; wraps 3 times then animal escapes.
    cur_pos      = float(BAR_W - len(CURSOR))
    anim_center  = float(BAR_W // 2)
    anim_vel     = anim_speed * random.choice([-1, 1])

    last_hop    = time.time()
    hop_ivl     = 0.4 + random.random() * 0.4
    last_accel  = time.time()
    accel_ivl   = 0.25 + random.random() * 0.35
    last_frame  = time.time()

    icon  = ANIMAL_DEFS.get(animal_type, {}).get("icon", "?")
    aname = animal_type.replace("_", " ").title()
    tier_label = tier.replace("_", " ").title()

    HIT_LABELS = {
        "head":     ">>> HEAD HIT!   x1.5 damage!",
        "body":     ">>> Body hit.   x1.0 damage.",
        "graze":    ">>> Graze.      x0.5 damage.",
        "near_miss":">>> Near miss!  x0.25 damage.",
        "miss":     ">>> Complete miss. No damage.",
    }

    def render(flash=""):
        # Silhouette line: place silhouette string centred at anim_center
        sil_start = int(round(anim_center - sil_len / 2))
        sil_arr   = [" "] * BAR_W
        for i, ch in enumerate(silhouette):
            p = sil_start + i
            if 0 <= p < BAR_W:
                sil_arr[p] = ch
        sil_str = "".join(sil_arr)

        # Bar line: dashes with cursor |_| overlaid
        bar = ["-"] * BAR_W
        cp  = max(0, min(BAR_W - len(CURSOR), int(round(cur_pos))))
        for i, ch in enumerate(CURSOR):
            bar[cp + i] = ch
        bar_str = "".join(bar)

        spear_label = spear_key.replace("_", " ").title()
        lines = [
            vfit(f"  SPEAR THROW  {icon} {aname}  [{tier_label}]  Cycle {cycles_done+1}/{total_cycles}", TERM_WIDTH),
            vfit(f"  Dist: {dist:.1f} tiles  |  {spear_label}  (cursor speed x{cursor_mult:.1f})", TERM_WIDTH),
            "  " + "\u2500" * (TERM_WIDTH - 4),
            "",
            f"  {sil_str}",
            "",
            f"  {bar_str}",
            "",
            vfit("  [SPACE] Throw   [ENTER/ESC] Cancel (no throw)", TERM_WIDTH),
            "",
            vfit("  \u2588=Head x1.5  \u2593=Body x1.0  \u2592=Graze x0.5  \u2591=Near x0.25  -=Miss", TERM_WIDTH),
        ]
        if flash:
            lines += ["", f"  {flash}"]
        sys.stdout.write("\033[2J\033[H" + "\r\n".join(str(l) for l in lines))
        sys.stdout.flush()

    while True:
        now = time.time()
        dt  = min(now - last_frame, 0.15)
        last_frame = now

        # --- Cursor moves left, wraps at left edge ---
        cur_pos -= cursor_speed * dt
        if cur_pos < 0:
            cur_pos = float(BAR_W - len(CURSOR))
            cycles_done += 1
            if cycles_done >= total_cycles:
                render("\u23f0 Animal escaped! (3 cycles) - Miss.")
                time.sleep(1.2)
                return "miss", False

        # --- Animal movement ---
        margin = sil_len / 2.0
        if movement == "smooth":
            anim_center += anim_vel * dt
            if anim_center - margin < 1: anim_center = margin + 1; anim_vel = abs(anim_vel)
            elif anim_center + margin > BAR_W - 1: anim_center = BAR_W - 1 - margin; anim_vel = -abs(anim_vel)
        elif movement == "hopping":
            anim_center += anim_vel * dt
            if anim_center - margin < 1: anim_center = margin + 1; anim_vel = abs(anim_vel)
            elif anim_center + margin > BAR_W - 1: anim_center = BAR_W - 1 - margin; anim_vel = -abs(anim_vel)
            if now - last_hop > hop_ivl:
                hop = random.choice([-5, -4, 4, 5])
                anim_center = max(margin + 1, min(BAR_W - 1 - margin, anim_center + hop))
                anim_vel = random.choice([-1, 1]) * anim_speed * (0.6 + random.random() * 0.8)
                last_hop = now; hop_ivl = 0.3 + random.random() * 0.5
        elif movement == "erratic":
            anim_center += anim_vel * dt
            if anim_center - margin < 1: anim_center = margin + 1; anim_vel = abs(anim_vel)
            elif anim_center + margin > BAR_W - 1: anim_center = BAR_W - 1 - margin; anim_vel = -abs(anim_vel)
            if now - last_accel > accel_ivl:
                anim_vel = random.choice([-1, 1]) * anim_speed * (0.4 + random.random() * 1.2)
                last_accel = now; accel_ivl = 0.2 + random.random() * 0.3

        render()

        # Windows fallback: use msvcrt.kbhit() instead of select()
        if _sys.platform == "win32":
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                # msvcrt.getch() returns bytes on Windows
                if isinstance(ch, bytes):
                    ch = ch.decode('utf-8', errors='ignore')
                if ch == " ":
                    zone = compute_spear_hit(cur_pos, anim_center, silhouette)
                    render(HIT_LABELS.get(zone, ""))
                    time.sleep(1.3)
                    return zone, False
                if ch in ("\r", "\n", "\x1b", "q"):
                    render("Cancelled. Spear not thrown.")
                    time.sleep(0.8)
                    return "miss", True
        else:
            # Unix/Linux: use select()
            rlist, _, _ = _sel.select([sys.stdin], [], [], 0.05)
            if not rlist:
                continue
            ch = sys.stdin.read(1)
            if ch == " ":
                zone = compute_spear_hit(cur_pos, anim_center, silhouette)
                render(HIT_LABELS.get(zone, ""))
                time.sleep(1.3)
                return zone, False
            if ch in ("\r", "\n", "\x1b", "q"):
                render("Cancelled. Spear not thrown.")
                time.sleep(0.8)
                return "miss", True


CAT_SITTING_TEMPLATES = [
    "The cat is sitting on your {item}.",
    "The cat has claimed your {item} as its throne.",
    "The cat is kneading your {item} with great authority.",
    "The cat is staring intensely at your {item}.",
    "The cat is grooming itself on top of your {item}.",
]

# ==================== HOUSING SYSTEM ====================

def _house_find_at(world, px, py):
    """Return the house dict whose footprint covers (px,py), or None."""
    for h in world.houses:
        fp = HOUSE_DEFS[h["type"]]["footprint"]
        hx, hy = h["x"], h["y"]
        if hx <= px < hx + fp and hy <= py < hy + fp:
            return h
    return None


def _house_find_nearby(world, px, py, radius=2):
    """Return house within radius tiles, or None."""
    for h in world.houses:
        fp = HOUSE_DEFS[h["type"]]["footprint"]
        cx = h["x"] + fp / 2; cy = h["y"] + fp / 2
        if math.hypot(cx - px, cy - py) <= radius + fp / 2:
            return h
    return None


def _house_protection_pct(house):
    """Compute (damage_frac, fire_frac) remaining after all protections.
    damage_frac: fraction of damage the house actually takes (1.0 = no protection).
    fire_frac: same but for fire damage."""
    dmg_frac = 1.0; fire_frac = 1.0
    for fu in house.get("furniture", []):
        fdef = FURNITURE_DEFS.get(fu["type"], {})
        if fdef.get("prot_type") == "protection":
            r = fdef.get("prot_reduction", 0.0)
            fr = fdef.get("fire_reduction", 0.0)
            dmg_frac *= (1.0 - r)
            fire_frac *= (1.0 - fr)
    return max(0.0, dmg_frac), max(0.0, fire_frac)


def _house_take_damage(house, raw_dmg, is_fire=False):
    """Apply raw_dmg to house, respecting protection. Returns actual damage dealt."""
    dmg_frac, fire_frac = _house_protection_pct(house)
    frac = fire_frac if is_fire else dmg_frac
    actual = max(0, int(round(raw_dmg * frac)))
    house["hp"] = max(0, house.get("hp", 0) - actual)
    return actual


def _house_turret_tick(house, world, player, msg, now):
    """Fire autofire cannons/ballistas at nearby animals. Throttled to once per 3s per turret."""
    hx, hy = house["x"], house["y"]
    house_cx = hx + HOUSE_DEFS[house["type"]]["footprint"] / 2
    house_cy = hy + HOUSE_DEFS[house["type"]]["footprint"] / 2
    for fu in house.get("furniture", []):
        fdef = FURNITURE_DEFS.get(fu["type"], {})
        if fdef.get("prot_type") != "turret": continue
        if not fu.get("autofire", True): continue
        if fu.get("ammo_qty", 0) <= 0: continue
        if now - fu.get("_last_fire", 0) < 3.0: continue
        turret_range = fdef["range"]
        targets = [a for a in world.animals if a.get("hp", 0) > 0 and
                   math.hypot(a["x"] - house_cx, a["y"] - house_cy) <= turret_range]
        if not targets: continue
        target = min(targets, key=lambda a: math.hypot(a["x"]-house_cx, a["y"]-house_cy))
        dist = math.hypot(target["x"]-house_cx, target["y"]-house_cy)
        miss_chance = min(0.95, fdef["miss_per_tile"] * dist)
        fu["_last_fire"] = now
        fu["ammo_qty"] -= 1
        if random.random() < miss_chance:
            msg.append(f"💣 {fu['type'].replace('_',' ').title()} fired — missed!")
        else:
            ammo_mult = AMMO_DMG_MULT.get(fu.get("ammo_type","cannonball"), 1.0)
            base_dmg = 20 if "cannon" in fu["type"] else 10
            dmg = int(base_dmg * ammo_mult)
            target["hp"] -= dmg
            _flash_hit(target.get("type",""))
            aname = target["type"].replace("_"," ").title()
            msg.append(f"💣 {fu['type'].replace('_',' ').title()} hit {aname}! -{dmg} HP")
            # Flee radius
            flee_r = fdef["flee_radius"]
            for a in world.animals:
                if math.hypot(a["x"]-house_cx, a["y"]-house_cy) <= flee_r:
                    a["fleeing"] = True
                    a["_threat_pos"] = (house_cx, house_cy)
            # Attract hostiles in radius
            attract_r = fdef["attract_radius"]
            for a in world.animals:
                if a.get("atk",0) > 0 and math.hypot(a["x"]-house_cx, a["y"]-house_cy) <= attract_r:
                    a["fleeing"] = False
                    a["_target"] = (house_cx, house_cy)
        if target.get("hp",0) <= 0:
            target["hp"] = 0


def _update_houses(world, player, weather, msg, now):
    """Called each world tick: turret fire, grot attacks, fire damage."""
    for h in world.houses:
        if h.get("hp",0) <= 0: continue
        _house_turret_tick(h, world, player, msg, now)
        # Grot attacks on house when player is inside
        hdef = HOUSE_DEFS[h["type"]]
        if player.inside_house_id == h["id"]:
            fp = hdef["footprint"]
            hx, hy = h["x"], h["y"]
            hcx = hx + fp/2; hcy = hy + fp/2
            for a in world.animals:
                if a.get("type") not in ("grot","grot_leader") or a.get("hp",0)<=0: continue
                dist_to_house = math.hypot(a["x"]-hcx, a["y"]-hcy)
                # Dugout camouflage: grots need to be within frac*vision
                if hdef["camouflage"]:
                    vision = ANIMAL_DEFS.get(a.get("type","grot"),{}).get("vision_max",8)
                    if dist_to_house > vision * hdef["camouflage_frac"]:
                        continue
                if dist_to_house > fp + 1: continue
                # Grot attacks house using grot tooth (tracked as _tooth_dur)
                if not a.get("_tooth_dur"):
                    a["_tooth_dur"] = random.randint(3,8)
                if now - a.get("_last_house_atk",0) < 2.0: continue
                a["_last_house_atk"] = now
                raw_dmg = a.get("atk", 2)
                actual = _house_take_damage(h, raw_dmg)
                a["_tooth_dur"] -= 1
                msg.append(f"💥 Grot bashes your {h['type']}! -{actual} HP ({h['hp']} left)")
                if a["_tooth_dur"] <= 0:
                    a["fleeing"] = True
                    msg.append("🦷 Grot's tooth broke! It fled.")
                if h["hp"] <= 0:
                    msg.append(f"💥 YOUR {h['type'].upper()} WAS DESTROYED!")
                    if player.inside_house_id == h["id"]:
                        player.inside_house_id = None
    # Fire damage to houses
    if getattr(weather, "firestorm_active", False):
        for h in world.houses:
            if h.get("_fire_dmg_tick",0) == 0 or now - h["_fire_dmg_tick"] >= 60.0:
                h["_fire_dmg_tick"] = now
                raw_fire = max(200, h.get("max_hp",1)//2)
                actual = _house_take_damage(h, raw_fire, is_fire=True)
                if actual > 0:
                    msg.append(f"🔥 Fire damages your {h['type']}! -{actual} HP ({h.get('hp',0)} left)")


def _render_house_interior(house, player):
    """Return list of strings to display as the house interior grid."""
    hdef = HOUSE_DEFS[house["type"]]
    extra = max(0, (TERM_WIDTH - 80) // 8)
    cols = hdef["interior_cols"] + extra
    rows = hdef["interior_rows"] + max(0, extra // 2)
    # Build grid
    grid = [[HOUSE_EMPTY] * cols for _ in range(rows)]
    # Place furniture
    for fu in house.get("furniture", []):
        fdef = FURNITURE_DEFS.get(fu["type"], {})
        emoji = fdef.get("emoji", "?")
        fw = fu.get("w", fdef.get("w",1)); fh = fu.get("h", fdef.get("h",1))
        if fu.get("rotation",0) % 2 == 1:
            fw, fh = fh, fw  # rotate 90°
        ix, iy = fu.get("ix",0), fu.get("iy",0)
        for dy in range(fh):
            for dx in range(fw):
                nx, ny = ix+dx, iy+dy
                if 0<=nx<cols and 0<=ny<rows:
                    grid[ny][nx] = emoji
    # Place player
    px, py = player.house_pos
    px = max(0, min(px, cols-1)); py = max(0, min(py, rows-1))
    grid[py][px] = "🧍"
    # Render
    hname = house["type"].replace("_"," ").title()
    hp_str = f"HP {house.get('hp','?')}/{house.get('max_hp','?')}"
    dmg_frac, _ = _house_protection_pct(house)
    prot_str = f"Prot {int((1-dmg_frac)*100)}%"
    lines = [
        vfit(f"  🏠 {hname}  {hp_str}  {prot_str}  —  [arrows] move  [P]lace  [R]otate  [M]ove item  [Q/L]eave  [?]help", TERM_WIDTH),
        "─" * TERM_WIDTH,
    ]
    for row in grid:
        lines.append("  " + "".join(row))
    lines.append("─" * TERM_WIDTH)
    return lines, cols, rows


def enter_house_mode(term, player, world, house, weather, msg_out):
    """Run the house interior mode loop. Returns when player leaves."""
    msgs = []
    def add_msg(m):
        msgs.append(m); msg_out.append(m)

    # Normalise player position to interior
    hdef = HOUSE_DEFS[house["type"]]
    extra = max(0, (TERM_WIDTH - 80) // 8)
    cols = hdef["interior_cols"] + extra
    rows = hdef["interior_rows"] + max(0, extra // 2)
    max_col = cols - 1
    max_row = rows - 1
    player.house_pos = [max_col // 2, max_row // 2]

    def do_render(hint=""):
        lines, _, _ = _render_house_interior(house, player)
        if msgs:
            lines.append("  " + vtrunc("  ".join(msgs[-3:]), TERM_WIDTH-4))
        if hint:
            lines.append("  " + vfit(hint, TERM_WIDTH-4))
        if cmd_buf:
            lines.append("  " + vfit(f"> {cmd_buf}", TERM_WIDTH-4))
        else:
            lines.append("  " + vfit("[arrow keys] move around the room, or type a command and press Enter.", TERM_WIDTH-4))
        sys.stdout.write("\033[2J\033[H" + "\r\n".join(lines))
        sys.stdout.flush()

    def furniture_at(ix, iy):
        for fu in house.get("furniture",[]):
            fdef = FURNITURE_DEFS.get(fu["type"],{})
            fw = fu.get("w",fdef.get("w",1)); fh = fu.get("h",fdef.get("h",1))
            if fu.get("rotation",0)%2==1: fw,fh=fh,fw
            if fu.get("ix",0)<=ix<fu.get("ix",0)+fw and fu.get("iy",0)<=iy<fu.get("iy",0)+fh:
                return fu
        return None

    def furniture_cells(fu):
        fdef = FURNITURE_DEFS.get(fu["type"], {})
        fw = fu.get("w", fdef.get("w", 1)); fh = fu.get("h", fdef.get("h", 1))
        if fu.get("rotation",0) % 2 == 1:
            fw, fh = fh, fw
        return {(fu.get("ix",0) + dx, fu.get("iy",0) + dy) for dy in range(fh) for dx in range(fw)}

    def clamp_furniture_position(fu):
        fdef = FURNITURE_DEFS.get(fu["type"], {})
        fw = fu.get("w", fdef.get("w", 1)); fh = fu.get("h", fdef.get("h", 1))
        if fu.get("rotation", 0) % 2 == 1:
            fw, fh = fh, fw
        fu["ix"] = max(0, min(fu["ix"], cols - fw))
        fu["iy"] = max(0, min(fu["iy"], rows - fh))

    def furniture_overlaps(ix, iy, w=None, h=None, ignore=None, rotation=0):
        if ignore is not None and (w is None or h is None):
            fdef = FURNITURE_DEFS.get(ignore["type"], {})
            w = ignore.get("w", fdef.get("w", 1))
            h = ignore.get("h", fdef.get("h", 1))
            if rotation is None:
                rotation = ignore.get("rotation", 0)
            if rotation % 2 == 1:
                w, h = h, w
        if w is None or h is None:
            return True
        if ix < 0 or iy < 0 or ix + w > cols or iy + h > rows:
            return True
        new_cells = {(ix + dx, iy + dy) for dy in range(h) for dx in range(w)}
        for fu in house.get("furniture", []):
            if fu is ignore:
                continue
            if furniture_cells(fu) & new_cells:
                return True
        return False

    def house_has_console():
        return any(fu["type"] == "gaming_console" for fu in house.get("furniture", []))

    def house_console():
        if not house_has_console():
            add_msg("❌ No gaming console is set up in this house.")
            return
        add_msg("🎮 You turn on the gaming console.")

        def _practice_animal_pool(biome):
            forest_prey = ["rabbit", "young_rabbit", "squirrel", "young_squirrel", "deer", "young_deer", "antelope", "young_antelope"]
            arctic_prey = ["penguin", "seal", "salmon"]
            prey = forest_prey + (arctic_prey if biome == "Arctic" else [])
            return {
                "prey": prey,
                "monsters": ["grot", "grot_leader"],
            }

        def _build_practice_target(atype, practice_player, mode, practice_biome):
            adef = ANIMAL_DEFS.get(atype, {})
            icon = adef.get("icon") or ("👹" if atype == "grot" else "👑" if atype == "grot_leader" else "❓")
            hp = max(1, int(adef.get("hp", 4)))
            atk = 2 if mode == "combat" and atype in ("grot", "grot_leader") else max(0, int(adef.get("atk", 0)))
            angle = random.uniform(0.0, 2.0 * math.pi)
            dist = random.uniform(3.0, 8.5)
            x = practice_player.x + math.cos(angle) * dist
            y = practice_player.y + math.sin(angle) * dist
            return {
                "type": atype,
                "icon": icon,
                "x": round(x, 1),
                "y": round(y, 1),
                "hp": hp,
                "max_hp": hp,
                "atk": atk,
                "def": max(0, int(adef.get("def", 0))),
                "speed_cpm": int(adef.get("speed_cpm", 15)),
                "vision_peak": adef.get("vision_peak", 8),
                "vision_max": adef.get("vision_max", 8),
                "fleeing": False,
                "_practice": True,
                "_practice_biome": practice_biome,
            }

        def _generate_practice_targets(practice_player, mode):
            practice_biome = random.choice(["Forest", "Arctic"])
            pool = _practice_animal_pool(practice_biome)
            if mode == "combat":
                selected = [random.choice(pool["monsters"])]
                if random.random() < 0.5:
                    selected.append(random.choice(pool["monsters"]))
                selected.extend(random.sample(pool["prey"], k=min(len(pool["prey"]), random.randint(2, 3))))
            else:
                selected = random.sample(pool["prey"], k=min(len(pool["prey"]), random.randint(2, 4)))
            targets = []
            for atype in selected:
                targets.append(_build_practice_target(atype, practice_player, mode, practice_biome))
            return targets, practice_biome

        def run_practice_grid_mode(target_filter, empty_msg, mode):
            import copy
            orig_player_sound = getattr(player, "sound", None)
            orig_world_sound = getattr(world, "sound", None)
            try:
                if hasattr(player, "sound"):
                    player.sound = None
                if hasattr(world, "sound"):
                    world.sound = None
                practice_player = copy.deepcopy(player)
                practice_world = copy.deepcopy(world)
            finally:
                if hasattr(player, "sound"):
                    player.sound = orig_player_sound
                if hasattr(world, "sound"):
                    world.sound = orig_world_sound

            practice_targets, practice_biome = _generate_practice_targets(practice_player, mode)
            if not practice_targets:
                add_msg(empty_msg)
                return
            practice_world.biome = practice_biome
            practice_world.animals = practice_targets
            targets = target_filter(practice_targets)
            if not targets:
                targets = practice_targets
            add_msg(f"🎮 Fictional practice scenario generated ({practice_biome} rules): {len(targets)} target(s).")
            run_grid_mode(term, practice_player, practice_world, targets, msgs)
            add_msg("🎮 Practice session ended. No meat, no permanent harm.")

        while True:
            term.show_menu([
                "🎮 GAMING CONSOLE",
                "─" * TERM_WIDTH,
                "  1) Grid combat practice",
                "  2) Spear throw practice",
                "  3) Hunting practice (grid mode)",
                "",
                "  Press number to choose, or Enter/Esc to exit."
            ])
            ch = term.get_key_no_flush(0.5)
            if ch in ('\r', '\n', 'ESC'):
                break
            if ch is None:
                continue
            if not ch.isdigit():
                continue
            if ch == '1':
                run_practice_grid_mode(
                    lambda nearby: [a for a in nearby if a.get("atk", 0) > 0] or nearby,
                    "❌ No practice targets could be generated for grid practice.",
                    "combat"
                )
                continue
            if ch == '2':
                active_spear = None
                for sp in ["advanced_ice_spear","ice_spear","advanced_heavy_spear","heavy_spear","advanced_throwing_spear","throwing_spear","advanced_spear","spear"]:
                    if player.inventory.get(sp, 0) > 0:
                        active_spear = sp
                        break
                if not active_spear:
                    add_msg("❌ Need a spear to practice throw! Craft one first.")
                    continue

                import copy
                orig_player_sound = getattr(player, "sound", None)
                orig_world_sound = getattr(world, "sound", None)
                try:
                    if hasattr(player, "sound"):
                        player.sound = None
                    if hasattr(world, "sound"):
                        world.sound = None
                    practice_player = copy.deepcopy(player)
                    practice_world = copy.deepcopy(world)
                finally:
                    if hasattr(player, "sound"):
                        player.sound = orig_player_sound
                    if hasattr(world, "sound"):
                        world.sound = orig_world_sound

                if practice_player.spear_type != active_spear or practice_player.spear_dur <= 0:
                    practice_player.spear_type = active_spear
                    practice_player.spear_dur = SPEAR_DEFS[active_spear]["dur"]
                practice_targets, practice_biome = _generate_practice_targets(practice_player, "throw")
                if not practice_targets:
                    add_msg("❌ No practice targets could be generated for spear practice.")
                    continue
                practice_world.biome = practice_biome
                practice_world.animals = practice_targets
                target = min(practice_targets, key=lambda a: math.hypot(a["x"]-practice_player.x, a["y"]-practice_player.y))
                dist = math.hypot(target["x"]-practice_player.x, target["y"]-practice_player.y)
                add_msg(f"🎮 Fictional practice scenario generated ({practice_biome} rules): {len(practice_targets)} target(s).")
                snd = getattr(term, "sound", None)
                if snd and getattr(snd, "enabled", False):
                    snd.play_spear_throw()
                _show_spear_tutorial_if_first(term, player, active_spear)
                hit_zone, cancelled = run_spear_minigame(term, practice_player, target["type"], dist, active_spear)
                if cancelled:
                    add_msg("🛑 Throw cancelled. Spear held.")
                    continue
                if hit_zone == "miss":
                    target["fleeing"] = True
                    practice_player.spear_dur -= min(SPEAR_DEFS[active_spear].get("throw_cost", 20), practice_player.spear_dur)
                    add_msg(f"💨 Threw spear — MISSED! ({dist:.1f} tiles)")
                else:
                    hit_mult = {"head":1.5,"body":1.0,"graze":0.5,"near_miss":0.25}.get(hit_zone, 0.0)
                    target["fleeing"] = True
                    dmg = max(1, int(SPEAR_DEFS[active_spear].get("throw", 0) * hit_mult * (2 if practice_player.inventory.get("poison",0)>0 else 1)))
                    if practice_player.inventory.get("poison",0)>0:
                        practice_player.inventory["poison"] -= 1
                    target["hp"] -= dmg
                    _flash_hit(target.get("type",""))
                    practice_player.spear_dur -= min(SPEAR_DEFS[active_spear].get("throw_cost", 20), practice_player.spear_dur)
                    if active_spear == "ice_spear":
                        practice_player.spear_dur = 0
                    zone_desc = {"head":"HEAD HIT","body":"body hit","graze":"graze","near_miss":"near miss"}.get(hit_zone,"hit")
                    add_msg(f"🗡️ Spear throw — {zone_desc}! -{dmg} dmg ({max(0,target.get('hp',0)):.0f} HP left)")
                if practice_player.spear_dur <= 0:
                    practice_player.inventory[active_spear] = max(0, practice_player.inventory.get(active_spear,0)-1)
                    practice_player.spear_type = None
                    practice_player.spear_dur = 0
                    add_msg(f"💥 {active_spear.replace('_',' ').title()} broke!")
                if target.get("hp",0) <= 0:
                    resolve_animal_kill(practice_player, practice_world, target, msgs)
                elif hit_zone != "miss" and not cancelled:
                    target["fleeing"] = True
                    animal_retaliation(practice_player, practice_world, target, msgs)
                add_msg("🎮 Practice session ended. No meat, no permanent harm.")
                continue
            if ch == '3':
                run_practice_grid_mode(
                    lambda nearby: [a for a in nearby if a.get("type") not in ("grot","grot_leader")],
                    "❌ No practice targets could be generated for hunting practice.",
                    "hunting"
                )
                continue
            if ch == '4':
                break

    def house_has_couch():
        return any(fu["type"] == "couch" for fu in house.get("furniture", []))

    def nearest_turret():
        px,py=player.house_pos
        for fu in house.get("furniture",[]):
            fdef=FURNITURE_DEFS.get(fu["type"],{})
            if fdef.get("prot_type")=="turret":
                return fu
        return None

    if not getattr(player, "house_tutorial_shown", False):
        _unlock_and_show_tutorial(term, player, "house")
        player.house_tutorial_shown = True

    add_msg(f"🏠 You enter the {house['type'].replace('_',' ')}.")
    cmd_buf = ""

    def show_house_help():
        term.print_page([
            "🏠 HOUSE CONTROLS",
            "─" * TERM_WIDTH,
            "  Arrow keys      — move around the interior",
            "  p / place <item>   — place furniture from inventory",
            "  m / move         — move furniture with arrows, Enter to confirm",
            "  r / rotate       — rotate furniture under you",
            "  game             — use the gaming console",
            "  rest / sleep     — rest in the house",
            "  shop             — browse shop prices",
            "  buy <item>       — purchase from the shop",
            "  sell <item>      — sell inventory items",
            "  inv / inventory  — show inventory",
            "  q / quit / leave — exit the house",
            "", 
            "Tip: arrow keys move the player around the room.",
        ])

    def house_rest():
        if getattr(player, "gather_all", None):
            add_msg("⏳ Can't rest while gathering all."); return
        if player.resting:
            _resume_paused_crafting(player)
            player.resting = False; player.rest_mode = None
            add_msg("🛑 Stopped resting. (any paused crafting resumes)"); return
        now_pc = time.time()
        for t in player.active_tasks:
            if "paused_remaining" not in t:
                t["paused_remaining"] = max(0, int(t["end"] - now_pc))
        if getattr(player, "gather_all", None) and "paused_remaining" not in player.gather_all:
            player.gather_all["paused_remaining"] = max(0, int(player.gather_all["end"] - now_pc))
        _inside_h = None
        if player.inside_house_id:
            for _hh in world.houses:
                if _hh["id"]==player.inside_house_id and _hh.get("hp",0)>0:
                    _inside_h=_hh; break
        _has_bed = _inside_h and any(f["type"] in ("bed","couch") for f in _inside_h.get("furniture",[]))
        if player.campfire_fuel > 0:
            player.resting = True; player.rest_mode = "campfire"
            player.rest_last = time.time()
            player.used_campfire = True
            player.campfire_rested = True
            add_msg(f"🔥 Resting at campfire ({player.campfire_fuel} fuel parts). +30😴 +15❤️ +5⚡/game-hr. (crafting paused, type 'rest' to stop)")
        elif _has_bed:
            player.resting = True; player.rest_mode = "house_bed"
            player.rest_last = time.time()
            add_msg("🛏️ Resting in bed or couch! +30😴 +19❤️ +6⚡/game-hr. No damage! (type 'rest' to stop)")
        elif _inside_h:
            player.resting = True; player.rest_mode = "house_floor"
            player.rest_last = time.time()
            add_msg("🏠 Resting on house floor. +30😴/game-hr, no damage! (type 'rest' to stop)")
        else:
            player.resting = True; player.rest_mode = "floor"
            player.rest_last = time.time()
            add_msg("😴 Resting on floor. +30😴/game-hr but -10❤️/hr. (crafting paused, type 'rest' to stop)")

    while True:
        if house not in world.houses or house.get("hp", 0) <= 0:
            add_msg("💥 Your house has been destroyed! You are forced outside.")
            player.inside_house_id = None
            break
        hint = f"Cmd: {cmd_buf}" if cmd_buf else "[arrow keys] move  [P]lace  [M]ove  [R]otate  [Q]uit  [?]help"
        do_render(hint)
        key = term.get_key(0.15)
        if key is None:
            _update_houses(world, player, weather, msgs, time.time())
            continue
        if key == "ESC":
            key = "\x1b"

        if key in ("\x7f", "\b") and cmd_buf:
            cmd_buf = cmd_buf[:-1]
            continue
        if len(key) == 1 and key.isprintable() and key not in ("\r", "\n"):
            cmd_buf += key
            continue
        if key in ("\r", "\n") and cmd_buf:
            cmd = cmd_buf.strip().lower()
            cmd_buf = ""
            parts = cmd.split()
            act = parts[0]
            arg = " ".join(parts[1:]).strip()
            px, py = player.house_pos
            if act in ("q","quit","leave","exit"):
                if hdef["portable"]:
                    world.houses.remove(house)
                    player.inventory["teepee"] = player.inventory.get("teepee",0)+1
                    add_msg("⛺ You fold up the teepee and pack it away.")
                else:
                    add_msg(f"🚪 You leave the {house['type'].replace('_',' ')}.")
                player.inside_house_id = None
                break
            elif act == "game":
                house_console()
            elif act in ("help","?"):
                show_house_help()
            elif act in ("inv","inventory"):
                inv_lines = ["🎒 INVENTORY", "─" * TERM_WIDTH, ""]
                for k,v in sorted(player.inventory.items()):
                    if k.startswith("unknown_") or not isinstance(v, int) or v <= 0:
                        continue
                    inv_lines.append(f"  {display_item_name(k):<30} {v}")
                inv_lines.append("")
                term.print_page(inv_lines)
            elif act == "shop":
                cat_keys = list(SHOP_CATEGORIES.keys())
                term.show_menu(["🏪 SHOP", "─"*TERM_WIDTH] + [f"  {k}" for k in cat_keys] + ["","  Press number. Enter to close."])
                while True:
                    ch = term.get_key_no_flush(0.5)
                    if ch in ('\r','\n','ESC'):
                        sys.stdout.write("\033[2J"); sys.stdout.flush(); break
                    if ch and ch.isdigit():
                        idx = int(ch)
                        if 1 <= idx <= len(cat_keys):
                            cn = cat_keys[idx-1]
                            out = [f"🏪 {cn.split('. ')[1]}", "─"*TERM_WIDTH, "  Name                       | Buy 🪙 | Sell 🪙"]
                            for ik in SHOP_CATEGORIES[cn]:
                                p = ITEM_PRICES.get(ik)
                                if p: out.append(f"  {ik.replace('_',' ').title():<28} | {int(p*1.5):<6} | {p}")
                            term.print_page(out); break
                add_msg("📦 Shop menu closed.")
            elif act in ("buy","sell"):
                qty_req = 1
                _qtoks = arg.split()
                if _qtoks and _qtoks[0] in ("all", "everything", "max"):
                    qty_req = "all"; arg = " ".join(_qtoks[1:])
                elif _qtoks and _qtoks[0].lstrip("-").isdigit():
                    qty_req = max(1, int(_qtoks[0])); arg = " ".join(_qtoks[1:])
                ik = arg.replace(" ", "_")
                if ik == "house":
                    ik = "teepee"
                if act == "buy" and ik == "textbook":
                    if player.inventory.get("textbook",0) >= 3:
                        add_msg("❌ Max 3 textbooks.")
                    elif player.coins >= 300:
                        player.coins -= 300
                        player.inventory["textbook"] = player.inventory.get("textbook",0)+1
                        player.textbooks_bought = getattr(player, "textbooks_bought", 0) + 1
                        add_msg("✅ Bought 📚 Textbook.")
                        if getattr(term, "sound", None) and term.sound.enabled: term.sound.play_buy()
                    else:
                        add_msg("❌ Need 300🪙")
                elif act == "buy" and ik == "id_lens":
                    if player.coins >= 50:
                        player.coins -= 50
                        player.inventory["id_lens"] = player.inventory.get("id_lens",0)+1
                        player.id_lens_bought = getattr(player, "id_lens_bought", 0) + 1
                        add_msg("✅ Bought 🔍 ID Lens.")
                        if getattr(term, "sound", None) and term.sound.enabled: term.sound.play_buy()
                    else:
                        add_msg("❌ Need 50🪙")
                elif ik not in ITEM_PRICES:
                    add_msg("❌ Not in shop. Type 'shop' to browse.")
                elif act == "buy":
                    c = int(ITEM_PRICES[ik]*1.5)
                    if qty_req == "all":
                        _n = int(player.coins // c) if c > 0 else 0
                    else:
                        _n = int(qty_req)
                    _n = max(1, _n)
                    _bought = 0
                    for _bi in range(_n):
                        if player.coins < c:
                            break
                        player.coins -= c; player.inventory[ik] = player.inventory.get(ik,0)+1
                        if ik == "axe": player.axe_dur = TOOL_DUR
                        if ik == "advanced_axe": player.axe_dur = TOOL_DUR_ADV
                        if ik == "pickaxe": player.pickaxe_dur = TOOL_DUR
                        if ik in player.station_hp: player.station_hp[ik] = STATION_MAX_HP
                        if ik in SPEAR_DEFS and (not player.spear_type or player.spear_dur <= 0):
                            player.spear_type = ik; player.spear_dur = SPEAR_DEFS[ik]["dur"]
                        _bought += 1
                    if _bought > 0:
                        if _bought == 1:
                            add_msg(f"✅ Bought {ik.replace('_',' ').title()} for {c}🪙")
                        else:
                            add_msg(f"✅ Bought {_bought}× {ik.replace('_',' ').title()} for {c*_bought}🪙")
                        if getattr(term, "sound", None) and term.sound.enabled: term.sound.play_buy()
                    else:
                        add_msg(f"❌ Need {c}🪙")
                else:
                    if ik in ("textbook","id_lens"):
                        add_msg("❌ Cannot sell.")
                    elif player.inventory.get(ik,0) > 0:
                        have = int(player.inventory.get(ik,0))
                        if qty_req == "all":
                            _n = have
                        else:
                            _n = min(int(qty_req), have)
                        _n = max(1, _n)
                        _sold = 0
                        for _si in range(_n):
                            if player.inventory.get(ik,0) <= 0:
                                break
                            player.coins += ITEM_PRICES[ik]; player.inventory[ik] -= 1
                            if ik in ("ice_chunk","freezing_water","freezing_dirty_water","arctic_water","snow"):
                                player.arctic_items_sold = getattr(player, "arctic_items_sold", 0) + 1
                            _sold += 1
                        if _sold == 1:
                            add_msg(f"✅ Sold {ik.replace('_',' ').title()} for {ITEM_PRICES[ik]}🪙")
                        else:
                            add_msg(f"✅ Sold {_sold}× {ik.replace('_',' ').title()} for {ITEM_PRICES[ik]*_sold}🪙")
                        if getattr(term, "sound", None) and term.sound.enabled: term.sound.play_sell()
                    else:
                        add_msg("❌ None to sell.")
            elif act in ("rest","sleep","unrest"):
                house_rest()
            elif act in ("place","p"):
                item_name = arg.replace(" ","_").lower() if arg else ""
                if not item_name:
                    add_msg("❌ Usage: place <item>")
                else:
                    fdef = FURNITURE_DEFS.get(item_name)
                    if not fdef:
                        add_msg(f"❌ '{item_name}' is not placeable furniture.")
                    elif player.inventory.get(item_name,0) <= 0:
                        add_msg(f"❌ No {item_name.replace('_',' ')} in inventory.")
                    elif fdef.get("requires") and not any(f["type"] == fdef["requires"] for f in house.get("furniture", [])):
                        add_msg(f"❌ Need a {fdef['requires'].replace('_',' ')} first.")
                    elif furniture_overlaps(px, py, fdef["w"], fdef["h"]):
                        add_msg("❌ Overlapped. Cannot place there.")
                    else:
                        if "furniture" not in house: house["furniture"]=[]
                        house["furniture"].append({"type":item_name,"ix":px,"iy":py,"rotation":0,"autofire":True,"ammo_type":None,"ammo_qty":0,"w":fdef["w"],"h":fdef["h"]})
                        player.inventory[item_name] -= 1
                        add_msg(f"✅ Placed {item_name.replace('_',' ').title()}!")
            elif act in ("rotate","r"):
                fu = furniture_at(px, py)
                if fu:
                    fu["rotation"] = (fu.get("rotation",0) + 1) % 4
                    add_msg(f"🔄 Rotated {fu['type'].replace('_',' ').title()}.")
                else:
                    add_msg("❌ No furniture at your position to rotate.")
            elif act in ("move","m"):
                fu = furniture_at(px, py)
                if not fu:
                    add_msg("❌ No furniture at your position.")
                else:
                    do_render(f"Move {fu['type'].replace('_',' ').title()} — arrows to reposition, Enter to confirm")
                    orig_ix,orig_iy = fu["ix"], fu["iy"]
                    while True:
                        mk = term.get_key_no_flush(30.0)
                        if mk is None:
                            continue
                        if mk == "ESC":
                            mk = "\x1b"
                        clamp_furniture_position(fu)
                        if mk == "UP":
                            fu["iy"] = max(0, fu["iy"]-1)
                        elif mk == "DOWN":
                            fu["iy"] = min(rows - (fu.get("h",1) if fu.get("rotation",0)%2==0 else fu.get("w",1)), fu["iy"]+1)
                        elif mk == "LEFT":
                            fu["ix"] = max(0, fu["ix"]-1)
                        elif mk == "RIGHT":
                            fu["ix"] = min(cols - (fu.get("w",1) if fu.get("rotation",0)%2==0 else fu.get("h",1)), fu["ix"]+1)
                        elif mk in ("\r","\n","q","Q","\x1b"):
                            break
                        clamp_furniture_position(fu)
                        if furniture_overlaps(fu["ix"], fu["iy"], fu.get("w",1), fu.get("h",1), ignore=fu):
                            fu["ix"], fu["iy"] = orig_ix, orig_iy
                            add_msg("❌ Overlapped. Cannot place there.")
                            break
                        do_render(f"Moving {fu['type'].replace('_',' ')} — Enter to confirm")
                    add_msg(f"📦 Moved {fu['type'].replace('_',' ').title()} to ({fu['ix']},{fu['iy']}).")
            else:
                add_msg("❌ Unknown house command. Try 'help'.")
            msgs[:] = msgs[-4:]
            continue

        px,py = player.house_pos
        if key == "UP": player.house_pos[1] = max(0, py-1)
        elif key == "DOWN": player.house_pos[1] = min(max_row, py+1)
        elif key == "LEFT": player.house_pos[0] = max(0, px-1)
        elif key == "RIGHT": player.house_pos[0] = min(max_col, px+1)
        elif key in ("q","Q","l","L","\x1b"):
            if hdef["portable"]:
                world.houses.remove(house)
                player.inventory["teepee"] = player.inventory.get("teepee",0)+1
                add_msg("⛺ You fold up the teepee and pack it away.")
            else:
                add_msg(f"🚪 You leave the {house['type'].replace('_',' ')}.")
            player.inside_house_id = None
            break
        elif key == "?":
            show_house_help()
        elif key in ("h","H"):
            dmg_frac,fire_frac=_house_protection_pct(house)
            add_msg(f"🏠 {house['type'].title()}: HP {house['hp']}/{house['max_hp']} | Dmg reduction {int((1-dmg_frac)*100)}% | Fire reduction {int((1-fire_frac)*100)}%")
        elif key in ("t","T"):
            tu=nearest_turret()
            if tu:
                tu["autofire"] = not tu.get("autofire", True)
                add_msg(f"🔫 {tu['type'].replace('_',' ').title()} autofire {'ON' if tu['autofire'] else 'OFF'}.")
            else:
                add_msg("❌ No cannon or ballista nearby.")
        elif key in ("f","F"):
            tu=nearest_turret()
            if tu:
                fdef=FURNITURE_DEFS.get(tu["type"],{})
                ammo_types=fdef.get("ammo_types",())
                available={a:player.inventory.get(a,0) for a in ammo_types if player.inventory.get(a,0)>0}
                if not available:
                    add_msg(f"❌ No compatible ammo ({', '.join(ammo_types)}) in inventory.")
                else:
                    for atype,qty in available.items():
                        tu["ammo_type"] = atype; tu["ammo_qty"] = tu.get("ammo_qty",0)+qty
                        player.inventory[atype] = 0
                    add_msg(f"🔫 Loaded {sum(available.values())} ammo.")
            else:
                add_msg("❌ No cannon or ballista nearby.")
        elif key in ("z","Z"):
            house_rest()
        elif key in ("r","R"):
            fu=furniture_at(px,py)
            if fu:
                old_rot = fu.get("rotation",0)
                new_rot = (old_rot + 1) % 4
                fu["rotation"] = new_rot
                if furniture_overlaps(fu["ix"], fu["iy"], ignore=fu, rotation=new_rot):
                    fu["rotation"] = old_rot
                    add_msg("❌ Can't rotate there; it would overlap other furniture.")
                else:
                    add_msg(f"🔄 Rotated {fu['type'].replace('_',' ').title()}.")
            else:
                add_msg("❌ No furniture at your position to rotate.")
        elif key in ("p","P"):
            do_render("Type item name to place (e.g. 'bed'): ")
            sys.stdout.write("\r\n  > "); sys.stdout.flush()
            item_line = ""
            while True:
                ch = term.get_key_no_flush(30.0)
                if ch is None:
                    break
                if ch in ("\r","\n"):
                    break
                if ch == "\x7f":
                    item_line = item_line[:-1]
                elif len(ch) == 1:
                    item_line += ch
            item_name=item_line.strip().replace(" ","_").lower()
            fdef=FURNITURE_DEFS.get(item_name)
            if not fdef:
                add_msg(f"❌ '{item_name}' is not placeable furniture.")
            elif player.inventory.get(item_name,0)<=0:
                add_msg(f"❌ No {item_name.replace('_',' ')} in inventory.")
            elif fdef.get("requires") and not any(f["type"]==fdef["requires"] for f in house.get("furniture",[])):
                add_msg(f"❌ Need a {fdef['requires'].replace('_',' ')} first.")
            elif furniture_overlaps(px, py, fdef["w"], fdef["h"]):
                add_msg("❌ Overlapped. Cannot place there.")
            else:
                if "furniture" not in house: house["furniture"]=[]
                house["furniture"].append({"type":item_name,"ix":px,"iy":py,"rotation":0,"autofire":True,"ammo_type":None,"ammo_qty":0,"w":fdef["w"],"h":fdef["h"]})
                player.inventory[item_name]-=1
                add_msg(f"✅ Placed {item_name.replace('_',' ').title()}!")
        elif key in ("m","M"):
            fu=furniture_at(px,py)
            if not fu:
                add_msg("❌ No furniture at your position.")
            else:
                do_render(f"Move {fu['type'].replace('_',' ').title()} — arrow keys, Enter to confirm")
                orig_ix,orig_iy=fu["ix"],fu["iy"]
                while True:
                    mk = term.get_key_no_flush(30.0)
                    if mk is None: continue
                    if mk == "ESC":
                        mk = "\x1b"
                    if mk == "UP":
                        fu["iy"] = max(0, fu["iy"]-1)
                    elif mk == "DOWN":
                        fu["iy"] = min(rows - (fu.get("h",1) if fu.get("rotation",0)%2==0 else fu.get("w",1)), fu["iy"]+1)
                    elif mk == "LEFT":
                        fu["ix"] = max(0, fu["ix"]-1)
                    elif mk == "RIGHT":
                        fu["ix"] = min(cols - (fu.get("w",1) if fu.get("rotation",0)%2==0 else fu.get("h",1)), fu["ix"]+1)
                    elif mk in ("\r","\n","q","Q","\x1b"):
                        break
                    clamp_furniture_position(fu)
                    if furniture_overlaps(fu["ix"], fu["iy"], fu.get("w",1), fu.get("h",1), ignore=fu):
                        fu["ix"], fu["iy"] = orig_ix, orig_iy
                        add_msg("❌ Overlapped. Cannot place there.")
                        break
                    do_render(f"Moving {fu['type'].replace('_',' ')} — Enter to confirm")

                add_msg(f"📦 Moved {fu['type'].replace('_',' ').title()} to ({fu['ix']},{fu['iy']}).")
        msgs[:] = msgs[-4:]

    return msgs


def _flee_cat_on_combat(player, world, msg):
    """Make the bonded cat dash away when combat is about to start."""
    now = time.time()
    following_cat = next((a for a in world.animals if a.get("type")=="cat" and a.get("_following_player")), None)
    if not following_cat:
        return
    following_cat["fleeing"] = True
    following_cat.pop("_following_player", None)
    following_cat.pop("_hunting_prey", None)
    player.cat_following = False
    player.cat_hunt_return = now + 30.0
    msg.append("🐈 Your cat dashes away from the fight! It'll be back...")
    msg[:] = msg[-3:]


def _tick_cat_companion(player, world, msg):
    """Handle periodic cat companion behaviors: meow, sitting messages, hunt/return."""
    now = time.time()
    # First time any wild cat wanders close, the old man chimes in with advice.
    if not getattr(player, "cat_approach_announced", False):
        approaching = next((a for a in world.animals
                            if a.get("type") == "cat" and a.get("hp", 1) > 0
                            and not a.get("_following_player")
                            and math.hypot(a["x"]-player.x, a["y"]-player.y) <= 5.0), None)
        if approaching is not None:
            player.cat_approach_announced = True
            # Queue a full-screen popup (shown by main loop via player._pending_popup)
            player._pending_popup = [
                "🧓 Old Man speaks!",
                "",
                "  Hohoho!  The cats around here really ARE friendly!",
                "",
                "  • Drop some meat near a cat to tame it.",
                "  • Drop catnip and the cat will come running to you.",
                "  • Once tamed, a cat will follow and protect you!",
                "",
                "  Press Enter to continue.",
            ]
    following_cat = next((a for a in world.animals if a.get("type")=="cat" and a.get("_following_player")), None)
    # If the cat fled during combat, try to bring it back once combat is over
    # and the return timer has elapsed.
    if not following_cat and not player.in_combat and getattr(player, "cat_hunt_return", 0) > 0 and now >= player.cat_hunt_return:
        # Find the closest cat that was previously bonded/fled
        candidate = None; best_d = float('inf')
        for a in world.animals:
            if a.get("type") != "cat": continue
            if a.get("hp", 1) <= 0: continue
            d = math.hypot(a["x"]-player.x, a["y"]-player.y)
            if d < best_d:
                best_d = d; candidate = a
        if candidate is not None:
            candidate["_following_player"] = True
            candidate["fleeing"] = False
            candidate.pop("_hunting_prey", None)
            player.cat_following = True
            player.cat_hunt_return = 0.0
            msg.append("🐈 Your cat reappears and trots back to your side!")
            msg[:] = msg[-3:]
            following_cat = candidate
    # Check if any cat was following; if none found but player thinks one is, correct state
    if not following_cat:
        if player.cat_following:
            player.cat_following = False
        return

    # Hunt announcements
    if following_cat.pop("_announce_hunt", None):
        prey_lbl = str(following_cat.get("_hunting_prey_label","prey")).replace("_"," ")
        msg.append("🐈 Your cat spots prey and dashes off to hunt!")
        msg[:] = msg[-3:]
    if following_cat.get("_announce_return", False):
        dist_to_player = math.hypot(following_cat["x"] - player.x, following_cat["y"] - player.y)
        if dist_to_player <= 3.0:
            following_cat.pop("_announce_return", None)
            msg.append("🐈 Your cat returns to your side and stops hunting.")
            msg[:] = msg[-3:]

    # Cat flees during combat/active hunt; returns after
    if player.in_combat:
        following_cat["_following_player"] = False
        following_cat["fleeing"] = True
        following_cat.pop("_following_player", None)
        player.cat_following = False
        player.cat_hunt_return = now + 30.0
        msg.append("🐈 Your cat dashes away from the fight! It'll be back...")
        msg[:] = msg[-3:]
        return

    # Meow — frequency depends on loyalty. A disgruntled cat (≤ -10) meows
    # much less often. Loyalty is NOT shown here; check the cat status menu.
    _loy = following_cat.get("loyalty", 0)
    meow_interval = 120.0 if _loy <= -10 else 30.0
    if now - player.last_meow >= meow_interval:
        player.last_meow = now
        meow = random.choice(CAT_MEOWS)
        msg.append(f"🐈 «{meow}»")
        msg[:] = msg[-3:]
        snd_c = getattr(player, "sound", None)
        if snd_c and getattr(snd_c, "enabled", False): snd_c.play_cat_meow()

    # The cat eventually decides it's okay to be petted. This permission resets
    # after 4–8 unpaused minutes, or whenever you give it meat/catnip.
    uc = getattr(player, "unpaused_clock", 0.0)
    if "_pet_ok_at" not in following_cat:
        following_cat["_pet_ok_at"] = uc + random.uniform(240.0, 480.0)
    if not following_cat.get("_pet_ok") and uc >= following_cat["_pet_ok_at"]:
        following_cat["_pet_ok"] = True
        msg.append("🐈 Your cat rolls over and purrs — it's okay to pet now!")
        msg[:] = msg[-3:]

    # "Cat sitting on X" every ~30s when player is idle (resting or not moving)
    player_idle = player.resting or (not player.active_tasks and not player.in_combat)
    if player_idle and now - player.last_cat_action >= 30.0:
        player.last_cat_action = now
        # Build list of SPECIFIC things the cat could sit on: your stations and
        # your inventory items (never a vague "something").
        sit_options = []
        owned_stations = [s for s in ("woodworking_station","furnace","smelter","sewing_station","water_filter","liquifier") if player.station_hp.get(s,0)>0]
        sit_options.extend(display_item_name(s) for s in owned_stations)
        inv_items = [k for k,v in player.inventory.items() if isinstance(v,(int,float)) and v>0 and k not in ("coins",)]
        if inv_items:
            sit_options.extend(display_item_name(k) for k in random.sample(inv_items, min(3, len(inv_items))))
        if player.campfire_fuel > 0: sit_options.append("campfire")
        # Drop any blank/placeholder options just in case
        sit_options = [s for s in sit_options if s and str(s).strip() and str(s).strip().lower() != "something"]
        if sit_options:
            chosen = random.choice(sit_options)
            tmpl = random.choice(CAT_SITTING_TEMPLATES)
            msg.append("🐈 " + tmpl.format(item=str(chosen).replace("_"," ")))
            msg[:] = msg[-3:]


    # When idle and not hunting, cat may bring a kill back
    if player_idle and following_cat.get("_last_hunt_kill"):
        kill_time = following_cat.pop("_last_hunt_kill")
        if now - kill_time < 60.0:
            msg.append("🐈 YOUR GODLY CAT IS DEVOURING MEAT IN FRONT OF YOU! JUST TRYING TO MAKE YOU JEALOUS… HEEHEE!")
            msg[:] = msg[-3:]


def _tick_animal_sounds(player, world, sound):
    """Ambient animal proximity sounds are disabled — the squirrel "tappity"
    gnawing and other proximity SFX were unwanted. Cat meows are handled by
    _tick_cat_companion instead."""
    return
    now = time.time()
    if now - getattr(player, "_last_animal_sound", 0) < 20.0:
        return
    player._last_animal_sound = now + random.uniform(0, 10)
    nearby = [a for a in world.animals
              if math.hypot(a["x"] - player.x, a["y"] - player.y) < FOG_RADIUS * 0.8
              and a.get("hp", 1) > 0]
    if not nearby:
        return
    chosen = random.choice(nearby)
    atype = chosen.get("type", "")
    sound.play_animal_type(atype)


# ==================== GRID MODE ====================
GRID_SIZE   = 20
GRID_EMPTY  = "🟫"
GRID_TREE   = "🌲"
GRID_ROCK   = "🪨"
GRID_CATNIP = "🌿"
GRID_BERRIES = "🫐"
GRID_MUSHROOMS = "🍄"
GRID_WATER = "💧"
GRID_GRASS = "🌾"
GRID_MOSS = "🌿"   # herb (U+1F33F) — unambiguously 2-wide; replaces ☘️ which is 1-wide in many terminals
GRID_RESOURCE = "🌱"

PREY_FLASH_TYPES = {
    "rabbit","young_rabbit","deer","young_deer","antelope","young_antelope",
    "squirrel","young_squirrel","seal","penguin","salmon",
}
ENTITY_GRID_SIZE = {
    "deer":2,"young_deer":2,"antelope":2,"young_antelope":2,
    "tree":2,"rock_vein":2,
    "rabbit":1,"young_rabbit":1,"squirrel":1,"young_squirrel":1,
    "cat":1,"young_cat":1,"grot":1,"grot_leader":1,"salmon":1,"seal":1,"penguin":1,
}
GRID_Z = {
    "grot_leader":90,"grot":85,"cat":82,"deer":75,"young_deer":75,"antelope":75,"young_antelope":75,
    "rabbit":70,"young_rabbit":70,"squirrel":70,"young_squirrel":70,"salmon":60,"seal":60,"penguin":60,
    "young_cat":55,"tree":50,"rock_vein":30,"catnip":20,
}


def _grid_calc_player_energy(player):
    armor_penalty = {"light_armor":10,"medium_armor":20,"heavy_armor":40}.get(player.wearing or "",0)
    ins = (CLOTHING_INSULATION.get(player.wearing_pants or "",0)+
           CLOTHING_INSULATION.get(player.wearing_shirt or "",0))
    return max(5, 100 - armor_penalty - ins + random.randint(-5,5))


def _grid_calc_grot_energy(player):
    # Grots have 15 fewer energy points than the player would in the same spot.
    armor_penalty = {"light_armor":10,"medium_armor":20,"heavy_armor":40}.get(getattr(player, "wearing", None) or "", 0)
    ins = (CLOTHING_INSULATION.get(getattr(player, "wearing_pants", None) or "", 0)+
           CLOTHING_INSULATION.get(getattr(player, "wearing_shirt", None) or "", 0))
    return max(5, 100 - armor_penalty - ins - 15 + random.randint(-5, 5))


def _grid_terrain_factor(world, x, y):
    """Movement multiplier for rough terrain — trees slow, rocks slow more.
    Applies to grots so terrain affects them just like the player."""
    xi, yi = _world_tile(x, y)
    factor = 1.0
    for (cx, cy), cl in world.clusters.items():
        item = cl.get("real_item", "")
        if item not in ("wood", "rock"):
            continue
        for di in range(2):
            for dj in range(2):
                if xi == cx + di and yi == cy + dj:
                    factor = min(factor, 0.77 if item == "wood" else 0.67)
    return factor



def _grid_render(term, player, world, entities, grid_ox, grid_oy, round_num, player_energy,
                  log_lines, action_hint, last_move_time, grid_start_t=None):
    """Render the 20x20 grid plus sidebar into the terminal."""
    GS = GRID_SIZE
    # Build cell map: (i,j) → (emoji, z)
    cells = {}  # key: (gi,gj) 0-based grid indices → (emoji, z)

    # Background
    for gj in range(GS):
        for gi in range(GS):
            cells[(gi,gj)] = (GRID_EMPTY, 0)

    # World resources/clusters in view
    for (cx,cy), cl in world.clusters.items():
        gi, gj = int(cx) - grid_ox, int(cy) - grid_oy
        if not (0<=gi<GS and 0<=gj<GS): continue
        item = cl.get("real_item") or cl.get("meta",{}).get("item","")
        if item == "wood":  # 1×1 to match graphics-mode density
            if cells.get((gi,gj),(None,0))[1] < 50:
                cells[(gi,gj)] = (GRID_TREE, 50)
        elif item == "rock":  # 1×1 to match graphics-mode density
            if cells.get((gi,gj),(None,0))[1] < 30:
                cells[(gi,gj)] = (GRID_ROCK, 30)
        elif item == "catnip":
            if cells.get((gi,gj),(None,0))[1] < 20:
                cells[(gi,gj)]=(GRID_CATNIP,20)
        else:
            # Show the same kinds of resources visible from the main world
            # screen instead of reducing grid mode to trees and rocks.
            source_item = cl.get("meta", {}).get("item", item)
            category = cl.get("category", "")
            if (source_item == "poisonous_berry" or item == "poisonous_berry") and cl.get("is_identified"):
                icon = "💀"  # U+1F480 skull — 2-wide; ☠️ U+2620 is 1-wide in many terminals
            elif source_item in ("berries", "wild_berries", "sweet_berries", "sour_berries", "glowing_berries", "frostberry", "shimmer_frostberry", "poisonous_berry") or item in BERRY_ITEMS:
                icon = GRID_BERRIES
            elif source_item in ("mushrooms", "mushroom_death_cap", "mystery_mushroom", "black_trumpets", "spotted_mushrooms") or item in MUSHROOM_ITEMS:
                icon = GRID_MUSHROOMS
            elif source_item in ("water", "arctic_water") or category == "water" or item in ("fresh_water", "dirty_water", "freezing_water", "freezing_dirty_water"):
                icon = GRID_WATER
            elif source_item in ("fibergrass", "snow"):
                icon = GRID_GRASS
            elif str(source_item).startswith("moss") or str(item).startswith("moss"):
                icon = GRID_MOSS
            else:
                icon = GRID_RESOURCE
            if cells.get((gi,gj),(None,0))[1] < 20:
                cells[(gi,gj)]=(icon,20)

    # Animation timing
    _now_a = time.time()
    _elapsed = _now_a - (grid_start_t or _now_a)
    # Player ANSI color phase
    if _elapsed < 3.0:
        _p_color = "\033[33m" if int(_now_a*10) % 2 == 0 else "\033[34m"
    else:
        _p_color = "\033[33m" if int(_now_a*2) % 2 == 0 else "\033[34m"
    # Player icon frame (visible 400ms / marker 100ms cycle = 500ms total)
    _p_frame_pos = (_now_a * 1000) % 500
    _p_marker = _p_frame_pos >= 400
    # Grot: blink bright red on/off every 0.25s
    _g_color = "\033[91m" if int(_now_a*4) % 2 == 0 else "\033[0m"
    _g_marker = False
    # Prey ANSI: green/cyan flash (offset phase) so rabbits/deer animate too
    _pr_color = "\033[32m" if int(_now_a*5 + 1) % 2 == 0 else "\033[36m"
    _pr_frame_pos = ((_now_a + 0.40) * 1000) % 500
    _pr_marker = _pr_frame_pos >= 400
    _ansi_reset = "\033[0m"

    # Entities
    for ent in entities:
        ex = int(round(ent["x"])); ey = int(round(ent["y"]))
        gi = ex - grid_ox; gj = ey - grid_oy
        if not (-1<=gi<GS+1 and -1<=gj<GS+1): continue
        adef = ANIMAL_DEFS.get(ent["type"],{})
        icon = ent.get("icon") or adef.get("icon","?")
        if isinstance(icon,str) and len(icon)>2: icon=icon[:2]
        sz = ENTITY_GRID_SIZE.get(ent["type"],1)
        z  = GRID_Z.get(ent["type"],70)
        if ent.get("_grid_shield"): icon="🛡️"
        # Grot flashing
        if ent.get("type") in ("grot","grot_leader") and ent.get("hp",0) > 0:
            if _g_marker:
                icon = "□"
            icon = f"{_g_color}{icon}{_ansi_reset}"
        # Prey flashing (rabbits, deer, antelope, squirrels) — same idea as grots,
        # with the emoji icon kept as the fallback when the marker isn't showing.
        elif ent.get("type") in PREY_FLASH_TYPES and ent.get("hp",0) > 0:
            if _pr_marker:
                icon = "○"
            icon = f"{_pr_color}{icon}{_ansi_reset}"
        for di in range(sz):
            for dj in range(sz):
                p=(gi+di,gj+dj)
                if 0<=p[0]<GS and 0<=p[1]<GS:
                    if cells.get(p,(None,0))[1] < z:
                        cells[p]=(icon,z)

    # Player icon
    now = time.time()
    moving = (now - last_move_time) < 0.75
    if _p_marker:
        picon = "□"
    elif moving:
        picon = "🚶"
    elif player.spear_type and player.spear_dur>0:
        picon = "⚔️"
    else:
        picon = "🧍"
    picon = f"{_p_color}{picon}{_ansi_reset}"
    px, py = _world_tile(player.x, player.y)
    pgi = px - grid_ox; pgj = py - grid_oy
    if 0<=pgi<GS and 0<=pgj<GS:
        cells[(pgi,pgj)] = (picon, 100)

    # Build rows
    SIDEBAR_W = 34
    # Header
    hp_bar = f"❤️{int(player.health)}/{int(player.max_health)}"
    spear_lbl = (player.spear_type or "none").replace("_"," ")
    shield_lbl = (player.shield_type or "none").replace("_"," ")
    header = vfit(f"  ⚔️ GRID MODE  Round {round_num}  Energy:{player_energy}  {hp_bar}  🗡️{spear_lbl}  🛡️{shield_lbl}", TERM_WIDTH)
    sep = "─" * TERM_WIDTH
    lines = [header, sep]

    sidebar_content = []
    hostile = [e for e in entities if e.get("atk",0)>0 or e.get("type","") in ("grot","grot_leader","deer","antelope")]
    for e in hostile[:8]:
        etype = e.get("type","?").replace("_"," ").title()
        ehp = e.get("hp",0); emhp = e.get("max_hp",ehp)
        ex2,ey2=int(round(e["x"])),int(round(e["y"]))
        sidebar_content.append(f"{etype:<12} HP:{ehp}/{emhp} @{ex2},{ey2}")
    while len(sidebar_content) < GS:
        sidebar_content.append("")
    # Copy log lines into sidebar tail, wrapping long entries
    wrapped_log = []
    for ll in log_lines:
        for frag in vwrap(ll, SIDEBAR_W):
            wrapped_log.append(frag)
    wrapped_tail = wrapped_log[-6:]
    for idx, ll in enumerate(wrapped_tail):
        sidebar_content[GS - 6 + idx] = vtrunc(ll, SIDEBAR_W)

    for gj in range(GS):
        row_cells = [_cell2(cells.get((gi,gj),(GRID_EMPTY,0))[0]) for gi in range(GS)]
        row_str = "".join(row_cells)
        side = sidebar_content[gj] if gj < len(sidebar_content) else ""
        lines.append(f"  {row_str} │ {vtrunc(side, SIDEBAR_W)}")

    lines.append(sep)
    hint = action_hint or "[↑]up [↓]dn [←]lt [→]rt [S/A/E]strike [T]throw [B]block [P]pass [Q]quit"
    lines.append(vfit(f"  {hint}", TERM_WIDTH))

    sys.stdout.write("\033[2J\033[H" + "\r\n".join(lines))
    sys.stdout.flush()


def run_grid_mode(term, player, world, initial_targets, msg_out=None):
    """Full 20x20 turn-based grid combat/hunt mode.
    initial_targets: list of animal dicts that triggered grid mode.
    Returns list of messages (also appended to msg_out if provided).
    """
    import select as _sel
    msgs = []
    sound = getattr(term, "sound", None) or getattr(player, "sound", None)
    if sound and getattr(sound, "enabled", False):
        try:
            sound.stop_gather()
        except Exception:
            pass
        sound.start_combat_bgm()

    def add_msg(m):
        msgs.append(m)
        if msg_out is not None: msg_out.append(m)

    round_num   = 1
    player_energy = _grid_calc_player_energy(player)
    last_move_time = 0.0
    log_lines   = []
    action_hint = ""
    grid_start_t = time.time()

    # Build entity list (all animals within 12 tiles of player)
    entities = [a for a in world.animals if math.hypot(a["x"]-player.x, a["y"]-player.y) <= 12.0]
    for e in entities:
        if "max_hp" not in e: e["max_hp"] = e.get("hp",1)
    # Ensure all initial targets are included
    for t in initial_targets:
        if t not in entities: entities.append(t)

    # Snapshot pre-grid state so prey that never actually saw / engaged the
    # player aren't forever marked as "fleeing" after we exit grid mode.
    _pre_flee = {id(e): bool(e.get("fleeing", False)) for e in entities}
    _initial_ids = {id(t) for t in initial_targets}
    _engaged_ids = set(_initial_ids)  # ids of entities that took damage or hit the player

    # Track which squirrels are in trees
    # e["_in_tree"] = depth (rounds spent in tree); at depth≥3 they escape

    def grid_origin():
        px, py = _world_tile(player.x, player.y)
        ox = px - GRID_SIZE//2
        oy = py - GRID_SIZE//2
        return ox, oy

    def do_render(hint=""):
        ox,oy = grid_origin()
        for wx in range(ox, ox + GRID_SIZE):
            for wy in range(oy, oy + GRID_SIZE):
                world._load(wx, wy)
        _grid_render(term, player, world, entities, ox, oy, round_num,
                     player_energy, log_lines[-8:], hint, last_move_time, grid_start_t)

    def grots_turn():
        """Run a turn for all hostile grots; locks input briefly."""
        moved_any = False
        for ent in list(entities):
            if ent.get("type") in ("cat", "young_cat") and ent.get("hp", 0) > 0:
                before = (ent.get("x"), ent.get("y"))
                entity_turn(ent)
                if (ent.get("x"), ent.get("y")) != before:
                    moved_any = True
        for ent in list(entities):
            if ent.get("type") in ("grot","grot_leader") and ent.get("hp",0) > 0:
                entity_turn(ent)
                moved_any = True
        dead = remove_dead(); resolve_kills(dead)
        if moved_any:
            do_render("👹 Grot turn complete.")
            time.sleep(GROT_GRID_STEP_DELAY)
        return moved_any


    def find_entities_at(wx, wy, exclude=None):
        hits=[]
        for e in entities:
            if e is exclude or e.get("hp",0)<=0: continue
            if int(round(e["x"]))==wx and int(round(e["y"]))==wy:
                hits.append(e)
        return hits

    def nearest_entity(from_x, from_y):
        best=None; bd=float('inf')
        for e in entities:
            if e.get("hp",0)<=0: continue
            d=math.hypot(e["x"]-from_x,e["y"]-from_y)
            if d<bd: bd=d; best=e
        return best, bd

    def entity_strike(attacker, target):
        """Attacker strikes target; returns (dmg, killed)."""
        atk = attacker.get("atk",2)
        def_val = target.get("def",0)
        raw = max(0, int(round(atk - def_val)))
        if attacker.get("type") == "grot_leader":
            berserk = attacker.get("hp",1) < attacker.get("max_hp",1)*0.5
            if berserk: raw = int(raw * 1.5)
        target["hp"] = target.get("hp",0) - raw
        return raw, target.get("hp",0)<=0

    def remove_dead():
        nonlocal entities
        dead=[]
        for e in entities[:]:
            if e.get("hp",0)<=0:
                dead.append(e)
                try: entities.remove(e)
                except ValueError: pass
        return dead

    def resolve_kills(dead_list):
        for e in dead_list:
            add_msg(f"💀 {e.get('type','?').replace('_',' ').title()} killed!")
            try: resolve_animal_kill(player, world, e, msgs)
            except Exception: pass
            try: world.animals.remove(e)
            except (ValueError, Exception): pass

    def player_strike():
        nonlocal player_energy
        if player_energy < 15:
            add_msg("⚡ Not enough energy to strike (15).")
            return
        if not player.spear_type or player.spear_dur<=0:
            add_msg("❌ No spear equipped.")
            return
        sdef = SPEAR_DEFS.get(player.spear_type,{})
        if sdef.get("no_heavy_spear") if False else False: pass  # placeholder
        # Find nearest entity within 1.5 tiles
        tgt,dist = nearest_entity(player.x, player.y)
        if tgt is None or dist > 1.5:
            add_msg(f"❌ Nothing in range to strike (need ≤1.5 tiles, nearest {dist:.1f}).")
            return
        if SHIELD_DEFS.get(player.shield_type,{}).get("no_heavy_spear") and player.spear_type in ("heavy_spear","advanced_heavy_spear"):
            add_msg("❌ Can't use heavy spear while shield equipped.")
            return
        dmg = sdef.get("strike",0) * (2 if player.inventory.get("poison",0)>0 else 1)
        if player.inventory.get("poison",0)>0: player.inventory["poison"]-=1
        tgt["hp"]=tgt.get("hp",0)-dmg
        player.spear_dur -= sdef.get("strike_cost",dmg)
        player_energy -= 15
        zone = tgt.get("type","?").replace("_"," ").title()
        add_msg(f"⚔️ Strike {zone}! -{dmg} HP ({max(0,tgt.get('hp',0))} left)")
        if player.spear_dur<=0:
            player.inventory[player.spear_type]=max(0,player.inventory.get(player.spear_type,0)-1)
            add_msg(f"💥 {player.spear_type.replace('_',' ').title()} broke!")
            player.spear_type=None; player.spear_dur=0
        dead=remove_dead(); resolve_kills(dead)

    def player_throw():
        nonlocal player_energy
        if player_energy < 35:
            add_msg("⚡ Not enough energy to throw (35).")
            return
        if not player.spear_type or player.spear_dur<=0:
            add_msg("❌ No spear equipped.")
            return
        sdef=SPEAR_DEFS.get(player.spear_type,{})
        if sdef.get("throw",0)<=0:
            add_msg("❌ This spear is melee only.")
            return
        # Pick nearest target
        tgt,dist=nearest_entity(player.x,player.y)
        if tgt is None:
            add_msg("❌ No target in range.")
            return
        # Squirrel in tree: must throw
        if tgt.get("_in_tree"):
            pass  # always allowed
        elif dist > 12:
            add_msg(f"❌ Too far to throw ({dist:.1f} tiles, max 12).")
            return
        # Apply shield cursor penalty
        cm = sdef.get("cursor_mult",1.0)
        if player.shield_type: cm *= SHIELD_DEFS.get(player.shield_type,{}).get("cursor_mult_throw",1.0)
        sdef_throw = dict(sdef); sdef_throw["cursor_mult"] = cm
        # Override cursor_mult temporarily
        SPEAR_DEFS[player.spear_type]["cursor_mult"] = cm
        hit_zone,cancelled = run_spear_minigame(term, player, tgt.get("type","deer"), dist, player.spear_type)
        SPEAR_DEFS[player.spear_type]["cursor_mult"] = sdef.get("cursor_mult",1.0)
        if cancelled:
            add_msg("🛑 Throw cancelled.")
            return
        player_energy -= 35
        if hit_zone=="miss":
            player.spear_dur-=min(sdef.get("throw_cost",20),player.spear_dur)
            add_msg("💨 Missed!")
        else:
            hm={"head":1.5,"body":1.0,"graze":0.5,"near_miss":0.25}.get(hit_zone,0)
            dmg=max(1,int(sdef.get("throw",0)*hm))
            tgt["hp"]=tgt.get("hp",0)-dmg
            player.spear_dur-=min(sdef.get("throw_cost",20),player.spear_dur)
            if player.spear_type=="ice_spear": player.spear_dur=0
            add_msg(f"🗡️ Throw {hit_zone}! -{dmg} HP ({max(0,tgt.get('hp',0))} left)")
        if player.spear_dur<=0:
            player.inventory[player.spear_type]=max(0,player.inventory.get(player.spear_type,0)-1)
            add_msg(f"💥 {player.spear_type.replace('_',' ').title()} broke!")
            player.spear_type=None; player.spear_dur=0
        dead=remove_dead(); resolve_kills(dead)

    def player_block():
        nonlocal player_energy
        if not player.shield_type:
            add_msg("❌ No shield equipped to block.")
            return
        sdef=SHIELD_DEFS.get(player.shield_type,{})
        ecost=sdef.get("energy_cost",10)
        if player_energy<ecost:
            add_msg(f"⚡ Not enough energy to block ({ecost}).")
            return
        if player.combat: player.combat["blocking"]=True
        player_energy-=ecost
        add_msg(f"🛡️ Blocking! Next hit will be shielded.")

    def entity_turn(ent):
        """Single entity takes its turn: move toward player or flee/hunt."""
        etype=ent.get("type","")
        if ent.get("hp",0)<=0: return
        # Squirrel in tree: get deeper each round
        if ent.get("_in_tree"):
            ent["_in_tree"] = ent.get("_in_tree",0)+1
            if ent.get("_in_tree",0)>=3:
                add_msg(f"🐿️ Squirrel escaped up the tree!")
                ent["hp"]=0
            return
        ex=int(round(ent["x"])); ey=int(round(ent["y"]))
        dist_to_player=math.hypot(ent["x"]-player.x,ent["y"]-player.y)
        ox,oy=grid_origin()
        speed=ent.get("speed_cpm",ANIMAL_DEFS.get(etype,{}).get("speed_cpm",15))
        if etype in ("grot", "grot_leader"):
            base_mt = max(1, int(_grid_calc_grot_energy(player) // 8))
            # Terrain still applies to grots: trees/rocks cut into their movement.
            move_tiles = max(1, int(round(base_mt * _grid_terrain_factor(world, ent["x"], ent["y"]))))
        else:
            move_tiles=max(1,round(speed/15.0))  # tiles this turn

        # Grot leader AI
        if etype=="grot_leader":
            cat_prey = None; cat_dist = float('inf')
            for prey in entities:
                if prey is ent or prey.get("type") not in ("cat", "young_cat") or prey.get("hp", 0) <= 0:
                    continue
                pd = math.hypot(prey["x"]-ent["x"], prey["y"]-ent["y"])
                if pd <= 10.0 and pd < cat_dist:
                    cat_prey = prey; cat_dist = pd
            if cat_prey:
                cat_prey["fleeing"] = True
                if cat_dist <= 1.2:
                    dmg = ent.get("atk", 3)
                    cat_prey["hp"] = cat_prey.get("hp", 1) - dmg
                    add_msg(f"👑 Grot Leader attacks {cat_prey.get('type','cat').replace('_',' ')} -{dmg} HP!")
                    if cat_prey.get("hp", 0) <= 0:
                        try: entities.remove(cat_prey)
                        except ValueError: pass
                        try: world.animals.remove(cat_prey)
                        except (ValueError, Exception): pass
                    return
                if cat_dist > 0:
                    dx=(cat_prey["x"]-ent["x"])/cat_dist; dy=(cat_prey["y"]-ent["y"])/cat_dist
                    for _ in range(move_tiles):
                        if math.hypot(ent["x"]-cat_prey["x"], ent["y"]-cat_prey["y"]) <= 1.2: break
                        ent["x"]+=dx; ent["y"]+=dy
                        do_render("👑 Grot Leader hunting cat...")
                        time.sleep(GROT_GRID_STEP_DELAY)
                    return
            berserk=ent.get("hp",1)<ent.get("max_hp",1)*0.5
            if berserk:
                # Berserk: charge player
                if dist_to_player>1.0 and dist_to_player>0:
                    dx=(player.x-ent["x"])/dist_to_player
                    dy=(player.y-ent["y"])/dist_to_player
                    for _ in range(move_tiles):
                        if math.hypot(ent["x"]-player.x, ent["y"]-player.y) <= 1.5:
                            break
                        ent["x"]+=dx; ent["y"]+=dy
                        do_render("👑 Grot Leader moving...")
                        time.sleep(GROT_GRID_STEP_DELAY)
                if math.hypot(ent["x"]-player.x,ent["y"]-player.y)<=1.5:
                    dmg=int(round(ent.get("atk",3)*1.5*player.armor_damage_multiplier()))
                    final,blocked=_apply_shield_block(player,dmg,msgs) if player.shield_type else (dmg,False)
                    if not blocked and final>0:
                        player.health=max(0,player.health-final)
                        add_msg(f"💥 Grot Leader (BERSERK) hits you -{final} HP!")
                        term.flash_red()
            else:
                # Normal: stay behind grots
                grots=[e for e in entities if e.get("type")=="grot" and e.get("hp",0)>0]
                if grots:
                    # Move to avg position of grots, on the far side from player
                    avg_x=sum(g["x"] for g in grots)/len(grots)
                    avg_y=sum(g["y"] for g in grots)/len(grots)
                    if dist_to_player>0:
                        away_x=avg_x+(avg_x-player.x)/dist_to_player*2
                        away_y=avg_y+(avg_y-player.y)/dist_to_player*2
                        d2=math.hypot(away_x-ent["x"],away_y-ent["y"])
                        if d2>0.5:
                            ent["x"]+=(away_x-ent["x"])/d2
                            ent["y"]+=(away_y-ent["y"])/d2
            return

        # Cats flee grots in grid mode too.
        if etype in ("cat", "young_cat"):
            nearest_grot = None; nearest_grot_dist = float('inf')
            for g in entities:
                if g is ent or g.get("type") not in ("grot", "grot_leader") or g.get("hp", 0) <= 0:
                    continue
                gd = math.hypot(g["x"]-ent["x"], g["y"]-ent["y"])
                if gd < nearest_grot_dist:
                    nearest_grot = g; nearest_grot_dist = gd
            if nearest_grot and nearest_grot_dist <= 12.0:
                ent["fleeing"] = True
                if nearest_grot_dist > 0:
                    dx=(ent["x"]-nearest_grot["x"])/nearest_grot_dist; dy=(ent["y"]-nearest_grot["y"])/nearest_grot_dist
                    for _ in range(move_tiles):
                        ent["x"]+=dx; ent["y"]+=dy
            return

        # Fleeing prey
        if ent.get("fleeing") and etype not in ("grot","grot_leader","cat"):
            # Check squirrel near tree
            if etype in ("squirrel","young_squirrel"):
                for (cx,cy),cl in world.clusters.items():
                    if cl.get("real_item","")=="wood" and math.hypot(cx-ent["x"],cy-ent["y"])<=1.5:
                        ent["_in_tree"]=1
                        add_msg(f"🐿️ Squirrel dashes up a tree!")
                        return
            if dist_to_player>0:
                dx=(ent["x"]-player.x)/dist_to_player; dy=(ent["y"]-player.y)/dist_to_player
                for _ in range(move_tiles):
                    ent["x"]+=dx; ent["y"]+=dy
            return

        # Grot: approach and attack
        if etype=="grot":
            ent_fleeing=ent.get("fleeing") and ent.get("hp",1)<ent.get("max_hp",1)*0.5
            # Check grot leader grab mechanic
            if ent_fleeing:
                leaders=[e for e in entities if e.get("type")=="grot_leader" and e.get("hp",0)>0]
                if leaders and random.random()<0.65:
                    ent["_grid_shield"]=True
                    add_msg(f"👹 Grot Leader grabs fleeing grot as a shield!")
                    if random.random()<0.5:
                        ent["_grid_shield"]=False
                        if dist_to_player>0:
                            ent["x"]+=(ent["x"]-player.x)/dist_to_player
                            ent["y"]+=(ent["y"]-player.y)/dist_to_player
                        add_msg(f"👹 Grot breaks free and flees!")
                    return
                if dist_to_player>0:
                    ent["x"]+=(ent["x"]-player.x)/dist_to_player
                    ent["y"]+=(ent["y"]-player.y)/dist_to_player
                return
            cat_prey = None; cat_dist = float('inf')
            for prey in entities:
                if prey is ent or prey.get("type") not in ("cat", "young_cat") or prey.get("hp", 0) <= 0:
                    continue
                pd = math.hypot(prey["x"]-ent["x"], prey["y"]-ent["y"])
                if pd <= 10.0 and pd < cat_dist:
                    cat_prey = prey; cat_dist = pd
            if cat_prey:
                cat_prey["fleeing"] = True
                if cat_dist <= 1.2:
                    dmg = ent.get("atk", 2)
                    cat_prey["hp"] = cat_prey.get("hp", 1) - dmg
                    add_msg(f"👹 Grot attacks {cat_prey.get('type','cat').replace('_',' ')} -{dmg} HP!")
                    if cat_prey.get("hp", 0) <= 0:
                        add_msg("💀 Cat killed by grot!")
                        try: entities.remove(cat_prey)
                        except ValueError: pass
                        try: world.animals.remove(cat_prey)
                        except (ValueError, Exception): pass
                    return
                if cat_dist > 0:
                    dx=(cat_prey["x"]-ent["x"])/cat_dist; dy=(cat_prey["y"]-ent["y"])/cat_dist
                    travel = min(float(move_tiles), max(0.0, cat_dist - 1.0))
                    remaining = travel
                    while remaining > 0:
                        step = min(1.0, remaining)
                        ent["x"] += dx * step; ent["y"] += dy * step
                        remaining -= step
                        do_render("👹 Grot hunting cat...")
                        time.sleep(GROT_GRID_STEP_DELAY)
                    return
            if dist_to_player>1.5 and dist_to_player>0:
                dx=(player.x-ent["x"])/dist_to_player; dy=(player.y-ent["y"])/dist_to_player
                # Stop next to the player rather than overshooting and
                # oscillating through the same rounded grid cell.
                travel = min(float(move_tiles), max(0.0, dist_to_player - 1.0))
                remaining = travel
                while remaining > 0:
                    step = min(1.0, remaining)
                    ent["x"] += dx * step
                    ent["y"] += dy * step
                    remaining -= step
                    dist_to_player = math.hypot(ent["x"]-player.x, ent["y"]-player.y)
                    do_render("👹 Grot moving...")
                    time.sleep(GROT_GRID_STEP_DELAY)
            if dist_to_player<=1.5:
                # Attack player
                dmg=int(round(ent.get("atk",2)*player.armor_damage_multiplier()))
                final_dmg,blocked=_apply_shield_block(player,dmg,msgs) if player.shield_type and (player.combat and player.combat.get("blocking")) else (dmg,False)
                if not blocked and final_dmg>0:
                    if player.wearing:
                        player.armor_dur-=final_dmg
                        if player.armor_dur<=0: player.wearing=None; player.armor_dur=0; add_msg("💥 Armor broke!")
                    player.health=max(0,player.health-final_dmg)
                    add_msg(f"💥 Grot hits you -{final_dmg} HP!")
                    term.flash_red()
            return

        # Generic prey: flee or mark fleeing
        vm=ent.get("vision_max", ANIMAL_DEFS.get(etype,{}).get("vision_max",5))
        if dist_to_player<vm:
            ent["fleeing"]=True
        if ent.get("fleeing") and dist_to_player>0:
            dx=(ent["x"]-player.x)/dist_to_player; dy=(ent["y"]-player.y)/dist_to_player
            for _ in range(move_tiles):
                ent["x"]+=dx; ent["y"]+=dy

    # ---- Main grid loop ----
    do_render()

    while True:
        if player.health<=0:
            add_msg("💀 You died in the grid!")
            try:
                player._grid_death = True
            except Exception: pass
            break

        live = [e for e in entities if e.get("hp",0)>0]
        hostile_live = [e for e in live if e.get("atk",0)>0 or e.get("type") in ("grot","grot_leader")]
        if not hostile_live and not initial_targets:
            add_msg("✅ No more threats. Exiting grid mode.")
            break

        # The grid window is centered on the player every render, so it
        # already "shifts" when the player walks toward the edge. Only
        # exit grid mode when EVERY live target (grot OR any other animal
        # pulled into the fight) is at least 20 tiles (Chebyshev distance)
        # from the player — that way a 3-tile-edge nudge doesn't kick you
        # out of combat, and hunting non-grot animals works correctly.
        nearest_target_dist = None
        for e in entities:
            if e.get("hp", 0) <= 0:
                continue
            # Only the things you're actually fighting keep you in grid mode:
            # the animals/grots you engaged (initial targets) or any hostile.
            is_target = (id(e) in _initial_ids or id(e) in _engaged_ids
                         or e.get("atk", 0) > 0 or e.get("type") in ("grot", "grot_leader"))
            if not is_target:
                continue
            ptx, pty = _world_tile(player.x, player.y)
            d = max(abs(int(round(e["x"])) - ptx),
                    abs(int(round(e["y"])) - pty))
            if nearest_target_dist is None or d < nearest_target_dist:
                nearest_target_dist = d

        if nearest_target_dist is None or nearest_target_dist >= 20:
            add_msg("⬛ Out of range (20+ tiles from any target) — exiting grid mode.")
            try: player.flee_until = time.time() + 6.0
            except Exception: pass
            break

        if player_energy <= 0:
            add_msg(f"⚡ Energy spent — grots take their big move.")
            grots_turn()
            dead=remove_dead(); resolve_kills(dead)
            round_num+=1
            player_energy=_grid_calc_player_energy(player)
            add_msg(f"🔄 Round {round_num} — Energy: {player_energy}")
            log_lines.extend(msgs[-4:])
            do_render()
            msgs.clear()
            continue

        # Animated input wait: re-render frequently for flashing effect
        key = None
        last_anim = 0.0
        while key is None:
            now_a = time.time()
            if now_a - last_anim >= 0.05:
                last_anim = now_a
                do_render()
            key = term.get_key(0.04)
            if player.health <= 0: break
        if player.health <= 0: continue
        if key is None: continue

        moved=False
        if key == "UP":
            player.y -= 1; moved=True; player_energy-=8; last_move_time=time.time()
        elif key == "DOWN":
            player.y += 1; moved=True; player_energy-=8; last_move_time=time.time()
        elif key == "LEFT":
            player.x -= 1; moved=True; player_energy-=8; last_move_time=time.time()
        elif key == "RIGHT":
            player.x += 1; moved=True; player_energy-=8; last_move_time=time.time()
        elif key in ("e","E","s","S","a","A"):
            player_strike()
            log_lines.extend(msgs[-2:]); msgs.clear()
        elif key in ("t","T"):
            player_throw()
            do_render()
            log_lines.extend(msgs[-2:]); msgs.clear()
        elif key in ("b","B"):
            player_block()
            log_lines.extend(msgs[-2:]); msgs.clear()
        elif key in ("p","P","\r","\n"):
            # Pass — end player turn
            player_energy=0
        elif key in ("q","Q"):
            # Quitting grid mode: enemies get one free turn (they strike),
            # then you exit with a 10-second grace window to escape.
            add_msg("🏃 You break off — enemies get one parting strike!")
            for ent in list(entities):
                if ent.get("hp",0) > 0:
                    entity_turn(ent)
            dead=remove_dead(); resolve_kills(dead)
            try:
                player.flee_until = time.time() + 10.0
            except Exception:
                pass
            # Give grots a 10s flee/ignore window so they don't immediately re-trigger grid mode
            now_q = time.time()
            for ent in entities:
                if ent.get("type") in ("grot","grot_leader"):
                    ent["flee_grace_until"] = now_q + 10.0
            add_msg("⬛ Exiting grid mode. 10s grace — RUN!")
            do_render()
            _resume_paused_crafting(player)
            break

        if moved:
            # Trees cost extra energy, rocks cost more; both are walkable.
            extra_cost = 0
            terrain_label = None
            px_i, py_i = _world_tile(player.x, player.y)
            for (cx,cy),cl in world.clusters.items():
                item=cl.get("real_item","")
                if item not in ("wood","rock"): continue
                for di in range(2):
                    for dj in range(2):
                        if px_i==cx+di and py_i==cy+dj:
                            if item == "wood":
                                extra_cost = max(extra_cost, int(round(8*0.3)))  # +30% => 1.3x total
                                terrain_label = "🌲 Pushing through trees (x1.3 energy)"
                            else:
                                extra_cost = max(extra_cost, int(round(8*0.5)))  # +50% => 1.5x total
                                terrain_label = "🪨 Climbing over rocks (x1.5 energy)"
            if extra_cost:
                player_energy -= extra_cost
                add_msg(terrain_label)
                log_lines.extend(msgs[-1:]); msgs.clear()
            # Grots wait until the player's energy is spent; no free move after each player action.

        log_lines=log_lines[-12:]

    # Restore the "fleeing" flag for any prey that never actually saw or
    # engaged the player. Bystander squirrels shouldn't bolt across the map
    # just because a grot fight happened nearby.
    try:
        for e in entities:
            if id(e) in _initial_ids:
                continue
            if e.get("type") in ("grot", "grot_leader"):
                continue
            took_damage = e.get("hp", 0) < e.get("max_hp", e.get("hp", 0))
            if took_damage:
                continue
            e["fleeing"] = _pre_flee.get(id(e), False)
    except Exception:
        pass

    # Sync player world position
    add_msg(f"Grid mode ended. Round {round_num}.")
    return msgs


def start_turn_based_combat(player, world, attackers, msg):
    """Initialize a simple turn-based combat session stored on player.combat.
    attackers: list of animal dicts (references into world.animals)
    """
    # Build combat enemy snapshots
    enemies = []
    for a in attackers:
        enemies.append({
            "ref": a,
            "type": a.get("type"),
            "hp": a.get("hp", 1),
            "atk": a.get("atk", 0),
            "def": a.get("def", 0),
            "speed_cpm": a.get("speed_cpm", 10),
            "fleeing": a.get("fleeing", False),
            "id": id(a),
        })
    # compute initiatives per user design:
    # Each monster: rand(1..40) + speed * 1.5
    for e in enemies:
        e["init"] = random.randint(1, 40) + int(round(e["speed_cpm"] * 1.5))
    # Player: rand(1..40) + (20 - def)
    player_init = random.randint(1, 40) + max(0, 20 - player.armor_defense())
    avg_enemy_init = float(max(1, sum(e["init"] for e in enemies) / max(1, len(enemies))))

    # Determine who goes first and how many segments the active side gets
    if player_init >= avg_enemy_init:
        # Player goes first. Number of player segments = floor(player_init / avg_enemy_init), capped to max 3
        segs = max(1, int(player_init // avg_enemy_init))
        player_turns = min(3, segs)
        enemy_segments = 1
        player_first = True
    else:
        # Enemies go first. They may act multiple times before player (symmetric rule)
        segs = max(1, int(avg_enemy_init // max(1, int(player_init))))
        enemy_segments = min(3, segs)
        player_turns = 1
        player_first = False

    player.combat = {
        "enemies": enemies,
        "player_init": player_init,
        "avg_enemy_init": avg_enemy_init,
        "player_turns": player_turns,
        "enemy_segments": enemy_segments,
        "player_ap": 5,   # action points remaining for current player turn segment
        "blocking": False,
        "player_first": player_first,
    }
    player.in_combat = True
    snd_cb = getattr(player, "sound", None)
    if snd_cb and getattr(snd_cb, "enabled", False): snd_cb.start_combat_bgm()
    # Pause any active crafting / gather-all so combat doesn't tick them forward
    now_pc = time.time()
    for t in player.active_tasks:
        if "paused_remaining" not in t:
            t["paused_remaining"] = max(0, int(t["end"] - now_pc))
    ga = getattr(player, "gather_all", None)
    if ga and "paused_remaining" not in ga:
        ga["paused_remaining"] = max(0, int(ga["end"] - now_pc))
        if snd_cb and getattr(snd_cb, "enabled", False):
            snd_cb.stop_gather()
    msg.append(f"⚔️ Turn-based combat started! You face {len(enemies)} enemy(ies). AP per player segment: 5.\nYou will act {'first' if player_first else 'after enemies'}; player segments: {player_turns}, enemy segments: {enemy_segments}.")
    # Brief user-facing combat help (commands and short effects)
    msg.append("🛈 Combat commands: a/attack/s/strike — Strike (cost 3 AP). t/throw — Throw (cost 5 AP). block — Brace to block (cost 3 AP). flee — Attempt to flee (cost 2 AP, grants 5s safe window but enemies may hit once). pass/end — End your segment and let enemies act. status — Show combat status.")
    if not player_first:
        msg.append("⚔️ Enemies strike first!")
        for seg in range(enemy_segments):
            for e in enemies:
                if e["hp"] <= 0:
                    continue
                _enemy_attack_player(player, e, msg)
                if player.health <= 0:
                    break
            if player.health <= 0:
                break


def _resume_paused_crafting(player):
    """Resume any crafting (and gather-all) that was paused."""
    now = time.time()
    for t in player.active_tasks:
        if "paused_remaining" in t:
            t["end"] = now + t["paused_remaining"]
            del t["paused_remaining"]
    ga = getattr(player, "gather_all", None)
    if ga and "paused_remaining" in ga:
        ga["end"] = now + ga["paused_remaining"]
        del ga["paused_remaining"]
    snd = getattr(player, "sound", None)
    if snd and getattr(snd, "enabled", False):
        if player.active_tasks and not any("paused_remaining" in t for t in player.active_tasks):
            station = player.active_tasks[0].get("station")
            snd.play_craft(station if isinstance(station, str) else (station[0] if station else None))
        if ga and "paused_remaining" not in ga and ga.get("item"):
            snd.loop_gather(ga.get("item"))


def _end_combat_if_clear(player, msg):
    """If all enemies are defeated OR all remaining are fleeing grots, exit combat."""
    if not player.in_combat or not player.combat:
        return False
    live = [e for e in player.combat.get("enemies", []) if e["hp"] > 0]
    if not live:
        msg.append("✅ All enemies defeated! Combat ended.")
        _resume_paused_crafting(player)
        _snd_ce = getattr(player, "sound", None)
        if _snd_ce and getattr(_snd_ce, "enabled", False): _snd_ce.stop_combat_bgm()
        player.in_combat = False
        player.combat = None
        return True
    # If every live enemy is a grot that is fleeing, end turn-based combat.
    if all((e.get("ref") or {}).get("type") == "grot" and (e.get("ref") or {}).get("fleeing") for e in live):
        msg.append("🏃 The grot(s) fled! Combat ended — chase them down to attack again.")
        _resume_paused_crafting(player)
        _snd_cf = getattr(player, "sound", None)
        if _snd_cf and getattr(_snd_cf, "enabled", False): _snd_cf.stop_combat_bgm()
        player.in_combat = False
        player.combat = None
        return True
    return False


def _apply_shield_block(player, final_dmg, msg):
    """Apply shield block to incoming damage. Returns final damage after shield.
    Depletes shield durability. Returns (final_dmg, blocked_completely)."""
    if not player.shield_type or player.shield_dur_blocks <= 0 and player.shield_dur_absorb <= 0:
        return final_dmg, False
    sdef = SHIELD_DEFS.get(player.shield_type)
    if not sdef:
        return final_dmg, False
    # Complete block roll
    if random.random() < sdef["complete_block_pct"]:
        player.shield_dur_blocks -= 1
        player.shield_dur_absorb -= final_dmg
        _check_shield_break(player, msg)
        return 0, True
    # Partial miss (no block at all)
    if random.random() < sdef["partial_miss_pct"]:
        return final_dmg, False
    # Partial reduction
    lo, hi = sdef["partial_reduce_range"]
    red = random.randint(lo, hi)
    reduced = max(0, int(round(final_dmg * (1 - red / 100.0))))
    absorbed = final_dmg - reduced
    player.shield_dur_blocks -= 1
    player.shield_dur_absorb -= absorbed
    _check_shield_break(player, msg)
    msg.append(f"🛡️ Shield reduced blow by {red}%!")
    return reduced, False


def _check_shield_break(player, msg):
    if not player.shield_type: return
    sdef = SHIELD_DEFS.get(player.shield_type, {})
    broke = False
    if player.shield_dur_blocks <= 0:
        broke = True
    elif player.shield_dur_absorb <= 0:
        broke = True
    if broke:
        msg.append(f"💥 {player.shield_type.replace('_',' ').title()} broke!")
        player.inventory[player.shield_type] = max(0, player.inventory.get(player.shield_type, 0) - 1)
        player.shield_type = None
        player.shield_dur_blocks = 0
        player.shield_dur_absorb = 0


_g_world = None  # module-level world reference set by main game loop

def _enemy_attack_player(player, enemy, msg):
    # If player is inside a house, redirect monster attack to the house instead
    if getattr(player, "inside_house_id", None) and _g_world is not None:
        for _hh in _g_world.houses:
            if _hh["id"] == player.inside_house_id and _hh.get("hp",0) > 0:
                raw = enemy.get("atk", 2)
                actual = _house_take_damage(_hh, raw)
                etype = enemy.get("type","enemy").replace("_"," ").title()
                msg.append(f"💥 {etype} attacks your {_hh['type'].replace('_',' ')}! -{actual} HP ({_hh['hp']} left)")
                return
    # Lone fleeing grot just runs — skip attack
    try:
        ref = enemy.get("ref") or {}
        if ref.get("type") == "grot" and ref.get("fleeing") and ref.get("flee_grace_until"):
            return
    except Exception:
        pass
    # compute raw damage
    atk = enemy.get("atk", 0)
    if atk <= 0: return
    base_dmg = int(round(atk))
    # apply armor multiplier
    final = int(round(base_dmg * player.armor_damage_multiplier()))
    # handle shield block
    if player.shield_type and (player.combat and player.combat.get("blocking")):
        final, fully_blocked = _apply_shield_block(player, final, msg)
        if fully_blocked:
            return
    elif player.combat and player.combat.get("blocking"):
        # legacy block (no shield) - 50% full block
        if random.random() < 0.5:
            msg.append("🛡️ You blocked the attack completely!")
            return
        if random.random() < 0.6:
            red = random.randint(50,70)
            final = int(round(final * (1 - red/100.0)))
            msg.append(f"🛡️ You partially blocked ({red}% reduced).")
    if final > 0:
        if player.wearing:
            player.armor_dur -= final
            if player.armor_dur <= 0:
                player.wearing = None
                player.armor_dur = 0
                msg.append("💥 Armor broke!")
        player.note_damage_cause(f"{enemy.get('type').replace('_',' ').title()} attack")
        player.health = max(0, player.health - final)
        msg.append(f"💥 {enemy.get('type').replace('_',' ').title()} hits you -{final} HP")


def handle_combat_command(player, world, act, arg, msg, term=None):
    """Process player commands while in combat. Returns True if command handled."""
    if not player.in_combat or not player.combat:
        return False
    if act in ("pause","resume","help"):
        return False
    # Allow utility commands to pass through to the main dispatcher while in combat
    PASSTHROUGH = {"equip","unequip","wear","remove","inv","inventory","quests","help",
                   "recipes","explain","stats","achievements","stat","bandage","bandages"}
    if act in PASSTHROUGH:
        return False
    state = player.combat
    enemies = state["enemies"]
    # helper to find a live enemy by nearest
    live = [e for e in enemies if e["hp"] > 0]
    # Auto-pass if the player can't afford any action this segment
    if state["player_ap"] < 2:
        msg.append("⚡ Out of AP — auto-passing segment.")
        act = "pass"
    # nested helper: present enemy selection menu if multiple targets
    def choose_target():
        if not live:
            return None
        if len(live) == 1:
            return live[0]
        # Build menu
        lines = ["🎯 Choose a target", "─" * TERM_WIDTH]
        for i, e in enumerate(live, 1):
            lines.append(f"  {i}. {e['type'].replace('_',' ').title():<18} | HP:{e['hp']} | @{int(e['ref']['x'])},{int(e['ref']['y'])}")
        lines.append("")
        lines.append("  Press number to select target, Enter to auto-target nearest.")
        lines.append("  Hotkeys: ',' previous, '.' next, TAB rotate")
        try:
            idx = 0
            term.show_menu(lines)
            while True:
                ch = term.get_key_no_flush(0.5)
                if not ch:
                    continue
                if ch in ('\r','\n'):
                    return live[idx]
                if ch and ch.isdigit():
                    sel = int(ch)
                    if 1 <= sel <= len(live):
                        return live[sel-1]
                if ch == ',':
                    idx = (idx - 1) % len(live)
                    term.show_menu(lines)
                    continue
                if ch == '.' or ch == '\t':
                    idx = (idx + 1) % len(live)
                    term.show_menu(lines)
                    continue
        except Exception:
            # fallback: nearest
            return min(live, key=lambda ee: math.hypot(ee['ref']['x']-player.x, ee['ref']['y']-player.y))
    if not live:
        msg.append("✅ All enemies defeated!")
        _resume_paused_crafting(player)
        _snd_cd = getattr(player, "sound", None)
        if _snd_cd and getattr(_snd_cd, "enabled", False): _snd_cd.stop_combat_bgm()
        player.in_combat = False; player.combat = None
        return True

    # Attack (strike) - costs 3 AP, requires spear
    if act in ("a","attack","s","strike"):
        if state["player_ap"] < 3:
            msg.append("⚡ Not enough AP to strike (3).")
            return True
        if not player.spear_type or player.spear_dur <= 0:
            msg.append("❌ No spear equipped to strike.")
            return True
        # choose target (menu if more than one)
        target = choose_target()
        if not target:
            msg.append("❌ No valid target.")
            return True
        sdef = SPEAR_DEFS.get(player.spear_type, {})
        dmg = sdef.get("strike", 0) * (2 if player.inventory.get("poison",0)>0 else 1)
        target["hp"] -= dmg
        # Grots flash red when hit in grid mode; other targets flash yellow
        if target.get("type","") in ("grot","grot_leader"):
            try: term.flash_red()
            except Exception: pass
        _flash_hit(target.get("type",""))
        # Sync HP back to world animal reference so damage persists across combats
        try:
            target["ref"]["hp"] = target["hp"]
            # Any hit spooks the animal — they should try to flee.
            if target["hp"] > 0:
                target["ref"]["fleeing"] = True
        except Exception: pass
        player.spear_dur -= sdef.get("strike_cost", dmg)
        state["player_ap"] -= 3
        if player.inventory.get("poison",0)>0:
            player.inventory["poison"] -= 1
        msg.append(f"⚔️ You strike {target['type'].replace('_',' ').title()} -{dmg} HP ({max(0,target['hp'])} left)")
        if player.spear_dur <= 0:
            player.inventory[player.spear_type] = max(0, player.inventory.get(player.spear_type,0)-1)
            msg.append(f"💥 {player.spear_type.replace('_',' ').title()} broke!")
            player.spear_type = None; player.spear_dur = 0
        # check kill
        if target["hp"] <= 0:
            # resolve kill against world refs
            try:
                resolve_animal_kill(player, world, target["ref"], msg)
            except Exception:
                pass
        # If all enemies are now defeated, exit combat immediately
        _end_combat_if_clear(player, msg)
        return True

    # Throw - costs 5 AP (use existing throw logic if available)
    if act in ("t","throw"):
        if state["player_ap"] < 5:
            msg.append("⚡ Not enough AP to throw (5).")
            return True
        if not player.spear_type or player.spear_dur <= 0 or player.inventory.get(player.spear_type,0) <= 0:
            msg.append("❌ No spear equipped to throw.")
            return True
        sdef = SPEAR_DEFS.get(player.spear_type, {})
        if sdef.get("throw", 0) <= 0:
            msg.append("❌ This weapon can only be used in melee.")
            return True
        target = choose_target()
        if not target:
            msg.append("❌ No valid target.")
            return True
        dist = math.hypot(target["ref"]["x"]-player.x, target["ref"]["y"]-player.y)
        if term is not None:
            _show_spear_tutorial_if_first(term, player, player.spear_type)
            hit_zone, cancelled = run_spear_minigame(term, player, target.get("type","deer"), dist, player.spear_type)
        else:
            miss_chance = min(0.95, max(0.0, math.ceil(dist) * sdef.get("miss_pct", 0.1)))
            hit_zone = "miss" if random.random() < miss_chance else "body"
            cancelled = False
        if cancelled:
            msg.append("🛑 Throw cancelled. Spear held.")
            return True
        state["player_ap"] -= 5
        target["ref"]["fleeing"] = True
        if hit_zone == "miss":
            player.spear_dur -= min(sdef.get("throw_cost", 0), player.spear_dur)
            msg.append("💨 Threw spear — MISSED!")
        else:
            hit_mult = {"head":1.5,"body":1.0,"graze":0.5,"near_miss":0.25}.get(hit_zone, 0.0)
            poison_mult = 2 if player.spear_poison_throw else 1
            dmg = max(1, int(sdef.get("throw", 0) * hit_mult * poison_mult))
            target["hp"] -= dmg
            _flash_hit(target.get("type",""))
            try: target["ref"]["hp"] = target["hp"]
            except Exception: pass
            player.spear_dur -= min(sdef.get("throw_cost", 0), player.spear_dur)
            if player.spear_type == "ice_spear": player.spear_dur = 0
            if player.spear_poison_throw:
                player.spear_poison_throw = False; player.spear_poison_strikes = 0
            zone_desc = {"head":"HEAD HIT","body":"body hit","graze":"graze","near_miss":"near miss"}.get(hit_zone,"hit")
            msg.append(f"🗡️ Spear throw — {zone_desc}! {target['type'].replace('_',' ').title()} -{dmg} HP ({max(0,target['hp'])} left)")
        if player.spear_dur <= 0:
            player.inventory[player.spear_type] = max(0, player.inventory.get(player.spear_type,0)-1)
            msg.append(f"💥 {player.spear_type.replace('_',' ').title()} broke!")
            player.spear_type = None; player.spear_dur = 0
        if target["hp"] <= 0:
            try:
                resolve_animal_kill(player, world, target["ref"], msg)
            except Exception:
                pass
        _end_combat_if_clear(player, msg)
        return True

    # Block - costs 3 AP
    if act == "block":
        if state["player_ap"] < 3:
            msg.append("⚡ Not enough AP to block (3).")
            return True
        state["player_ap"] -= 3
        state["blocking"] = True
        msg.append("🛡️ You brace to block incoming attacks this enemy segment.")
        return True

    # Flee - costs 2 AP and ends combat; 50% chance enemies hit once
    if act == "flee":
        if state["player_ap"] < 2:
            msg.append("⚡ Not enough AP to flee (2).")
            return True
        state["player_ap"] -= 2
        _resume_paused_crafting(player)
        has_grot = any((e.get("ref") or {}).get("type") in ("grot", "grot_leader") for e in live)
        if has_grot:
            player._combat_music_delay_until = time.time() + 10.0
        _snd_fl = getattr(player, "sound", None)
        if _snd_fl and getattr(_snd_fl, "enabled", False): _snd_fl.stop_combat_bgm()
        player.in_combat = False
        player.combat = None
        player.flee_until = time.time() + 5.0
        # enemies have 50% chance to hit once
        for e in live:
            if random.random() < 0.5:
                _enemy_attack_player(player, e, msg)
        msg.append("🏃 You fled the battle for 10s.")
        return True

    # Pass / end segment: let enemies act for this segment
    if act in ("pass","end","done","p"):
        # enemies act
        state["blocking"] = False
        for e in [en for en in enemies if en["hp"]>0]:
            _enemy_attack_player(player, e, msg)
        # If enemies were all defeated mid-pass, exit cleanly
        if _end_combat_if_clear(player, msg):
            return True
        # reset player AP for next player segment and decrement player_turns
        player.combat["player_turns"] -= 1
        if player.combat["player_turns"] <= 0:
            # combat rounds complete: re-evaluate initiatives for next cycle
            _resume_paused_crafting(player)
            player.in_combat = False
            player.combat = None
            msg.append("🏁 Combat ended.")
        else:
            player.combat["player_ap"] = 5
            msg.append(f"🔁 Next player segment: {player.combat['player_turns']} remaining.")
        return True

    # Status
    if act in ("status","st"):
        out = [f"🛡️ In Combat — HP: {int(player.health)} / {int(player.max_health)}", f"AP: {state['player_ap']} | Segments left: {state['player_turns']}"]
        for e in state['enemies']:
            out.append(f" - {e['type']} HP:{e['hp']}")
        for line in out: msg.append(line)
        return True

    # other commands not handled in combat
    msg.append("❌ In combat: use 'a/attack', 't/throw', 'block', 'flee', 'pass', or 'status'.")
    return True


def eat_unknown_item(player, inv_key, msg):
    inv_entry = player.inventory[inv_key]
    if inv_entry["qty"] < 1 or not inv_entry["items"]:
        msg.append("❌ Nothing in that stack."); return
    real = inv_entry["items"].pop(random.randint(0, len(inv_entry["items"])-1))
    inv_entry["qty"] -= 1
    if inv_entry["qty"] <= 0: del player.inventory[inv_key]
    eff = food_effects.get(real, {"hunger":5})
    nh = eff.get("health",0); nn = eff.get("hunger",0); ne = eff.get("energy",0); nt = eff.get("thirst",0)
    mystery_msg = False
    if eff.get("risk") == "mystery_mushroom":
        mystery_msg = True
        mm = roll_mystery_mushroom()
        if random.random() < mm["risk_pct"] / 100.0:
            nh = 0
            player.health = max(0, player.health - mm["damage"])
            msg.append(f"☠️ Mystery mushroom backfired! -{mm['damage']} HP.")
        else:
            nh = mm["health"]
            msg.append(f"✅ Mystery mushroom was safe! +{nh}❤️ +{nn}🍽️ +{ne}⚡ +{nt}💧 +{mm['fatigue']}😴")
        nn = mm["hunger"]
        ne = mm["energy"]
        nt = mm["thirst"]
        if mm["fatigue"]:
            player.fatigue = min(MAX_STAT_CAP, player.fatigue + mm["fatigue"])
    elif eff.get("risk") == "mystery_moss":
        if random.random() < 0.5: nh += 50
        else: nh -= random.randint(10,50)
    elif eff.get("risk_min"):
        if random.random() < random.uniform(eff["risk_min"],eff["risk_max"]): nh -= eff.get("risk_dmg",0)
    player.hunger = min(MAX_STAT_CAP, max(0, player.hunger+nn))
    player.energy = min(MAX_STAT_CAP, max(0, player.energy+ne))
    player.thirst = min(MAX_STAT_CAP, max(0, player.thirst+nt))
    player.health = min(MAX_STAT_CAP, max(0, player.health+nh))
    if not mystery_msg:
        if nh <= -25:      msg.append("🤢 You ate the unknown item and feel terribly ill!")
        elif nh < 0:       msg.append("😕 You ate the unknown item. You feel a bit sick.")
        elif nn > 30 or ne > 30: msg.append("😋 You ate the unknown item. You feel well nourished!")
        elif nn > 10 or ne > 10: msg.append("👍 You ate the unknown item. It was edible enough.")
        else:              msg.append("🤔 You ate the unknown item. You feel... odd.")

def do_inspect_inventory(player, arg, msg, refresh_fn):
    if getattr(player, "inspect_pending", None):
        msg.append("⏳ Already inspecting — please wait."); return True
    found_key = find_unknown_inv_key(player, arg)
    if not found_key: return False
    inv_entry = player.inventory[found_key]
    if not inv_entry.get("items"):
        msg.append("❌ No items in that stack."); return True
    tries = inv_entry.get("inspect_tries", 0)
    if tries >= MAX_INSPECTIONS:
        msg.append(f"⚠️ Max inspections reached ({MAX_INSPECTIONS}/{MAX_INSPECTIONS}). Cannot inspect further."); return True
    has_lens = player.inventory.get("id_lens", 0) > 0
    if not has_lens and player.energy < INSPECT_COST:
        msg.append(f"⚡ Not enough energy — need {INSPECT_COST}, have {int(player.energy)}. (Or buy an ID Lens)"); return True
    # --- Schedule a non-blocking inspection ---
    player.inspect_pending = {"kind": "inv", "key": found_key, "end": time.time() + INSPECT_TIME}
    msg.append("🔍 Inspecting... (3 seconds)")
    snd_inv = getattr(player, "sound", None)
    if snd_inv and getattr(snd_inv, "enabled", False): snd_inv.play_inspect()
    return True

def _finalize_inspect(player, world, msg):
    ip = getattr(player, "inspect_pending", None)
    if not ip or time.time() < ip["end"]:
        return
    if ip["kind"] == "inv":
        key = ip["key"]
        inv_entry = player.inventory.get(key)
        if not inv_entry or not inv_entry.get("items"):
            player.inspect_pending = None; return
        has_lens = player.inventory.get("id_lens", 0) > 0
        if has_lens:
            player.inventory["id_lens"] -= 1
            real = inv_entry["items"].pop(0)
            inv_entry["qty"] -= 1
            if inv_entry["qty"] <= 0: del player.inventory[key]
            player.inventory[real] = player.inventory.get(real, 0) + 1
            msg.append(f"🔍 Lens used! It's {display_item_name(real)}.")
        else:
            player.energy -= INSPECT_COST
            real = inv_entry["items"][0]
            tries = inv_entry.get("inspect_tries", 0)
            inv_entry["inspect_tries"] = tries + 1
            chance = min(1.0, IDENTIFY_CHANCES.get(real, 0.0) + player.inventory.get("textbook", 0) * 0.1)
            if random.random() <= chance:
                inv_entry["items"].pop(0); inv_entry["qty"] -= 1
                if inv_entry["qty"] <= 0: del player.inventory[key]
                player.inventory[real] = player.inventory.get(real, 0) + 1
                msg.append(f"✅ Identified! It's {display_item_name(real)}. ({inv_entry.get('inspect_tries',1)}/{MAX_INSPECTIONS})")
            else:
                msg.append(f"❌ Failed to identify. ({inv_entry.get('inspect_tries',1)}/{MAX_INSPECTIONS})")
    elif ip["kind"] == "cluster":
        cx, cy = ip["cx"], ip["cy"]
        cl = world.clusters.get((cx, cy))
        if cl and not cl["is_identified"]:
            # Quick-tutorial override: force success on the 5th attempt.
            qt_force = qt_force_inspect_outcome(player)
            if qt_force is not None:
                if player.energy < INSPECT_COST:
                    msg.append("⚡ Not enough energy (need 5).")
                else:
                    player.energy -= INSPECT_COST
                    cl["inspection_attempts"] += 1
                    if qt_force:
                        cl["is_identified"] = True
                        cl["name"] = cl["real_item"].replace("_", " ").title()
                        msg.append(f"✅ Identified as {cl['name']}! ({cl['inspection_attempts']}/{MAX_INSPECTIONS})")
                        player._qt_last_inspect_success = True
                    else:
                        msg.append(f"❌ Failed. ({cl['inspection_attempts']}/{MAX_INSPECTIONS} attempts used)")
                        player._qt_last_inspect_success = False
                    player._qt_inspect_finished = True
            else:
                ok, m = world.inspect_cluster(player, cl)
                msg.append(m)
                if not ok and "Failed" in m:
                    player.total_inspect_failures = getattr(player, "total_inspect_failures", 0) + 1
                    if player.total_inspect_failures == 10 and getattr(player, "textbooks_bought", 0) == 0:
                        msg.append("👴 Old Man: 'Buying a textbook is expensive (300 coins), but it can help by making inspects easier.'")
                if getattr(player, "qt_active", False) and getattr(player, "qt_step", "") == "inspect_berries":
                    player._qt_last_inspect_success = bool(ok)
                    player._qt_inspect_finished = True
    player.inspect_pending = None



# ==================== CRAFTING HELPER ====================
def resolve_any_berry(player, recipe):
    """
    For recipes that use 'any_berry', check if player has enough total berries.
    Returns (ok, missing_msg).
    """
    mats = recipe.get("mat", {})
    needed = mats.get("any_berry", 0)
    if needed == 0: return True, None
    have = player.count_any_berry()
    if have < needed:
        return False, f"❌ Missing: need {needed} berry (any type), have {have}"
    return True, None

# ==================== SAVE HELPERS ====================
def do_save(player, world, save_path, biome, dead=False, death_reason="", paused=False):
    """Serialize player + world state to save_path."""
    # Accumulate session playtime before saving, but do not count paused time.
    now_t = time.time()
    if not paused:
        player.total_playtime += now_t - player.session_start
    player.session_start = now_t
    save_inv = {}
    for k, v in player.inventory.items():
        if isinstance(v, dict):
            save_inv[k] = {"__unknown__": True, "qty": v.get("qty", 0),
                           "items": v.get("items", []), "inspect_tries": v.get("inspect_tries", 0)}
        else:
            save_inv[k] = v
    name = os.path.splitext(os.path.basename(save_path))[0].replace("_", " ")
    cur_biome = biome_at(player.x, player.y)
    data = {
        "meta": {
            "name": name,
            "biome": cur_biome,
            "debug": bool(getattr(player, "debug_mode", False)),
            "terminal_theme": getattr(player, "terminal_theme", "dark"),
            "graphics_mode": bool(getattr(player, "graphics_mode", False)),
            "graphics_adaptive": bool(getattr(player, "graphics_adaptive", False)),
            "show_commands": bool(getattr(player, "show_commands", True)),
            "last_played": time.time(),
            "health": player.health,
            "coins": player.coins,
            "total_playtime": player.total_playtime + max(0.0, time.time() - player.session_start),
            "points": player.points,
            "dead": dead,
            "death_reason": death_reason,
        },
        "player": {k: v for k, v in player.__dict__.items() if k not in ["inventory", "session_start", "sound"]},
        "player_inv": save_inv,
        "world": {
            "clusters": {f"{x}_{y}": v for (x, y), v in world.all_clusters_for_save().items()},
            "animals": world.all_animals_for_save(),
            "houses": world.houses,
        },
    }
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "w") as f:
        json.dump(data, f)


def delete_save(save_name):
    """Delete a save file from SAVES_DIR."""
    save_path = os.path.join(SAVES_DIR, save_name + ".json")
    if os.path.exists(save_path):
        try:
            os.remove(save_path)
            return True, f"✅ Save '{save_name}' deleted."
        except Exception as e:
            return False, f"❌ Failed to delete: {e}"
    return False, f"❌ Save '{save_name}' not found."

def _ps_key():
    """
    Read one raw keypress from stdin.
    Returns 'UP', 'DOWN', 'ENTER', 'ESC', or a single printable character.
    Works on Linux/macOS (termios) and Windows (msvcrt).
    """
    if HAVE_TERMIOS:
        import tty as _tty, termios as _termios, select as _sel
        fd = sys.stdin.fileno()
        old = _termios.tcgetattr(fd)
        try:
            _tty.setraw(fd)
            ch = os.read(fd, 1).decode('utf-8', errors='ignore')
            if ch == '\x1b':
                rdy, _, _ = _sel.select([fd], [], [], 0.08)
                if rdy:
                    ch2 = os.read(fd, 1).decode('utf-8', errors='ignore')
                    if ch2 == '[':
                        rdy2, _, _ = _sel.select([fd], [], [], 0.08)
                        if rdy2:
                            ch3 = os.read(fd, 1).decode('utf-8', errors='ignore')
                            if ch3 == 'A': return 'UP'
                            if ch3 == 'B': return 'DOWN'
                return 'ESC'
            if ch in ('\r', '\n'):   return 'ENTER'
            if ch == '\x7f':         return 'BACKSPACE'
            if ch == '\x03':         raise KeyboardInterrupt
            if ch == '\x04':         raise EOFError
            return ch
        finally:
            _termios.tcsetattr(fd, _termios.TCSANOW, old)
    else:
        import msvcrt as _msvcrt
        ch = _msvcrt.getwch()
        if ch in ('\r', '\n'):  return 'ENTER'
        if ch == '\x03':        raise KeyboardInterrupt
        if ch == '\x00' or ch == '\xe0':
            ch2 = _msvcrt.getwch()
            if ch2 == 'H': return 'UP'
            if ch2 == 'P': return 'DOWN'
            return 'ESC'
        if ch == '\x08': return 'BACKSPACE'
        return ch


def _setup_audio_venv():
    """
    Install pygame for the current Python interpreter (no venv needed).
    Uses --user --only-binary=:all: so no C compiler is required on any platform.
    Falls back to a source build if the pre-built wheel fails.
    Returns True on success; prints the error and returns False on failure.
    """
    import subprocess, importlib, site as _site
    print("  🔧 Setting up audio... please wait...")
    sys.stdout.flush()

    # Inside a virtualenv --user is blocked; outside one it is fine
    in_venv = (hasattr(sys, "real_prefix") or
               (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix) or
               bool(os.environ.get("VIRTUAL_ENV")))
    user_flag = [] if in_venv else ["--user"]

    def _try_install(pkg, extra_flags=()):
        cmd = [sys.executable, "-m", "pip", "install", "--quiet",
               pkg] + list(user_flag) + list(extra_flags)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
            return r.returncode == 0, (r.stderr or r.stdout or "")
        except Exception as exc:
            return False, str(exc)

    # On Windows never attempt a source build — no MSVC / compiler guaranteed
    allow_source = sys.platform != "win32"

    # Try each candidate package; prefer pre-built wheel, fall back to source on non-Windows
    # pygame-ce (Community Edition) ships Python 3.14 wheels; pygame classic may not yet
    candidates = ["pygame", "pygame-ce"]
    ok = False
    err = ""
    for pkg in candidates:
        ok, err = _try_install(pkg, ["--only-binary=:all:"])
        if ok:
            break
        if allow_source:
            ok, err = _try_install(pkg)
            if ok:
                break

    if not ok:
        err_tail = err[-700:].strip()
        print(f"  ❌ Audio setup failed:\n{err_tail}")
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        if sys.platform == "win32":
            print(f"  ℹ️  No pre-built audio wheel found for Python {py_ver} on Windows.")
            print(f"     You can try running:  pip install pygame-ce")
        return False

    # If installed to user site-packages, make sure it is on sys.path
    if not in_venv:
        try:
            user_sp = _site.getusersitepackages()
            if user_sp and user_sp not in sys.path:
                sys.path.insert(0, user_sp)
        except Exception:
            pass

    try:
        global pygame, PYGAME_AVAILABLE, array
        pygame = importlib.import_module("pygame")
        from array import array as _arr
        array = _arr
        PYGAME_AVAILABLE = True
        print("  ✅ Audio ready!")
        return True
    except Exception as e:
        print(f"  ❌ Could not import pygame after install: {e}")
        return False


_MENU_MUSIC = {"chan": None, "snd": None, "playing": False}


def _start_menu_music():
    """Loop the main-menu track from assets/ on the menu screen."""
    if not PYGAME_AVAILABLE or _MENU_MUSIC.get("playing"):
        return
    try:
        if not pygame.get_init():
            pygame.init()
        if not pygame.mixer.get_init():
            pygame.mixer.init(SOUND_SAMPLE_RATE, -16, 2, SOUND_BUFFER_SIZE)
        else:
            try:
                pygame.mixer.stop()
            except Exception:
                pass
        import pathlib
        # Try dedicated menu track first, fall back to the forest ambience.
        for fname in ("audiomass-output-_1_.ogg", "hayden-folker-adrift-_1_.ogg"):
            path = pathlib.Path(__file__).parent / "assets" / fname
            if path.exists():
                snd = pygame.mixer.Sound(str(path))
                try:
                    snd.set_volume(0.55)
                except Exception:
                    pass
                ch = pygame.mixer.find_channel(True)
                if ch:
                    ch.play(snd, loops=-1)
                    _MENU_MUSIC.update({"chan": ch, "snd": snd, "playing": True})
                return
    except Exception:
        _MENU_MUSIC["playing"] = False


def _stop_menu_music():
    try:
        if _MENU_MUSIC.get("chan"):
            _MENU_MUSIC["chan"].stop()
    except Exception:
        pass
    _MENU_MUSIC.update({"chan": None, "snd": None, "playing": False})


CREDITS_LINES = [
    "  " + "=" * 60,
    "  \U0001F30C  9 PLANETS \u2014 CREDITS",
    "  " + "=" * 60,
    "",
    "  Chief Game Designer:        Ibai Minaya Lemonds",
    "  Supplemental Game Designer: Khoa LeDihn",
    "  Programmer:                 Ibai Minaya Lemonds",
    "  Writer:                     Ibai Minaya Lemonds",
    "  Flavor Text:                Khoa LeDihn",
    "",
    "  \U0001F3B5 Battle music",
    "     Dragon Castle by Makai Symphony",
    "     https://soundcloud.com/makai-symphony",
    "     Music promoted by https://www.chosic.com/",
    "     Creative Commons CC BY-SA 3.0",
    "     https://creativecommons.org/licenses/by-sa/3.0/",
    "",
    "  \U0001F3B5 Forest ambience",
    "     \"Adrift\" composed by Hayden Folker",
    "     Licensed under Creative Commons Attribution 3.0 (CC BY 3.0).",
    "",
    "  \U0001F3B5 Arctic ambience",
    "     \"Flowing Into The Darkness\" by Nyoko",
    "     Licensed under Creative Commons Attribution 3.0 (CC BY 3.0)",
    "     https://creativecommons.org/licenses/by/3.0/",
    "     https://soundcloud.com/thenyoko",
    "",
    "  " + "=" * 60,
]


def show_credits_screen():
    """Dedicated credits screen (main menu option)."""
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    print()
    for line in CREDITS_LINES:
        print(line)
    sys.stdout.write("\n  Press Enter to return to the menu... ")
    sys.stdout.flush()
    try:
        while True:
            k = _ps_key()
            if k in ("ENTER", "\r", "\n", None):
                break
    except (EOFError, KeyboardInterrupt):
        pass
    sys.stdout.write("\n")
    sys.stdout.flush()


def _prompt_debug_password():
    """Prompt for the Debug Mode password (masked). 3 wrong tries = denied.
    Returns True only on the correct password."""
    PW = "catsruledogsdrool"
    for attempt in range(3):
        sys.stdout.write("\n  🔓 Debug Mode password (%d tries left): " % (3 - attempt))
        sys.stdout.flush()
        entered = ""
        while True:
            try:
                ck = _ps_key()
            except (EOFError, KeyboardInterrupt):
                return False
            if ck == 'ENTER':
                break
            if ck == 'BACKSPACE':
                if entered:
                    entered = entered[:-1]
                    sys.stdout.write("\b \b"); sys.stdout.flush()
                continue
            if ck and ck.isprintable() and len(ck) == 1:
                entered += ck
                sys.stdout.write("*"); sys.stdout.flush()
        if entered == PW:
            sys.stdout.flush()
            time.sleep(0.8)
            return True
        sys.stdout.write("\n  ❌ Incorrect password.\n")
        sys.stdout.flush()
        time.sleep(0.6)
    sys.stdout.write("  🚫 3 failed attempts — Debug Mode denied.\n")
    sys.stdout.flush()
    time.sleep(0.9)
    return False


def pick_save():
    """
    Show the save-slot menu in normal (cooked) terminal mode.
    Returns (save_path, biome, is_new_game).
    """
    os.makedirs(SAVES_DIR, exist_ok=True)
    _start_menu_music()
    saves = sorted(f for f in os.listdir(SAVES_DIR) if f.endswith(".json"))

    print()
    print("  " + "═" * 54)
    print("  🪐  9 PLANETS — Beta")
    print("  🎵 Battle music: Dragon Castle by Makai Symphony")
    print("  " + "═" * 54)


    live_entries = []   # (path, biome, debug_flag, line_template, ts)
    dead_entries = []   # (line, ts)

    for fname in saves:
        path = os.path.join(SAVES_DIR, fname)
        try:
            with open(path) as f:
                d = json.load(f)
            m = d.get("meta", {})
            display_name = m.get("name", fname[:-5])
            biome_tag    = "🌲" if m.get("biome", "Forest") == "Forest" else "❄️"
            hp           = m.get("health", d.get("player", {}).get("health", "?"))
            coins        = m.get("coins",  d.get("player", {}).get("coins",  "?"))
            ts           = m.get("last_played", 0)
            date_str     = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "unknown"
            is_dead      = m.get("dead", False)
            if is_dead:
                reason = m.get("death_reason", "Unknown")
                pts = int(m.get("points", d.get("player", {}).get("points", 0)))
                pt_secs = m.get("total_playtime", d.get("player", {}).get("total_playtime", 0))
                time_str = _fmt_playtime(pt_secs)
                dead_entries.append((
                    f"  ☠️  {display_name:<20} {biome_tag}  🪙{coins:.0f}  🏆{pts}pts  ⏱️{time_str}  💀 {reason}", ts))
            else:
                pts = int(m.get("points", d.get("player", {}).get("points", 0)))
                pt_secs = m.get("total_playtime", d.get("player", {}).get("total_playtime", 0))
                time_str = _fmt_playtime(pt_secs)
                live_entries.append((path, m.get("biome", "Forest"), bool(m.get("debug", False)),
                                     f"  {{i}}. {biome_tag} {display_name:<18} ❤️{hp:.0f}  🪙{coins:.0f}  🏆{pts}pts  ⏱️{time_str}  🕒 {date_str}", ts))
        except Exception:
            live_entries.append((path, "Forest", False,
                                 f"  {{i}}. 📁 {fname[:-5]}  (unreadable)", 0))

    # Sort most-recent first
    live_entries.sort(key=lambda e: -e[4])
    dead_entries.sort(key=lambda e: -e[1])

    # Pagination setup
    SAVE_PAGE_SIZE = 8
    total_live = len(live_entries)
    total_pages = max(1, (total_live + SAVE_PAGE_SIZE - 1) // SAVE_PAGE_SIZE)
    current_page = 0
    new_idx = total_live + 1
    dev_state = {"on": False}   # Dev Mode toggle (first menu option)

    def _show_save_page(page, buf=""):
        sys.stdout.write("\033[2J\033[H")   # clear screen, go home
        sys.stdout.flush()
        start = page * SAVE_PAGE_SIZE
        end   = min(start + SAVE_PAGE_SIZE, total_live)
        print()
        print("  " + "═" * 54)
        print("  🪐  9 PLANETS — Beta")
        print("  🎵 Battle music: Dragon Castle by Makai Symphony")
        print("  " + "═" * 54)
        _dev_lbl = "ON ✅" if dev_state["on"] else "OFF"
        print(f"\n  🛠  Dev Mode: {_dev_lbl}   (type 'dev' to toggle)")
        if total_pages > 1:
            print(f"\n  💾  YOUR SAVES  (page {page+1}/{total_pages})\n")
        else:
            print(f"\n  💾  YOUR SAVES\n")
        for i in range(start, end):
            print(live_entries[i][3].replace("{i}", str(i+1)))
        if page == total_pages - 1 and dead_entries:
            print("\n  📜  PAST GAMES\n")
            for line, _ in dead_entries:
                print(line)
        print(f"\n  {new_idx}. ✨  New Game")
        print(f"  {new_idx + 1}. 📜  Credits")
        print("  0.  ❌  Exit")
        if total_pages > 1:
            print("  ↑/↓ arrow keys to flip pages   d<n> to delete")
        else:
            print("  d<n> to delete a save (e.g. d1)")
        sys.stdout.write(f"\n  Choose: {buf}")
        sys.stdout.flush()

    if total_live or dead_entries:
        _show_save_page(0)
        buf = ""          # typed characters accumulate here
        while True:
            try:
                k = _ps_key()
            except (EOFError, KeyboardInterrupt):
                sys.exit(0)

            if k == 'UP':
                if current_page > 0:
                    current_page -= 1
                    buf = ""
                    _show_save_page(current_page, buf)
                continue
            if k == 'DOWN':
                if current_page < total_pages - 1:
                    current_page += 1
                    buf = ""
                    _show_save_page(current_page, buf)
                continue
            if k == 'BACKSPACE':
                buf = buf[:-1]
                sys.stdout.write(f"\r  Choose: {buf}  \r  Choose: {buf}")
                sys.stdout.flush()
                continue
            if k == 'ENTER':
                raw = buf.strip()
                buf = ""
                sys.stdout.write("\n")
                sys.stdout.flush()
                if raw == "0":
                    sys.exit(0)
                # Dev Mode toggle (first option)
                if raw.lower() == "dev":
                    dev_state["on"] = not dev_state["on"]
                    _show_save_page(current_page, "")
                    continue
                # Delete command
                if raw.lower().startswith("d") and len(raw) > 1:
                    try:
                        del_idx = int(raw[1:])
                        if 1 <= del_idx <= total_live:
                            path_d, _, _, _, _ = live_entries[del_idx - 1]
                            sname = os.path.splitext(os.path.basename(path_d))[0]
                            sys.stdout.write(f"  Delete save '{sname}'? [y/N]: ")
                            sys.stdout.flush()
                            confirm_buf = ""
                            while True:
                                ck = _ps_key()
                                if ck == 'ENTER':
                                    break
                                if ck == 'BACKSPACE':
                                    confirm_buf = confirm_buf[:-1]
                                elif ck and ck.isprintable():
                                    confirm_buf += ck
                                    sys.stdout.write(ck); sys.stdout.flush()
                            if confirm_buf.strip().lower() in ("y","yes"):
                                ok, m = delete_save(sname)
                                sys.stdout.write(f"\n  {m}\n"); sys.stdout.flush()
                                if ok:
                                    return pick_save()
                            else:
                                sys.stdout.write("\n  Deletion cancelled.\n"); sys.stdout.flush()
                    except (ValueError, IndexError):
                        pass
                    _show_save_page(current_page, "")
                    continue
                # Number selection
                if raw.isdigit():
                    idx = int(raw)
                    if 1 <= idx <= total_live:
                        path, biome, save_debug, _, _ = live_entries[idx - 1]
                        return path, biome, False, None, False, 1.0, True, dev_state["on"], False, save_debug, "dark", False, False
                    if idx == new_idx:
                        break
                    if idx == new_idx + 1:
                        show_credits_screen()
                        _show_save_page(current_page, "")
                        continue
                if raw:
                    sys.stdout.write("  ⚠️  Invalid choice.\n"); sys.stdout.flush()
                    time.sleep(0.6)
                _show_save_page(current_page, "")
                continue
            # Printable character — echo and accumulate
            if k and k.isprintable():
                buf += k
                sys.stdout.write(k); sys.stdout.flush()
    else:
        while True:
            sys.stdout.write("\033[2J\033[H")
            print()
            print("  " + "═" * 54)
            print("  🪐  9 PLANETS — Beta")
            print("  " + "═" * 54)
            print("\n  No saves found.\n")
            print("  1. ✨  New Game")
            print("  2. 📜  Credits")
            print("  0. ❌  Exit")
            try:
                raw_start = input("\n  Choose: ").strip()
            except (EOFError, KeyboardInterrupt):
                sys.exit(0)
            if raw_start == "0":
                sys.exit(0)
            if raw_start == "2":
                show_credits_screen()
                continue
            break

    # ---- New Game flow ----
    print("\n  ✨  NEW GAME\n")
    while True:
        try:
            raw_name = input("  Save name: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if not raw_name:
            print("  ⚠️  Name cannot be empty.")
            continue
        safe = "".join(c for c in raw_name if c.isalnum() or c in " _-").strip()
        if not safe:
            print("  ⚠️  Name must contain at least one letter or number.")
            continue
        slug = safe.replace(" ", "_")
        path = os.path.join(SAVES_DIR, slug + ".json")
        if os.path.exists(path):
            print(f"  ⚠️  A save named '{safe}' already exists. Choose a different name.")
            continue
        break

    # ---- AUDIO (first setting) ----
    print()
    print("  🔊 AUDIO:")
    print("  The game includes ambient sounds and music via pygame.")
    print("  ⚠️  Audio uses extra CPU — if your device lags, choose No.")
    audio_enabled = False
    while True:
        try:
            raw_audio = input("  Enable audio? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if raw_audio in ("", "n", "no"):
            audio_enabled = False
            print("  🔇 Audio disabled.")
            break
        if raw_audio in ("y", "yes"):
            if PYGAME_AVAILABLE:
                audio_enabled = True
                print("  🔊 Audio enabled.")
            else:
                audio_enabled = _setup_audio_venv()
                if not audio_enabled:
                    print("  🔇 Continuing without audio.")
            break
        print("  ⚠️  Please answer y or n.")

    print()
    print("  🌍 START LOCATION:")
    print("  1. 🌲 Forest  — Temperate woodland, food & storms")
    print("\n  Starting in the Arctic is no longer available. You must travel there later with preparation.\n")
    chosen_biome = "Forest"

    print("  🎯 GAME MODE:")
    print("  1. Quest Mode (recommended, especially for beginners) — follow the old man's guidance and goals.")
    print("  2. Explorer Mode — free play without quest popups or required quests.")
    chosen_mode = "quest"
    while True:
        try:
            raw_mode = input("  Choose mode [1/2]: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if raw_mode == "1":
            chosen_mode = "quest"
            break
        if raw_mode == "2":
            chosen_mode = "explorer"
            break
        print("  ⚠️  Invalid choice. Enter 1 or 2.")

    print()
    print("  ⚡ FAST MODE:")
    print("  1. Off — normal pacing (Arctic is far, standard craft times).")
    print("  2. On  — Arctic only 1000 coordinates away & everything crafts 3x faster.")
    chosen_fast = False
    while True:
        try:
            raw_fast = input("  Fast Mode [1/2]: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if raw_fast in ("1", ""):
            chosen_fast = False
            break
        if raw_fast == "2":
            chosen_fast = True
            break
        print("  ⚠️  Invalid choice. Enter 1 or 2.")

    print()
    print("  🖼️  DISPLAY MODE:")
    print("  1. Standard — normal terminal view.")
    print("  2. Graphics — shows a live mini-map of your surroundings.")
    print("               Auto-zooms the terminal for the best experience.")
    print("               All gameplay remains command-driven (no extra keypresses).")
    chosen_graphics = False
    while True:
        try:
            raw_graphics = input("  Choose display mode [1/2]: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if raw_graphics in ("1", ""):
            chosen_graphics = False
            break
        if raw_graphics == "2":
            chosen_graphics = True
            break
        print("  ⚠️  Invalid choice. Enter 1 or 2.")

    chosen_adaptive = False
    if chosen_graphics:
        print()
        print("  📐 GRAPHICS MAP SIZE:")
        print("  1. Classic  — fixed 20×20 grid (always the same, like the original).")
        print("  2. Adaptive — fills your terminal! Wider terminal = more map visible.")
        print("               Up to 400 tiles at once. Aspect ratio stays balanced.")
        while True:
            try:
                raw_adaptive = input("  Choose map size [1/2]: ").strip()
            except (EOFError, KeyboardInterrupt):
                sys.exit(0)
            if raw_adaptive in ("1", ""):
                chosen_adaptive = False
                break
            if raw_adaptive == "2":
                chosen_adaptive = True
                break
            print("  ⚠️  Invalid choice. Enter 1 or 2.")

    chosen_theme = "dark"
    if not chosen_graphics:
        print()
        print("  🖥️  TERMINAL THEME:")
        print("  1. Dark Mode — always dark with white letters.")
        print("  2. Day/Night Mode — white by day, black by night.")
        while True:
            try:
                raw_theme = input("  Choose terminal theme [1/2]: ").strip()
            except (EOFError, KeyboardInterrupt):
                sys.exit(0)
            if raw_theme in ("1", ""):
                chosen_theme = "dark"
                break
            if raw_theme == "2":
                chosen_theme = "day_night"
                break
            print("  ⚠️  Invalid choice. Enter 1 or 2.")
    else:
        print("  ℹ️  Terminal theme: Dark Mode (fixed for Graphics Mode).")

    print()
    print("  🥊 COMBAT SETTING:")
    print("  1. Normal — standard encounters.")
    print("  2. Combat — doubled monster spawn (more dangerous).")
    chosen_combat = "normal"
    while True:
        try:
            raw_combat = input("  Choose combat setting [1/2]: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if raw_combat == "1":
            chosen_combat = "normal"
            break
        if raw_combat == "2":
            chosen_combat = "combat"
            break
        print("  ⚠️  Invalid choice. Enter 1 or 2.")

    if chosen_combat == "combat":
        if chosen_mode == "quest":
            chosen_mode = "combat"
        else:
            chosen_mode = "explorer_combat"

    print()
    print("  ⚖️  DIFFICULTY:")
    print("  1. Easy")
    print("  2. Normal")
    print("  3. Hard")
    print("  4. Light  (only ❤️ Health, 🍽️ Hunger, ⚡ Energy — Energy regenerates)")
    difficulty_mult = NORMAL_HUNGER_MULT
    LIGHT_MODE["on"] = False
    while True:
        try:
            raw_diff = input("  Choose difficulty [1/2/3/4]: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if raw_diff == "1": difficulty_mult = BEGINNER_HUNGER_MULT; break
        if raw_diff == "2": difficulty_mult = NORMAL_HUNGER_MULT;  break
        if raw_diff == "3": difficulty_mult = HARD_HUNGER_MULT;  break
        if raw_diff == "4":
            difficulty_mult = BEGINNER_HUNGER_MULT
            LIGHT_MODE["on"] = True
            break
        print("  ⚠️  Invalid choice. Enter 1, 2, 3, or 4.")

    print()
    print("  ⚙️ DEBUG MODE:")
    print("  This is a password-protected cheat mode.")
    print("  Enable it only if you want extra debugging powers and no penalties.")
    debug_mode = False
    while True:
        try:
            raw_debug = input("  Enable Debug Mode? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if raw_debug in ("", "n", "no"):
            debug_mode = False
            break
        if raw_debug in ("y", "yes"):
            debug_mode = _prompt_debug_password()
            if debug_mode:
                print("  ✅ Debug Mode enabled.")
            else:
                print("  🔒 Debug Mode disabled.")
            break
        print("  ⚠️  Please answer y or n.")

    print()
    print("  📖 QUICK TUTORIAL:")
    print("  Would you like a quick, guided tutorial that walks you through")
    print("  finding berries, inspecting them, and crafting your first plank?")
    quick_tutorial = False
    while True:
        try:
            raw_qt = input("  Quick tutorial? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if raw_qt in ("y", "yes"):
            quick_tutorial = True
            break
        if raw_qt in ("", "n", "no"):
            quick_tutorial = False
            break
        print("  ⚠️  Please answer y or n.")

    print()
    return path, chosen_biome, True, chosen_mode, quick_tutorial, difficulty_mult, audio_enabled, dev_state["on"], chosen_fast, debug_mode, chosen_theme, chosen_graphics, chosen_adaptive



# ==================== MAIN ====================
# ==================== DEATH ROOM — HILDEGARD DHANVANTARI ====================
# When the player dies they are taken to a black emoji room where the god of
# healing offers a resurrection in exchange for supplies. Rendered flicker-free
# (in-place repaint, no destructive clears) just like graphics mode.

DR_W = 25
DR_H = 24
DR_BLACK = "\u2b1b"
DR_WHITE = "\u2b1c"
DR_SUN = "\u2600\ufe0f"
DR_GOD = "\U0001f622"
DR_PLAYER = "\u2620\ufe0f"

def _dr_god_cells():
    cells = {(14, 12): DR_GOD}
    for r in (12, 13, 15, 16):
        cells[(r, 12)] = DR_SUN
    for c in (9, 10, 11, 13, 14, 15):
        cells[(14, c)] = DR_SUN
    return cells

DR_GOD_CELLS = _dr_god_cells()

def _dr_nice(name):
    return str(name).replace("_", " ").title()

def _dr_render(term, pr, pc, text_lines, white_rows=0, prompt=""):
    """Repaint the death room in place (no clear-screen => no flicker).

    The room is windowed to whatever the terminal can show, and the dialogue
    text ALWAYS gets its rows first — so graphics mode (smaller window / bigger
    font) looks the same as standard mode instead of cutting the text off."""
    try:
        _cols, _rows = os.get_terminal_size()
    except Exception:
        _cols, _rows = TERM_WIDTH, 24
    _cols = max(20, _cols)
    _rows = max(8, _rows)
    _draw_w = max(1, _cols - 8)

    # ── Text block first (it has priority over room rows) ────────────────
    text = []
    for line in text_lines:
        text.extend(vwrap(str(line), _draw_w) if line else [""])
    if prompt:
        text.append(prompt)

    avail = _rows - 1                     # keep one spare row: never scroll
    text_h = min(len(text) + 1, max(3, avail - 6))   # +1 = blank spacer row
    grid_h = max(4, min(DR_H, avail - text_h))
    grid_w = max(6, min(DR_W, _draw_w // 2))

    # Vertical window: keep the god (rows 12-16) and the player in view.
    lo = min(12, pr); hi = max(16, pr + 1)
    if hi - lo + 1 <= grid_h:
        r0 = lo - (grid_h - (hi - lo + 1)) // 2
    else:
        r0 = pr - grid_h // 2
    r0 = max(0, min(DR_H - grid_h, r0))
    # Horizontal window: keep the god column (12) and the player column.
    clo = min(9, pc); chi = max(15, pc)
    if chi - clo + 1 <= grid_w:
        c0 = clo - (grid_w - (chi - clo + 1)) // 2
    else:
        c0 = pc - grid_w // 2
    c0 = max(0, min(DR_W - grid_w, c0))

    def _tile(r, c):
        if r < white_rows:
            return _cell2(DR_WHITE)
        if c == pc and r in (pr, pr + 1):
            return _cell2(DR_PLAYER)
        if (r, c) in DR_GOD_CELLS:
            return _cell2(DR_GOD_CELLS[(r, c)])
        return _cell2(DR_BLACK)

    out = []
    for r in range(r0, r0 + grid_h):
        out.append("".join(_tile(r, c) for c in range(c0, c0 + grid_w)))
    out.append("")
    out.extend(text[-(max(1, text_h - 1)):] if len(text) > text_h - 1 else text)
    out = out[:avail]

    body = "\033[K\r\n".join(vtrunc(str(l), _draw_w).rstrip() for l in out)
    sys.stdout.write("\033[?25l\033[H\033[40m\033[97m" + body + "\033[K\033[J")

    # ── ANSI absolute-position fixup (same protocol as graphics mode) ──────
    # Terminals disagree on emoji cell width, so sequential output drifts a
    # column or two across a row. Re-stamp every grid cell at an explicit
    # \033[row;colH so each tile is pinned to its exact column.
    _fx = []
    for i in range(grid_h):
        _row = i + 1
        for j in range(grid_w):
            _fx.append(f"\033[{_row};{1 + j * 2}H{_tile(r0 + i, c0 + j)}")
    sys.stdout.write("".join(_fx))
    sys.stdout.write(f"\033[{min(len(out) + 1, _rows)};1H")
    sys.stdout.flush()


def _dr_move(pr, pc, key):
    nr, nc = pr, pc
    if key == 'UP': nr -= 1
    elif key == 'DOWN': nr += 1
    elif key == 'LEFT': nc -= 1
    elif key == 'RIGHT': nc += 1
    if nc < 0 or nc >= DR_W or nr < 0 or nr + 1 >= DR_H:
        return pr, pc
    if (nr, nc) in DR_GOD_CELLS or (nr + 1, nc) in DR_GOD_CELLS:
        return pr, pc
    return nr, nc

def _dr_wait(term, state, text_lines, prompt="", accept=None, seconds=None):
    """Render + let the player walk around. Returns the accepted key, or None
    when a timed pause elapses."""
    start = time.time()
    while True:
        _dr_render(term, state["pr"], state["pc"], text_lines, prompt=prompt)
        k = term.get_key(0.12)
        if k in ('UP', 'DOWN', 'LEFT', 'RIGHT'):
            state["pr"], state["pc"] = _dr_move(state["pr"], state["pc"], k)
            continue
        if accept and k and k.lower() in accept:
            return k.lower()
        if seconds is not None and time.time() - start >= seconds:
            return None

def _dr_difficulty_scale(player):
    """How many 'death levels' each real death counts for.
    Easy x2, Normal x4, Hard x8 (death 1 on easy asks like death 2)."""
    m = getattr(player, "difficulty_mult", NORMAL_HUNGER_MULT)
    if m <= BEGINNER_HUNGER_MULT: return 2
    if m >= HARD_HUNGER_MULT: return 8
    return 4

def _dr_pick_requests(player, count):
    """Pick a tribute totalling `count` items.

    The god's demand must ALWAYS grow by the difficulty step on every death,
    so when the player doesn't own `count` distinct item types we keep the
    total honest by asking for larger amounts of the types they do own.
    """
    count = max(1, int(count))
    inv = getattr(player, "inventory", {}) or {}
    excluded = {
        "coins", "woodworking_station", "furnace", "water_filter", "liquifier",
        "sewing_station", "smelter", "axe", "advanced_axe", "pickaxe",
        "light_armor", "medium_armor", "heavy_armor", "pants", "shirt",
        "medium_pants", "medium_shirt", "heavy_pants", "heavy_shirt",
        "bandages", "enhanced_bandage", "textbook", "id_lens",
        "poison_trap", "trap", "catnip",
    }
    excluded.update(SPEAR_DEFS.keys() if isinstance(SPEAR_DEFS, dict) else set())
    excluded.update(SHIELD_DEFS.keys() if isinstance(SHIELD_DEFS, dict) else set())
    excluded.update(CLOTHING_PANTS if isinstance(CLOTHING_PANTS, (list, tuple, set)) else set())
    excluded.update(CLOTHING_SHIRTS if isinstance(CLOTHING_SHIRTS, (list, tuple, set)) else set())
    pool = []
    for k, v in inv.items():
        if k in excluded or k.startswith("unknown_") or k.startswith("half_"):
            continue
        if isinstance(v, (int, float)) and v > 0:
            pool.append((k, int(v)))
        elif isinstance(v, dict):
            q = int(v.get("qty", 0) or 0)
            if q > 0:
                pool.append((k, q))
    if not pool:
        return []
    random.shuffle(pool)

    amounts = {}
    # For each item type, pick a random demand:
    #   - half the inventory is MOST common (weight 3)
    #   - 1 item is LEAST common (weight 1)
    #   - all of the item is LEAST common (weight 1)
    # We honour `count` as the total number of items demanded across all types.
    if not pool:
        return []

    # First, assign a random amount to each item type in the pool.
    pool_amounts = {}
    for key, have in pool:
        half = max(1, math.ceil(have / 2))
        weights = []
        choices = []
        # Option: ask for 1 (least common)
        choices.append(1); weights.append(1)
        # Option: ask for half (most common — highest weight)
        if half != 1:
            choices.append(half); weights.append(3)
        # Option: ask for all (least common)
        if have != 1 and have != half:
            choices.append(have); weights.append(1)
        total_w = sum(weights)
        r = random.random() * total_w
        acc = 0; picked = choices[0]
        for ch, wt in zip(choices, weights):
            acc += wt
            if r <= acc:
                picked = ch; break
        pool_amounts[key] = picked

    # Trim/fill to hit the overall `count` target while respecting per-item limits.
    total_asked = sum(pool_amounts.values())
    keys = list(pool_amounts.keys())
    random.shuffle(keys)
    # Reduce if over
    while total_asked > count and keys:
        for k in keys:
            if total_asked <= count:
                break
            if pool_amounts[k] > 1:
                pool_amounts[k] -= 1
                total_asked -= 1
    # Increase if under (round-robin, never over the inventory limit)
    rounds = 0
    while total_asked < count and rounds < 5:
        rounds += 1
        for k in keys:
            if total_asked >= count:
                break
            have = next(h for kk, h in pool if kk == k)
            if pool_amounts[k] < have:
                pool_amounts[k] += 1
                total_asked += 1

    return [(k, pool_amounts[k]) for k in keys if pool_amounts.get(k, 0) > 0]

def _dr_req_text(reqs):
    return ", ".join(f"{amt} {_dr_nice(k)}" for k, amt in reqs)

def _dr_take(player, reqs):
    for key, amt in reqs:
        cur = player.inventory.get(key, 0)
        if isinstance(cur, dict):
            cur["qty"] = max(0, int(cur.get("qty", 0) or 0) - amt)
        else:
            player.inventory[key] = max(0, int(cur) - amt)

def _dr_whiteout(term, state):
    for rows in range(1, DR_H + 1):
        _dr_render(term, state["pr"], state["pc"],
                   ["", "The light takes everything..."], white_rows=rows)
        time.sleep(0.375)

def _dr_silence_music(sound):
    """Stop the normal/ambient music while the death room is on screen."""
    if not sound or not getattr(sound, "enabled", False):
        return
    try: sound.stop_all_loops()
    except Exception: pass
    for name in ("bgm_channel", "ambient_channel", "combat_bgm_channel"):
        ch = getattr(sound, name, None)
        if ch:
            try: ch.stop()
            except Exception: pass
    try: sound.in_combat_bgm = False
    except Exception: pass


def _dr_restore_music(sound):
    """Bring the normal ambient music back after the death room."""
    if not sound or not getattr(sound, "enabled", False):
        return
    ch = getattr(sound, "ambient_channel", None)
    if ch:
        try: ch.set_volume(1.0)
        except Exception: pass
    for meth in ("start_ambient_bgm", "restore_ambient", "start_ambient", "play_ambient", "resume_bgm", "start_bgm"):
        fn = getattr(sound, meth, None)
        if callable(fn):
            try:
                fn()
                break
            except Exception:
                pass


def _dr_exit_graphics(player, was_on):
    """Restore graphics mode (and its zoom) after the death room."""
    if not was_on:
        return
    try:
        player.graphics_mode = True
    except Exception:
        pass
    try:
        sys.stdout.write("\033[H\033[2J")
        sys.stdout.flush()
    except Exception:
        pass


def death_room_sequence(term, player, world, sound, death_reason):
    """Full death → god → revive flow. Returns True if the player is revived."""
    deaths = int(getattr(player, "death_count", 0)) + 1
    player.death_count = deaths

    state = {"pr": 22, "pc": 12}
    # The death room is drawn with its own standard-mode renderer. Graphics
    # mode keeps a different theme/zoom and repaints the split-panel HUD, which
    # made the room look wrong there. Leave graphics mode for the duration and
    # restore it afterwards so both modes look identical.
    _gm_was = bool(getattr(player, "graphics_mode", False))
    if _gm_was:
        try:
            player.graphics_mode = False
        except Exception:
            pass
    try:
        sys.stdout.write("\033[?25l\033[0m\033[40m\033[97m\033[H\033[2J")
        sys.stdout.flush()
    except Exception:
        pass
    _dr_silence_music(sound)
    if sound and getattr(sound, "enabled", False):
        try: sound.play_god_voice()
        except Exception: pass

    header = [
        "\033[1m*** I AM HILDEGARD DHANVANTARI. AND YOU ARE DEAD!!! ***\033[0m",
        f"YOU ARE DEAD, MAN!   (Cause: {death_reason})",
        "",
    ]
    _dr_wait(term, state, header + ["Hildegard Dhanvantari, god of healing, regards you..."],
             seconds=3.0)

    scale = _dr_difficulty_scale(player)
    ask_count = deaths * scale
    reqs = _dr_pick_requests(player, ask_count)
    if not reqs:
        _dr_wait(term, state, header + [
            "\"You carry nothing at all. Even I cannot trade with empty hands.\"",
            "", "Press any key..."], accept="abcdefghijklmnopqrstuvwxyz \r\n", seconds=6.0)
        _dr_restore_music(sound)
        _dr_exit_graphics(player, _gm_was)
        return False

    ask = header + [
        "\"I am good, and so I will revive you. However, I'm running low on "
        + ", ".join(_dr_nice(k) for k, _ in reqs) + ".\"",
        "",
        f"\"Would you be so kind to give me {_dr_req_text(reqs)}?\"  [y/n]",
    ]
    ans = _dr_wait(term, state, ask, prompt="> ", accept="yn")

    if ans == 'n':
        extra = _dr_pick_requests(player, ask_count + scale)
        if not extra:
            extra = reqs
        _dr_wait(term, state, header + [
            "\"Oh really? I guess I don't have to revive you!\"",
            "You say: \"No, please! Allow me to survive!\"",
        ], seconds=3.5)
        _dr_wait(term, state, header + [
            f"\"Okay, then give me {_dr_req_text(extra)}.\"",
            "You say: \"O-okay!\"",
        ], seconds=3.5)
        reqs = extra

    _dr_take(player, reqs)
    _dr_wait(term, state, header + [
        f"You hand over {_dr_req_text(reqs)}.",
        "\"Then live again, mortal.\"",
    ], seconds=2.5)

    _dr_whiteout(term, state)

    player.health = getattr(player, "max_health", 100.0)
    player.hunger = max(getattr(player, "hunger", 0.0), 50.0)
    player.thirst = max(getattr(player, "thirst", 0.0), 50.0)
    player.energy = getattr(player, "max_energy", 100.0)
    player.fatigue = max(getattr(player, "fatigue", 0.0), 50.0)
    player.in_combat = False
    try:
        player.last_damage_cause = ""
    except Exception:
        pass
    _dr_restore_music(sound)
    _dr_exit_graphics(player, _gm_was)
    return True


def main():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("❌ This game requires a real terminal (TTY).")
        print("   Run it from a terminal or command prompt using: python3 game.py")
        return "exit"

    save_path = None; biome = "Forest"
    try:
        save_path, biome, is_new, chosen_mode, quick_tutorial, difficulty_mult, audio_enabled, dev_mode, fast_mode, debug_mode, chosen_theme, chosen_graphics, chosen_adaptive = pick_save()
        global _DEV_MODE; _DEV_MODE = bool(dev_mode)
        term = Terminal()
        if not term.using_windows_fallback:
            termios.tcflush(term.fd, termios.TCIFLUSH)
        term.setup()
        # If the player opted into the quick interactive tutorial, skip the
        # standard tutorial pages here — they will be shown at the end of QT.
        if is_new and not quick_tutorial:
            run_tutorial(term)
            _pending_lore_after_player = True
        else:
            _pending_lore_after_player = False

        # Animated "Preparing world" loading screen. The dots cycle
        # . -> .. -> ... -> .. -> . (250ms each) and then loop, while the
        # actual world/save preparation runs. Prep output is captured and
        # printed once the animation finishes so it doesn't break the line.
        _prep_done = threading.Event()
        _prep_start = time.time()
        def _prep_dots_anim():
            base = "🚀 Preparing world"
            seq = [".", "..", "...", "..", "."]
            i = 0
            while not _prep_done.is_set():
                _real_stdout.write("\r" + base + seq[i % len(seq)] + "   ")
                _real_stdout.flush()
                i += 1
                _prep_done.wait(0.25)
            _real_stdout.write("\r" + base + "...\n")
            _real_stdout.flush()
        _real_stdout = sys.stdout
        _prep_capture = io.StringIO()
        sys.stdout = _prep_capture
        _prep_thread = threading.Thread(target=_prep_dots_anim, daemon=True)
        _prep_thread.start()

        def _finish_prep():
            """Stop the dot animation and restore real stdout. Idempotent.
            Must run BEFORE any interactive step (tutorial/quests) so prompts
            are visible — otherwise the screen looks frozen on 'Preparing world'."""
            if _prep_done.is_set():
                return
            _elapsed = time.time() - _prep_start
            if _elapsed < 1.25:
                time.sleep(1.25 - _elapsed)
            _prep_done.set()
            try:
                _prep_thread.join(timeout=2.0)
            except Exception:
                pass
            if sys.stdout is not _real_stdout:
                sys.stdout = _real_stdout
                _txt = _prep_capture.getvalue()
                if _txt.strip():
                    _real_stdout.write(_txt)
                    _real_stdout.flush()

        player = Player()
        player.mode = chosen_mode or "quest"
        player.difficulty_mult = difficulty_mult
        player.light_mode = bool(LIGHT_MODE.get("on"))
        player.fast_mode = bool(fast_mode)
        player.debug_mode = bool(debug_mode)
        player.terminal_theme = chosen_theme or "dark"
        player.graphics_mode = bool(chosen_graphics)
        player.graphics_adaptive = bool(chosen_adaptive)
        world = World(biome, "day")
        world.biome = biome
        global _g_world; _g_world = world
        sound = SoundManager() if audio_enabled else SoundManager.__new__(SoundManager)
        if not audio_enabled:
            sound.enabled = False; sound.bgm_channel = None
            sound.ambient_channel = None; sound.sounds = {}; sound.last_low_health = 0.0
            sound.last_biome = None
        elif not sound.enabled:
            err_hint = getattr(sound, "_init_error", None)
            print(f"  ⚠️  Audio: pygame installed but mixer failed to open.")
            if err_hint:
                print(f"     Reason: {err_hint}")
            print("  🔇 Continuing without sound.")
        player.sound = sound
        world.sound = sound
        if sound.enabled:
            sound.play_intro()
            sound.play_environment(world.biome)
        _stop_menu_music()
        weather = WeatherSystem()
        term.theme_mode = player.terminal_theme
        term.pause_context_player = player
        # Adaptive mode: just verify terminal is large enough for any map.
        # Classic mode: target 88×22 for the 20×20 fixed grid.
        if getattr(player, "graphics_adaptive", False):
            graphics_zoomed = _attempt_graphics_mode(player, target_cols=60, target_rows=16)
        else:
            graphics_zoomed = _attempt_graphics_mode(player, target_cols=88, target_rows=22)
        term.pause_context_world = world
        term.pause_context_weather = weather

        # Load save file before update_quests to preserve quest states
        if not is_new:
            try:
                with open(save_path) as f: data = json.load(f)
                for k, v in data.get("world", {}).get("clusters", {}).items():
                    x, y = map(int, k.split("_")); world.clusters[(x, y)] = v
                for a, val in data.get("player", {}).items():
                    if hasattr(player, a): setattr(player, a, val)
                for k, v in data.get("player_inv", {}).items():
                    if isinstance(v, dict) and v.get("__unknown__"):
                        player.inventory[k] = {"qty": v.get("qty", 0), "items": v.get("items", []),
                                               "inspect_tries": v.get("inspect_tries", 0)}
                    elif k in player.inventory and isinstance(v, (int, float)):
                        player.inventory[k] = v
                world.animals = data.get("world", {}).get("animals", [])
                world.houses = data.get("world", {}).get("houses", [])
                player.debug_mode = bool(data.get("meta", {}).get("debug", False))
                player.terminal_theme = data.get("meta", {}).get("terminal_theme", getattr(player, "terminal_theme", "dark"))
                player.graphics_mode = bool(data.get("meta", {}).get("graphics_mode", getattr(player, "graphics_mode", False)))
                player.graphics_adaptive = bool(data.get("meta", {}).get("graphics_adaptive", getattr(player, "graphics_adaptive", False)))
                player.show_commands = bool(data.get("meta", {}).get("show_commands", getattr(player, "show_commands", True)))
                for a in world.animals:
                    a["last_move"] = time.time()
                # Fix active_tasks end times: if task end is in the past, keep 1s left
                now_load = time.time()
                for t in player.active_tasks:
                    if t.get("end", 0) < now_load:
                        t["end"] = now_load + 1.0
                print("✅ Save loaded.")
            except Exception as e:
                print(f"⚠️  Load failed ({e}). Starting fresh."); is_new = True

        # Apply Fast Mode world tuning (Arctic distance + craft speed) based on
        # the player's setting (restored from save for existing games).
        global _FAST_MODE, _CRAFT_TIME_MULT, FOREST_RADIUS
        _FAST_MODE = bool(getattr(player, "fast_mode", False))
        _CRAFT_TIME_MULT = (1.0 / 3.0) if _FAST_MODE else 1.0
        FOREST_RADIUS = _FAST_FOREST_RADIUS if _FAST_MODE else 3500

        if is_new and quick_tutorial:
            msg = ["📖 Interactive Tutorial active. Normal quests begin after the walkthrough."]
        elif player.mode == "quest":
            msg = ["🎮 Quest Mode active. Follow the old man's goals or type 'quests' to review them."]
        elif player.mode == "combat":
            msg = ["🎮 Combat Mode active. Quest Mode with doubled monster spawn — good luck!"]
        elif player.mode == "explorer_combat":
            msg = ["🎮 Explorer Combat Mode active. Quests are disabled and monster spawn is higher."]
        else:
            msg = ["🎮 Explorer Mode active. Quests are disabled and you can roam freely."]
        if getattr(player, "graphics_mode", False):
            if graphics_zoomed:
                msg.append("🖼️ Graphics Mode active — terminal auto-zoom was attempted.")
            else:
                msg.append("🖼️ Graphics Mode active — terminal zoom could not be adjusted automatically.")

        # Finish the loading animation and restore real stdout BEFORE the
        # interactive tutorial / first quest update. These steps print prompts
        # and wait for keypresses, so they must not run while output is being
        # captured (that made the game look stuck on "Preparing world").
        _finish_prep()

        # Start the interactive tutorial before the first quest update so no
        # normal quest can activate or pop up during the guided walkthrough.
        if is_new and quick_tutorial:
            qt_init(term, player, world)
        elif _pending_lore_after_player:
            schedule_lore_intro(player, delay=5.0)

        update_quests(player, weather, world, msg, term)

        def _exit_handler(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGINT, _exit_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, _exit_handler)
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, _exit_handler)
    except Exception as e:
        # Make sure the animation thread is stopped and real stdout restored
        # before reporting any setup failure.
        try:
            _prep_done.set()
            if _prep_thread.is_alive():
                _prep_thread.join(timeout=1.0)
        except Exception:
            pass
        try:
            if sys.stdout is not _real_stdout:
                sys.stdout = _real_stdout
                _leftover = _prep_capture.getvalue()
                if _leftover.strip():
                    sys.stdout.write(_leftover)
        except Exception:
            pass
        print(f"\n❌ Setup failed: {e}")
        import traceback; traceback.print_exc()
        try: input("\nTraceback shown above. Press Enter to close...")
        except Exception: pass
        return "exit"

    sys.stdout.flush()
    if is_new:
        world.seed_initial_animals(player)
    player.last_passive = time.time()
    if getattr(player, "debug_mode", False):
        player.apply_debug_mode()
    player.last_day = time.time()
    weather.last_evap = time.time()
    buf = ""; game_over = False; paused = False; crashed = False; last_render = time.time(); last_auto_save = time.time()
    # Tab-completion state: index into _TAB_CMDS (-1 = inactive)
    _tab_idx = -1
    _TAB_CMDS = [
        tok for _raw, _ in SIDEBAR_COMMANDS
        for tok in [_raw.split("/")[0].split("<")[0].strip()]
        if tok and any(c.isalpha() for c in tok)
    ]
    player_died = False; death_reason = ""

    def refresh():
        nonlocal last_render; last_render = time.time()
        sp = SPD_NIGHT if player.time_of_day == "night" else SPD_DAY
        if player.wearing == "heavy_armor": sp *= 0.7
        # Line 1: position / biome
        # Line 2: vital stats + tool durabilities
        # Line 3: coins / weather / armor
        # Line 4 (optional): station HP
        has_adv_axe = player.inventory.get("advanced_axe", 0) > 0
        has_axe     = player.inventory.get("axe", 0) > 0
        has_pick    = player.inventory.get("pickaxe", 0) > 0
        hdr = [
            f"{'🌙 NIGHT' if player.time_of_day=='night' else '☀️ DAY'} | 📍@({player.x},{player.y}) | {'🌲 Forest' if biome_at(player.x,player.y)=='Forest' else '❄️ Arctic'} | 🧭{'↗️' if dist_to_border(player.x,player.y)>0 else '↙️'}{abs(int(dist_to_border(player.x,player.y)))}",
            (f"❤️{player.health:.0f} | 🍽️{player.hunger:.0f} | ⚡{int(player.energy)}" if is_light(player) else f"❤️{player.health:.0f} | 🍽️{player.hunger:.0f} | 💧{player.thirst:.0f} | ⚡{int(player.energy)} | 😴{int(player.fatigue)}"),
            f"🪙{player.coins:.0f} | 📚{player.inventory.get('textbook',0)} | {(weather.current if biome_at(player.x,player.y)=='Arctic' else ('☀️ CLEAR' if any(w in weather.current.upper() for w in ('ARCTIC', 'BLIZZARD', 'SNOW STORM', 'SNOWSTORM')) else weather.current)).upper()} | 🏆{int(player.points)}pts | {_temp_label(player.temp, player)}"
        ]
        # Tool durabilities on line 2
        if has_adv_axe and player.axe_dur > 0:
            hdr[1] += f" | 🪓{int((max(0,player.axe_dur)/TOOL_DUR_ADV)*100)}%"
        elif has_axe and player.axe_dur > 0:
            hdr[1] += f" | 🪓{int((max(0,player.axe_dur)/TOOL_DUR)*100)}%"
        if has_pick and player.pickaxe_dur > 0:
            hdr[1] += f" | ⛏️{int((max(0,player.pickaxe_dur)/TOOL_DUR)*100)}%"
        if player.wearing or any(player.inventory.get(a,0) > 0 for a in ["light_armor","medium_armor","heavy_armor"]):
            hdr[2] += " | 🛡️ " + (player.wearing or "None").replace("_"," ").title()
        player_ins = (CLOTHING_INSULATION.get(player.wearing_pants, 0) +
                      CLOTHING_INSULATION.get(player.wearing_shirt, 0))
        clothing_worn = []
        if player.wearing_pants: clothing_worn.append(f"👖{CLOTHING_INSULATION[player.wearing_pants]}")
        if player.wearing_shirt: clothing_worn.append(f"👕{CLOTHING_INSULATION[player.wearing_shirt]}")
        if biome_at(player.x, player.y) == "Arctic":
            req = player.arctic_insulation_req
            ins_str = f"🧊{player_ins:.0f}/{req:.0f}"
            hdr[1] += " | " + ins_str + (" ".join(clothing_worn) and (" | " + " ".join(clothing_worn)) or "")
        elif clothing_worn:
            hdr[1] += " | " + " ".join(clothing_worn)
        if player.spear_type and player.spear_dur > 0 and player.inventory.get(player.spear_type,0) > 0:
            sdef_h = SPEAR_DEFS.get(player.spear_type, {})
            hdr[1] += f" | 🗡️{int(max(0,player.spear_dur)/sdef_h.get('dur',100)*100)}%"
        if player.shield_type and player.shield_dur_blocks > 0:
            sdef_h2 = SHIELD_DEFS.get(player.shield_type, {})
            hdr[1] += f" | 🛡️{player.shield_dur_blocks}blk/{player.shield_dur_absorb}abs"
        if player.cat_following:
            _fcat = next((a for a in world.animals if a.get("type")=="cat" and a.get("_following_player")), None)
            _fl = _fcat.get("loyalty", 0) if _fcat else 0
            _dist_lbl = " (keeping distance)" if _fl <= -10 else ""
            hdr[2] += f" | 🐈 Cat: following (loyalty {_fl:+d}){_dist_lbl}"
        if player.on_fire:
            hdr[2] += " | 🔥 ON FIRE!"
        # Diseases line: show every active disease + stack count
        _dz_main = getattr(player, "diseases", {}) or {}
        if _dz_main:
            try:
                _dlbl_main = ", ".join(
                    DISEASE_DISPLAY.get(d, d) + (f" x{v.get('stacks',1)}" if v.get('stacks',1) > 1 else "")
                    for d, v in _dz_main.items()
                )
                hdr.append(f"☣️  Diseases: {_dlbl_main}")
            except Exception:
                pass
        if player.in_combat and player.combat:
            state = player.combat
            scan = [f"  ⚔️ COMBAT MODE — HP {int(player.health)}/{int(player.max_health)} | AP {state['player_ap']} | Segments {state['player_turns']} | {'Blocking' if state.get('blocking') else 'Ready'}"]
            scan.append("  Enemies:")
            for e in state['enemies']:
                status = "DEFEATED" if e['hp'] <= 0 else f"HP:{e['hp']} ATK:{e['atk']} DEF:{e['def']}"
                scan.append(f"   - {e['type'].replace('_',' ').title():<18} | {status}")
            scan.append("")
            scan.append("  Commands: a/attack, t/throw, block, flee, pass, status, pause")
            term.render_main(hdr, scan, msg, "Combat> ", buf, player, paused)
            return
        # Station HP line
        st_parts = []
        for st, hp in player.station_hp.items():
            if player.inventory.get(st, 0) > 0 and hp > 0:
                if "woodworking" in st: icon, short = "⚒️", "Woodwork"
                elif "sewing" in st: icon, short = "🪡", "Sewing"
                elif "furnace" in st: icon, short = "🔥", "Furnace"
                elif "smelter" in st: icon, short = "⚗️", "Smelter"
                elif "water_filter" in st: icon, short = "💧", "Water Filter"
                elif "liquifier" in st: icon, short = "🧪", "Liquifier"
                else: icon, short = "🏭", st.replace("_"," ").title()[:8]
                st_parts.append(f"{icon} {short}: {int(hp)} hp")
        if st_parts:
            st_line = "🏭 " + " | ".join(st_parts)
            try:
                cols, _ = os.get_terminal_size()
            except:
                cols = TERM_WIDTH
            hdr.extend(vwrap(st_line, cols))
        cluster_scan = []
        # Build set of animal positions to allow overriding clusters
        animal_positions = set()
        for a in world.animals:
            d_a = math.hypot(a["x"]-player.x, a["y"]-player.y)
            if d_a <= FOG_RADIUS:
                animal_positions.add((int(round(a["x"])), int(round(a["y"]))))

        for c, d in world.scan(player.x, player.y):
            # Skip clusters at positions where animals are present
            if tuple(c.get("pos", (0, 0))) in animal_positions:
                continue
            m = f"{(d*sp)/60.0:.1f}m"
            if c.get("meta",{}).get("locked"):
                tool_req = c["meta"].get("tool_req","")
                ic = "🔓" if (tool_req == "axe" and player.has_axe()) or player.inventory.get(tool_req,0) > 0 else "🔒"
            else:
                ic = "  "
            if c.get("is_identified"):
                col2 = display_item_name(c.get("real_item", ""))
            else:
                col2 = UNKNOWN_DISPLAY_MAP.get(UNKNOWN_CATEGORY_MAP.get(c.get("real_item", ""), ""), "❓ Unknown")
            # Burning clusters: show 🔥 FIRE during firestorm, 💨 Ash after
            if c.get("meta",{}).get("is_burning"):
                display_name = "🔥 Fire"
            elif c.get("meta",{}).get("is_ash"):
                display_name = "🔥 FIRE" if weather.firestorm_active else "💨 Ash Pile"
            else:
                display_name = c.get('name') or display_item_name(c.get('real_item', ''))
            # Use vfit so emoji in names/types don't overflow the column width
            name_col = vfit(display_name, 27)
            type_col = vfit(col2, 19)
            qty_s    = str(c['qty']).ljust(3)
            coord_str = f"@({c['pos'][0]},{c['pos'][1]})"
            cluster_scan.append(f"  {ic} {name_col} | {type_col} | {qty_s} | {m:<5} | {coord_str}")
        animal_scan = []
        nearby_animals = []
        for a in world.animals:
            d_a = math.hypot(a["x"]-player.x, a["y"]-player.y)
            if d_a <= FOG_RADIUS:
                nearby_animals.append((d_a, a))
        nearby_animals.sort(key=lambda x: x[0])
        if nearby_animals:
            counts = {}
            for _, a in nearby_animals:
                counts[a['type']] = counts.get(a['type'], 0) + 1
            summary = ", ".join(f"{counts[t]} {t.replace('_',' ').title()}" for t in sorted(counts, key=lambda k: (-counts[k], k)))
            animal_scan.append(f"  🐾 Nearby wildlife: {summary}")
            for d_a, a in nearby_animals[:4]:
                adef_s = ANIMAL_DEFS.get(a["type"], {})
                icon_s = adef_s.get("icon", "❓")
                state_s = "🏃 fleeing" if a.get("fleeing") else "🌿 nearby"
                atype_label = a["type"].replace("_"," ").title()
                if a["type"] == "grot":
                    icon_s = "👹"
                animal_scan.append(f"  {icon_s} {atype_label:<18} | {state_s:<12} | {d_a:.1f} tiles | HP:{a['hp']} | @({a['x']:.0f},{a['y']:.0f})")
        # Nearby houses — shown on the map as their own properly-sized
        # structures (footprint × footprint), NOT as tiny grots-sized clusters.
        house_scan = []
        for h in world.houses:
            if h.get("hp", 0) <= 0: continue
            hdef_s = HOUSE_DEFS.get(h["type"], {})
            fp_s = hdef_s.get("footprint", 1)
            hcx = h["x"] + fp_s / 2.0; hcy = h["y"] + fp_s / 2.0
            d_h = math.hypot(hcx - player.x, hcy - player.y)
            if d_h > FOG_RADIUS + fp_s: continue
            emoji_h = hdef_s.get("emoji", "🏠")
            hname_s = h["type"].replace("_", " ").title()
            inside_lbl = " (you are inside)" if getattr(player, "inside_house_id", None) == h["id"] else ""
            here_lbl = " — type 'enter'" if _house_find_at(world, int(player.x), int(player.y)) is h else ""
            house_scan.append(f"  {emoji_h} {hname_s:<14} | 🏠 shelter {fp_s}×{fp_s} | HP:{int(h.get('hp',0))}/{int(h.get('max_hp',0))} | {d_h:.1f} tiles | @({h['x']},{h['y']}){inside_lbl}{here_lbl}")
        # Build scan display - show cluster info even when paused
        if cluster_scan or animal_scan or house_scan:
            scan_header = [f"  {'WHAT IT IS':<30} {'WHAT YOU GET':<21} {'AMT':<4} {'DIST':<6} COORDINATES"]
            scan = animal_scan + house_scan + scan_header + cluster_scan
        else:
            scan = ["  🔍 Nothing nearby."]
        term.render_main(hdr, scan, msg, "> ", buf, player, paused)

    def flash_damage(dmg=0):
        player._damage_flash_pending = False
        if sound and sound.enabled: sound.play_damage(dmg)
        for _ in range(3):
            refresh(); term.flash_red()

    def flash_pending_damage():
        if getattr(player, "_damage_flash_pending", False):
            flash_damage()

    try:
        while not game_over:
            was_crafting = bool(player.active_tasks)
            # ---- Async INSPECT finalization ----
            if getattr(player, "inspect_pending", None) and not paused and not player.in_combat:
                _had_inspect = True
                _finalize_inspect(player, world, msg)
                if _had_inspect and not getattr(player, "inspect_pending", None):
                    if sound and sound.enabled: sound.stop_inspect()
                # Quick-tutorial inspect-result hook
                if getattr(player, "_qt_inspect_finished", False):
                    qt_on_event(term, player, world, "inspect_result",
                                success=bool(getattr(player, "_qt_last_inspect_success", False)))
                    player._qt_inspect_finished = False
                msg = msg[-3:]

            # ---- Async GATHER ALL finalization ----
            ga = getattr(player, "gather_all", None)
            if ga and not paused and not player.in_combat and time.time() >= ga["end"]:
                gx, gy = ga["x"], ga["y"]
                qty = ga["qty"]; energy_cost = ga["energy_cost"]
                cl = world.clusters.get((gx, gy))
                if not cl or cl.get("qty", 0) <= 0:
                    msg.append("🔍 Gather all: nothing left to collect.")
                    if sound and sound.enabled: sound.stop_gather()
                    player.gather_all = None
                else:
                    real = cl["real_item"]
                    if not cl["is_identified"]:
                        cat = UNKNOWN_CATEGORY_MAP.get(real, "misc")
                        inv_key, inv_entry = player.get_unknown_entry(cat)
                        inv_entry["qty"] += qty; inv_entry["items"].extend([real] * qty)
                        inv_entry["inspect_tries"] = max(inv_entry.get("inspect_tries", 0), cl.get("inspection_attempts", 0))
                        disp = UNKNOWN_DISPLAY_MAP.get(cat, f"❓ Unknown {cat.title()}")
                        msg.append(f"➕ {qty} {disp}")
                    else:
                        player.inventory[real] = player.inventory.get(real, 0) + qty
                        msg.append(f"➕ {qty} {display_item_name(real)} (gathered all)")
                    if real == "wood":
                        player.wood_gathered += qty
                        for _ in range(qty):
                            used, brk = player.use_axe(1)
                            if brk:
                                msg.append(brk)
                                if sound and sound.enabled: sound.play_tool_break()
                                break
                    if real in BERRY_ITEMS: player.berries_gathered += qty
                    if real in MUSHROOM_ITEMS: player.mushrooms_gathered += qty
                    if real == "bee_hive": player.bee_hives_collected += qty
                    if real == "spider_silk": player.spider_silk_gathered += qty
                    if real == "rock":
                        for _ in range(qty):
                            used, brk = player.use_pickaxe(1)
                            if brk:
                                msg.append(brk)
                                if sound and sound.enabled: sound.play_tool_break()
                                break
                    if real == "rock":
                        for _ in range(qty):
                            roll = random.random()
                            if roll < 0.005:
                                player.inventory["gold_ore"] = player.inventory.get("gold_ore", 0) + 1
                                msg.append("✨ Gold Ore!")
                            elif roll < 0.105:
                                player.inventory["copper_ore"] = player.inventory.get("copper_ore", 0) + 1
                                msg.append("🔶 Copper Ore!")
                            elif roll < 0.255:
                                player.inventory["iron_ore"] = player.inventory.get("iron_ore", 0) + 1
                                msg.append("⚙️ Iron Ore!")
                    if cl.get("meta", {}).get("hazard"):
                        hk = cl["meta"].get("hazard_key"); h = HAZARDS.get(hk, {}); base_dmg = h.get("dmg", 0)
                        hits = 0; blocked = 0; total_dmg = 0; broken = False
                        for _ in range(qty):
                            if random.random() < h.get("chance", 0.5):
                                final_dmg = base_dmg
                                if player.wearing:
                                    reduction = player.armor_hazard_reduction(hk)
                                    final_dmg = max(0, base_dmg - reduction)
                                    if final_dmg < base_dmg:
                                        player.armor_dur -= final_dmg
                                        if player.armor_dur <= 0:
                                            player.wearing = None
                                            player.armor_dur = 0
                                            broken = True
                                if final_dmg > 0:
                                    player.note_damage_cause(f"Hit by {hk.replace('_', ' ').title()}")
                                    player.health -= final_dmg
                                    total_dmg += final_dmg
                                    hits += 1
                                else:
                                    blocked += 1
                        if hits > 0:
                            msg.append(f"💥 Hit by {hk.replace('_', ' ').title()} {hits} times! -{total_dmg} HP")
                            flash_damage(total_dmg)
                        elif blocked > 0:
                            msg.append("🛡️ Attack blocked by armor!")
                        if broken:
                            msg.append("💥 Armor broke!")
                    # Dirt tiles only partially deplete — halve remaining qty (round up)
                    if real == "dirt":
                        import math as _m
                        rem = cl.get("qty", 0)
                        if rem <= 1:
                            cl["qty"] = 0
                            world.depleted.add((gx, gy))
                            if (gx, gy) in world.clusters:
                                del world.clusters[(gx, gy)]
                        else:
                            cl["qty"] = _m.ceil(rem / 2)
                            msg.append(f"🟫 Dirt patch thinned — {cl['qty']} remaining.")
                    else:
                        # Partial gathers (energy-limited) leave the remainder behind.
                        cl["qty"] = max(0, cl.get("qty", 0) - qty)
                        if cl["qty"] <= 0:
                            world.depleted.add((gx, gy))
                            if (gx, gy) in world.clusters:
                                del world.clusters[(gx, gy)]

                    player.energy = max(0, player.energy - energy_cost)
                    msg.append(f"✅ Gathering finished! Energy cost = {energy_cost}.")
                    if sound and sound.enabled:
                        sound.stop_gather()
                        if real == "wood":
                            sound.play_chop()
                        elif real in ("rock", "ice_chunk"):
                            sound.play_pickaxe()
                        else:
                            sound.play_collect()
                    player.gather_all = None
                    qt_on_event(term, player, world, "gather_all_done", item=real)
                msg = msg[-3:]


            # Advance the unpaused playtime clock (used for cat pet-cooldown etc.)
            _uc_now = time.time()
            if not paused:
                player.unpaused_clock += min(_uc_now - getattr(player, "_last_uc", _uc_now), 1.0)
            player._last_uc = _uc_now

            if not paused:
                res = player.update_passive()
                unlocked = was_crafting and not player.active_tasks
                if unlocked and sound and sound.enabled: sound.stop_craft()
                if unlocked and getattr(player, "qt_last_finished", None):
                    qt_on_event(term, player, world, "craft_done", item=player.qt_last_finished)
                    player.qt_last_finished = None

                if res not in ("dead",) and not player.in_combat:
                    if getattr(player, "difficulty_mult", NORMAL_HUNGER_MULT) <= BEGINNER_HUNGER_MULT:
                        world.animals = [a for a in world.animals if a.get("type") not in ("grot", "grot_leader")]
                    # Auto-trigger GRID MODE if any grot sees the player
                    grot_sees = []
                    for a in world.animals:
                        if a.get("type") not in ("grot", "grot_leader") or a.get("hp", 0) <= 0:
                            continue
                        vm = a.get("vision_max", 10)
                        if math.hypot(a["x"] - player.x, a["y"] - player.y) <= vm:
                            grot_sees.append(a)
                    if grot_sees and time.time() > player.flee_until:
                        for t in player.active_tasks:
                            t["paused_remaining"] = max(0, int(t["end"] - time.time()))
                        nearby_targets = [a for a in world.animals if math.hypot(a["x"]-player.x, a["y"]-player.y) <= 12.0]
                        if not nearby_targets:
                            nearby_targets = grot_sees
                        msg.append("👹 A grot spotted you! Entering GRID MODE!")
                        _flee_cat_on_combat(player, world, msg)
                        _unlock_and_show_tutorial(term, player, "grot_combat")
                        grid_msgs = run_grid_mode(term, player, world, nearby_targets, msg)
                        for gm in grid_msgs[-3:]: msg.append(gm)
                        msg = msg[-3:]
                    else:
                        hostile_nearby = [a for a in world.animals if a.get("atk",0) > 0 and math.hypot(a["x"]-player.x, a["y"]-player.y) <= 1.0]
                        if hostile_nearby and time.time() > player.flee_until:
                            # Pause any active crafting
                            for t in player.active_tasks:
                                t["paused_remaining"] = max(0, int(t["end"] - time.time()))
                            _flee_cat_on_combat(player, world, msg)
                            start_turn_based_combat(player, world, hostile_nearby, msg)
                if res == "time_shift":
                    icon = "🌙" if player.time_of_day == "night" else "☀️"
                    label = "NIGHT" if player.time_of_day == "night" else "DAY"
                    hunger_loss = int(round(DAY_NIGHT_HUNGER_LOSS * getattr(player, "difficulty_mult", NORMAL_HUNGER_MULT)))
                    msg.append(f"⏰ TIME SHIFT: It is now {icon} {label}! (-{hunger_loss}🍽️)")
                    world.time_of_day = player.time_of_day
                    if player.time_of_day == "day":
                        player.days_survived += 1
                        player.hidden_xp += 50
                        if not player.grace_period_over and player.days_survived >= 1:
                            player.grace_period_over = True
                    # Daily world events
                    flood_msg = world.check_flood()
                    if flood_msg: msg.append(flood_msg)
                    overpop_msg = world.check_overpopulation()
                    if overpop_msg: msg.append(overpop_msg)
                    msg = msg[-3:]
                elif res and res != "dead" and not res.startswith("✅ Finished"):
                    msg.append(res); msg = msg[-3:]
                # Flash red on starvation or dehydration tick
                if getattr(player, '_starvation_flash', False):
                    player._starvation_flash = False
                    msg.append("🍽️ STARVATION! -10 HP from hunger!"); msg = msg[-3:]
                    refresh(); term.flash_red()
                if getattr(player, '_thirst_flash', False):
                    player._thirst_flash = False
                    msg.append("💧 DEHYDRATING! Taking damage from thirst!"); msg = msg[-3:]
                    refresh(); term.flash_red()
                # Frostberry thaw message
                if getattr(player, '_frostberry_thaw_msg', 0):
                    qty = player._frostberry_thaw_msg; player._frostberry_thaw_msg = 0
                    msg.append(f"🌡️ Warmth thawed {qty} frostberries into wild berries!"); msg = msg[-3:]
                # Freezing water thaw message
                if getattr(player, '_freezing_water_thaw_msg', 0):
                    qty = player._freezing_water_thaw_msg; player._freezing_water_thaw_msg = 0
                    msg.append(f"💧 Warmth melted {qty} freezing water into fresh water!"); msg = msg[-3:]
                if unlocked:
                    msg.append("🔓 Movement unlocked. Arrow keys are active again."); msg = msg[-3:]
                world.regen()
                world.update_fire(weather, player)
                now = time.time()

                # Keep the battle track in sync with the actual combat state.
                if sound and getattr(sound, "enabled", False):
                    delay_until = getattr(player, "_combat_music_delay_until", 0.0)
                    if delay_until and time.time() >= delay_until:
                        player._combat_music_delay_until = 0.0
                        sound.start_combat_bgm()
                    sound.tick_combat_bgm(bool(getattr(player, "in_combat", False)))

                # Park distant world data in SQLite (and revive it on approach).
                world.offload_distant(player)

                # Water evaporation: every 30s without rain
                if now - weather.last_evap >= 30.0:
                    weather.last_evap = now
                    if not weather.is_raining():
                        world.apply_evaporation()

                world.spawn_animals(player)
                world.move_animals(player)
                world.mature_animals()
                world.update_animal_survival()
                world.deplete_resources_by_animals()

                # ---- Cat companion tick ----
                _tick_cat_companion(player, world, msg)
                # ---- Ambient animal sounds tick ----
                _tick_animal_sounds(player, world, sound)
                # ---- Drain queued disease messages ----
                _pdm = getattr(player, "pending_disease_msgs", None)
                if _pdm:
                    msg.extend(_pdm); msg = msg[-3:]
                    player.pending_disease_msgs = []
                # ---- House tick ----
                _update_houses(world, player, weather, msg, now)

                # Firestorm end check
                if weather.firestorm_active:
                    if weather.is_raining():
                        weather.firestorm_active = False; player.on_fire = False
                        msg.append("🌧️ Rain has put out the firestorm!"); msg = msg[-3:]
                    else:
                        ash_count = sum(1 for c in world.clusters.values() if c.get("meta",{}).get("is_ash"))
                        other_count = sum(1 for c in world.clusters.values() if not c.get("meta",{}).get("is_ash"))
                        if ash_count >= max(1, other_count):
                            weather.firestorm_active = False
                            msg.append("🔥 Firestorm has burned itself out."); msg = msg[-3:]

                # On-fire periodic warning
                if player.on_fire and int(now) % 4 == 0:
                    msg.append("🔥 YOU'RE ON FIRE! -5 HP/sec — move to water!"); msg = msg[-3:]

                # Stat warnings — low/critical health, hunger, thirst, fatigue
                if not hasattr(player, '_last_stat_warn'): player._last_stat_warn = 0.0
                if not hasattr(player, '_last_nutrition_warn'): player._last_nutrition_warn = 0.0
                if now - player._last_stat_warn >= 8.0:
                    player._last_stat_warn = now
                    # Health warnings
                    if player.health < 10:
                        msg.append("💀 CRITICAL HEALTH! Use bandages or rest immediately!"); msg = msg[-3:]
                        refresh(); term.flash_red()
                    elif player.health < 30:
                        msg.append("❤️ Very low health! Consider bandaging or resting."); msg = msg[-3:]
                    elif player.health < 50:
                        msg.append("❤️ Low health. Watch out!"); msg = msg[-3:]
                    # Fatigue warnings
                    if player.fatigue < 10:
                        msg.append("😴 Very low fatigue! Can't gather or craft. Rest now!"); msg = msg[-3:]
                # Fatigue-zero popup — show once each time fatigue bottoms out
                if getattr(player, "_fatigue_zero_popup", False):
                    player._fatigue_zero_popup = False
                    try:
                        term.show_menu(["", "  😴  REST NOW!", "", "  Your fatigue has hit 0 — you can't walk, gather, or craft.", "  Type 'rest' to recover.", "", "  Press any key to continue."])
                        term.get_key_no_flush(30.0)
                        player.last_passive = time.time()
                    except Exception:
                        msg.append("😴 REST NOW! Fatigue is 0."); msg = msg[-3:]
                if now - player._last_nutrition_warn >= 30.0:
                    player._last_nutrition_warn = now
                    # Hunger warnings
                    if player.hunger < 10:
                        msg.append("🍽️ CRITICAL HUNGER! Starving — eat NOW or lose HP!"); msg = msg[-3:]
                        refresh(); term.flash_red()
                    elif player.hunger < 30:
                        msg.append("🍽️ Very low hunger! Eat soon."); msg = msg[-3:]
                    elif player.hunger < 50:
                        msg.append("🍽️ Low hunger. Find food."); msg = msg[-3:]
                    # Thirst warnings
                    if player.thirst < 10:
                        msg.append("💧 CRITICAL THIRST! Dehydrating — drink water NOW!"); msg = msg[-3:]
                        refresh(); term.flash_red()
                    elif player.thirst < 30:
                        msg.append("💧 Very low thirst! Drink soon."); msg = msg[-3:]
                    elif player.thirst < 50:
                        msg.append("💧 Low thirst. Find water."); msg = msg[-3:]
                if player.health < 30 and not paused:
                    if not hasattr(player, '_last_low_hp_flash'): player._last_low_hp_flash = 0.0
                    if now - player._last_low_hp_flash >= 5.0:
                        player._last_low_hp_flash = now
                        refresh(); term.flash_red()

                # Achievement checks every 5 seconds
                if not hasattr(player, '_last_ach_check'): player._last_ach_check = 0.0
                if now - player._last_ach_check >= 5.0:
                    player._last_ach_check = now
                    cur_pt = player.total_playtime + (now - player.session_start)
                    earned_set = set(player.earned_achievements)
                    for aid, ach in ACHIEVEMENTS.items():
                        if aid in earned_set: continue
                        if check_achievement_cond(aid, player, cur_pt):
                            player.earned_achievements.append(aid)
                            player.points += ach["pts"]
                            player.coins += ach["coins"]
                            msg.append(f"🏆 Achievement: {ach['name']}! +{ach['pts']}pts +{ach['coins']}🪙")
                    msg = msg[-3:]
                    try: check_major_goals(term, player)
                    except Exception: pass
                    try: check_lore_intro(term, player)
                    except Exception: pass

                if now - player.last_weather_check >= 300:
                    player.last_weather_check = now
                    w = weather.update_hourly(world, player)
                    if w:
                        msg.append(w); msg = msg[-3:]
                        if weather.lightning_hit or weather.tornado_hit:
                            refresh()
                            if weather.lightning_hit:
                                for _ in range(3):
                                    term.flash_white()
                                if sound and sound.enabled:
                                    sound.play_lightning()
                            if weather.tornado_hit:
                                term.flash_red()
                                if sound and sound.enabled:
                                    sound.play_tornado()
                    # Weather-change tutorial: fire when current weather changes
                    cur_w = getattr(weather, "current", None)
                    prev_w = getattr(player, "_prev_weather_for_tutorial", None)
                    if cur_w and cur_w != prev_w:
                        player._prev_weather_for_tutorial = cur_w
                        _unlock_and_show_tutorial(term, player, "weather_hazard")
                # Fatigue-dip tutorial: trigger first time fatigue drops below 50
                if player.fatigue < 50 and "rest_fatigue" not in getattr(player, "tutorials_unlocked", []):
                    _unlock_and_show_tutorial(term, player, "rest_fatigue")
                # Drain any queued tutorials (e.g. first spear craft)
                pending = getattr(player, "pending_tutorials", None)
                if pending:
                    for _tk in list(pending):
                        _unlock_and_show_tutorial(term, player, _tk)
                    player.pending_tutorials = []
                update_quests(player, weather, world, msg, term)
                msg = msg[-3:]
                if save_path and now - last_auto_save >= 30.0:
                    last_auto_save = now
                    try:
                        do_save(player, world, save_path, biome, paused=False)
                    except Exception as e:
                        msg.append(f"⚠️ Auto-save failed: {e}"); msg = msg[-3:]
            else:
                res = None
                unlocked = False
                now = time.time()
            if sound and sound.enabled and not paused and player.health <= 25:
                _lh_interval = max(0.38, 4.0 * (player.health / 25.0))
                if time.time() - sound.last_low_health > _lh_interval:
                    sound.play_low_health()
                    sound.last_low_health = time.time()
            if player.health <= 0:
                if player.hunger <= 0:
                    death_reason = "Starvation"
                elif player.thirst <= 0:
                    death_reason = "Dehydration"
                elif player.resting and player.rest_mode in ("floor","house_floor","house_bed"):
                    death_reason = "Perished while resting on the cold ground"
                else:
                    death_reason = player.last_damage_cause or "Fatal injuries"
                if sound and sound.enabled:
                    sound.play_death()
                flash_pending_damage()
                term.render_main(["💀 GAME OVER"],[f"📍@({player.x},{player.y})"],
                                 [f"You have perished. Cause: {death_reason}."],"","",player, paused)
                _death_screen_start = time.time()
                while time.time() - _death_screen_start < 5.0:
                    time.sleep(0.1)
                _revived = False
                try:
                    _revived = death_room_sequence(term, player, world, sound, death_reason)
                except Exception as _dre:
                    _revived = False
                if _revived:
                    freeze_blocking_time(player, world, weather, time.time() - _death_screen_start)
                    death_reason = ""
                    msg.append("✨ Hildegard Dhanvantari has revived you."); msg = msg[-3:]
                    rn = True
                    continue
                player_died = True
                break

            rn = False
            # Quick tutorial: time-based and event-driven transitions
            qt_tick(term, player, world)
            step_msg = None
            if not paused and player.auto_walk_target:
                step_msg = player.auto_walk_step(world)
                if step_msg:
                    msg.append(step_msg); msg = msg[-3:]; rn = True
                    if "💥" in step_msg or "Hazard hit" in step_msg:
                        flash_damage()
                    if "Arrived at" in step_msg:
                        qt_on_event(term, player, world, "arrived_walk")

            key = term.get_key() if not step_msg else None
            if player.auto_walk_target and key is not None:
                player.auto_walk_target = None
            if player.in_combat and player.auto_walk_target:
                player.auto_walk_target = None
                rn = True

            # ---- MOVEMENT (blocked while crafting and combat) ----
            if key in ['UP','DOWN','LEFT','RIGHT'] and not paused and not player.in_combat:
                if player.resting:
                    msg.append("😴 Can't move while resting. Type 'rest' to stop first."); msg = msg[-3:]; rn = True
                    continue
                if player.active_tasks:
                    msg.append("🔨 Can't move while crafting! Wait for it to finish, or use the 'cancel' command."); msg = msg[-3:]; rn = True
                elif getattr(player, "gather_all", None):
                    msg.append("⏳ Can't move while gathering all. Wait for it to finish."); msg = msg[-3:]; rn = True
                elif player.fatigue <= 0:
                    msg.append("😴 Too exhausted to walk. Rest now!"); msg = msg[-3:]; rn = True
                else:
                    dx = 1 if key=='RIGHT' else -1 if key=='LEFT' else 0
                    dy = -1 if key=='UP' else 1 if key=='DOWN' else 0
                    prev_biome = biome_at(player.x, player.y)
                    player.last_move_time = time.time()
                    m, d = player.travel_to(dx, dy)
                    if d == -1: msg.append("😮‍💨 Exhausted!")
                    elif d > 0.01:
                        cur_biome = biome_at(player.x, player.y)
                        if cur_biome != prev_biome:
                            if cur_biome == "Arctic":
                                msg.append("❄️ You've left the Forest and entered the Arctic wilderness!")
                                player.arctic_visited = True
                            else:
                                msg.append("🌲 You've returned to the Forest!")
                            if sound and sound.enabled:
                                sound.play_environment(cur_biome)
                        # Extinguish fire if stepping on/near water
                        if player.on_fire:
                            nearby_cl = world.clusters.get((int(player.x), int(player.y)))
                            if nearby_cl and nearby_cl.get("real_item") in ("water","fresh_water","dirty_water","freezing_water","freezing_dirty_water"):
                                player.on_fire = False
                                msg.append("💧 Fire extinguished by water!")
                        if sound and sound.enabled:
                            sound.play_walk()
                        # House nearby hint
                        _nearby_h = _house_find_at(world, int(player.x), int(player.y))
                        if _nearby_h and not player.inside_house_id:
                            msg.append(f"🏠 You're inside a {_nearby_h['type'].replace('_',' ')} footprint. Type 'enter' to go inside.")
                        msg = msg[-3:]; rn = True; time.sleep(0.05)

            elif key in ('\r','\n'):
                cmd = buf.strip().lower(); buf = ""; rn = True
                if not cmd: continue
                parts = cmd.split(); act = parts[0]; arg = " ".join(parts[1:])
                # ---- Quantity parsing: "eat all", "eat 5", "buy 5", "sell all",
                # "craft 3", "drink 5", etc. qty_req is 1 (default), an int N, or
                # the string "all". The quantity token is stripped from arg so the
                # downstream item lookup still works.
                qty_req = 1
                if act in ("eat", "drink", "buy", "sell", "craft", "feed"):
                    _qtoks = arg.split()
                    if _qtoks and _qtoks[0] in ("all", "everything", "max"):
                        qty_req = "all"; arg = " ".join(_qtoks[1:])
                    elif _qtoks and _qtoks[0].lstrip("-").isdigit():
                        qty_req = max(1, int(_qtoks[0])); arg = " ".join(_qtoks[1:])
                # Standalone "filter" → alias for "craft filter"
                if act == "filter" and not arg: act = "craft"; arg = "filter"

                # If in turn-based combat, route commands to the combat handler first
                if player.in_combat:
                    handled = handle_combat_command(player, world, act, arg, msg, term=term)
                    msg = msg[-3:]
                    if handled:
                        rn = True
                        continue

                # If gather-all is in progress, block state-changing commands (read-only allowed).
                LOCKED_DURING_GATHER = {"craft","rest","gather","hunt","attack","a","s","strike",
                                        "t","throw","trap","traps","eat","drink","fish","walk","go","pet","feed",
                                        "buy","sell","equip","unequip","wear","remove","bandage",
                                        "bandages","poison","inspect","identify"}
                # Exception: combat pauses gather-all, but the player must still be
                # able to equip/swap gear and use bandages mid-fight.
                COMBAT_EXEMPT = {"equip","unequip","wear","remove","bandage","bandages"}
                if getattr(player, "gather_all", None) and act in LOCKED_DURING_GATHER \
                   and not (player.in_combat and act in COMBAT_EXEMPT):
                    msg.append("⏳ Can't do that while gathering all. Wait for it to finish.")
                    msg = msg[-3:]; rn = True; continue

                # If resting, block state-changing commands (same lock as crafting).
                LOCKED_DURING_REST = {"craft","gather","hunt","attack","a","s","strike",
                                      "t","throw","trap","traps","eat","drink","fish","walk","go","pet","feed",
                                      "buy","sell","equip","unequip","wear","remove","bandage",
                                      "bandages","poison","inspect","identify"}
                if getattr(player, "resting", False) and act in LOCKED_DURING_REST \
                   and not (player.in_combat and act in COMBAT_EXEMPT):
                    msg.append("😴 Can't do that while resting. Type 'rest' to stop first.")
                    msg = msg[-3:]; rn = True; continue

                # ---- HELP ----
                if act == "help":
                    page_keys = list(HELP_PAGES.keys())
                    # Paginated help: show TOC, then page content in terminal-height pages
                    def _help_show_toc():
                        try: _tw = os.get_terminal_size().columns
                        except Exception: _tw = TERM_WIDTH
                        _tw = max(40, _tw)
                        lines = ["📖 HELP MENU", "─" * _tw]
                        for i, k in enumerate(page_keys, 1):
                            lines.append(f"  {i}. {k}")
                        lines += ["", "  Press a number to open a page.  0 or Enter to close."]
                        term.show_menu(lines)
                    def _help_show_page(page_key, sub_page=0):
                        try: _tw, _th = os.get_terminal_size()
                        except Exception: _tw, _th = TERM_WIDTH, 24
                        _tw = max(40, _tw); _th = max(6, _th)
                        content_lines = HELP_PAGES[page_key].split('\n')
                        page_h = max(4, _th - 5)   # lines of content per screen
                        total_sub = max(1, (len(content_lines) + page_h - 1) // page_h)
                        sub_page = max(0, min(sub_page, total_sub - 1))
                        start = sub_page * page_h
                        visible = content_lines[start: start + page_h]
                        idx_num = page_keys.index(page_key) + 1
                        header = f"📖 {page_key}  [{sub_page+1}/{total_sub}]"
                        nav = "  N=next page  P=prev page  B=back to menu  Q=close"
                        out_lines = [header, "─" * _tw] + visible
                        while len(out_lines) < _th - 1:
                            out_lines.append("")
                        out_lines.append(nav)
                        term.show_menu(out_lines)
                        return total_sub, sub_page
                    _help_show_toc()
                    _cur_page_key  = None
                    _cur_sub_page  = 0
                    _total_sub     = 1
                    while True:
                        ch = term.get_key_no_flush(0.5)
                        if ch is None:
                            continue
                        if _cur_page_key is None:
                            # TOC mode
                            if ch in ('\r', '\n', '0', 'ESC', 'q', 'Q'):
                                sys.stdout.write("\033[2J"); sys.stdout.flush(); break
                            if ch and ch.isdigit():
                                idx = int(ch)
                                if 1 <= idx <= len(page_keys):
                                    _cur_page_key = page_keys[idx - 1]
                                    _cur_sub_page = 0
                                    _total_sub, _cur_sub_page = _help_show_page(_cur_page_key, _cur_sub_page)
                        else:
                            # Page-view mode
                            if ch in ('b', 'B', 'ESC'):
                                _cur_page_key = None
                                _help_show_toc()
                            elif ch in ('q', 'Q', '\r', '\n', '0'):
                                sys.stdout.write("\033[2J"); sys.stdout.flush(); break
                            elif ch in ('n', 'N', 'DOWN'):
                                if _cur_sub_page < _total_sub - 1:
                                    _cur_sub_page += 1
                                _total_sub, _cur_sub_page = _help_show_page(_cur_page_key, _cur_sub_page)
                            elif ch in ('p', 'P', 'UP'):
                                if _cur_sub_page > 0:
                                    _cur_sub_page -= 1
                                _total_sub, _cur_sub_page = _help_show_page(_cur_page_key, _cur_sub_page)
                            elif ch and ch.isdigit():
                                idx = int(ch)
                                if 1 <= idx <= len(page_keys):
                                    _cur_page_key = page_keys[idx - 1]
                                    _cur_sub_page = 0
                                    _total_sub, _cur_sub_page = _help_show_page(_cur_page_key, _cur_sub_page)
                    rn = True
                # ---- TUTORIALS (re-read unlocked tutorials) ----
                elif act in ("tutorials", "tutorial"):
                    if not hasattr(player, "tutorials_unlocked") or player.tutorials_unlocked is None:
                        player.tutorials_unlocked = []
                    unlocked = [k for k in TUTORIALS.keys() if k in player.tutorials_unlocked]
                    if not unlocked:
                        msg.append("\U0001f4dc No tutorials unlocked yet. Keep playing \u2014 they'll pop up the first time you try new things!")
                        msg = msg[-3:]; rn = True; continue
                    arg_l = (arg or "").strip()
                    if arg_l.isdigit():
                        idx = int(arg_l)
                        if 1 <= idx <= len(unlocked):
                            _show_tutorial(term, player, unlocked[idx-1])
                        else:
                            msg.append(f"\u274c No tutorial #{idx}. You have {len(unlocked)} unlocked.")
                            msg = msg[-3:]
                        rn = True; continue
                    menu_lines = ["\U0001f4dc TUTORIALS", "\u2500"*TERM_WIDTH]
                    for i, k in enumerate(unlocked, 1):
                        menu_lines.append(f"  {i}. {TUTORIALS[k]['title']}")
                    menu_lines += ["", "  Press a number key. Press Enter to close."]
                    term.show_menu(menu_lines)
                    while True:
                        ch = term.get_key_no_flush(0.5)
                        if ch in ('\r','\n','ESC'):
                            sys.stdout.write("\033[2J"); sys.stdout.flush(); break
                        if ch and ch.isdigit():
                            i2 = int(ch)
                            if 1 <= i2 <= len(unlocked):
                                _show_tutorial(term, player, unlocked[i2-1]); break
                    rn = True


                # ---- PAUSE / RESUME ----
                elif act in ("pause","resume"):
                    # Sub-command: 'pause crafting' / 'resume crafting' freezes
                    # only the active crafting (and gather-all) tasks without
                    # pausing time, weather, or the rest of the world.
                    arg_l = (arg or "").strip().lower()
                    if arg_l in ("craft", "crafting", "craft all", "all"):
                        if act == "pause":
                            ga = getattr(player, "gather_all", None)
                            any_paused = False
                            now_pc = time.time()
                            for t in player.active_tasks:
                                if "paused_remaining" not in t:
                                    t["paused_remaining"] = max(0, int(t["end"] - now_pc))
                                    any_paused = True
                            if ga and "paused_remaining" not in ga:
                                ga["paused_remaining"] = max(0, int(ga["end"] - now_pc))
                                any_paused = True
                            if any_paused:
                                if sound and sound.enabled:
                                    sound.stop_craft()
                                    sound.stop_gather()
                                msg.append("⏸️ Crafting paused. Type 'resume crafting' to continue. (Time keeps flowing!)")
                            elif player.active_tasks or ga:
                                msg.append("⏸️ Crafting is already paused.")
                            else:
                                msg.append("ℹ️ No crafting task to pause.")
                        else:  # resume crafting
                            had_any = False
                            for t in player.active_tasks:
                                if "paused_remaining" in t:
                                    had_any = True
                            ga = getattr(player, "gather_all", None)
                            if ga and "paused_remaining" in ga:
                                had_any = True
                            if had_any:
                                _resume_paused_crafting(player)
                                msg.append("▶️ Crafting resumed.")
                            else:
                                msg.append("ℹ️ No paused crafting to resume.")
                        msg = msg[-3:]; rn = True; continue
                    if act == "resume" and not arg_l and not paused:
                        had_any = False
                        for t in player.active_tasks:
                            if "paused_remaining" in t:
                                had_any = True
                        ga = getattr(player, "gather_all", None)
                        if ga and "paused_remaining" in ga:
                            had_any = True
                        if had_any:
                            _resume_paused_crafting(player)
                            msg.append("▶️ Crafting resumed.")
                            msg = msg[-3:]; rn = True; continue
                    if act == "pause":
                        if paused:
                            msg.append("⏸️ Already paused. Type 'resume' to continue.")
                        else:
                            paused = True
                            player.pause_started = time.time()
                            for t in player.active_tasks:
                                t["paused_remaining"] = max(0, int(t["end"] - player.pause_started))
                            msg.append("⏸️ Game paused. Time, weather, and auto-walk are frozen.")
                            if sound and sound.enabled:
                                sound.duck_volume()
                                sound.stop_all_loops()
                    else:
                        if not paused:
                            msg.append("▶️ Game is not paused. Type 'pause' to freeze the game.")
                        else:
                            paused = False
                            if sound and sound.enabled: sound.restore_volume()
                            now = time.time()
                            pause_duration = now - player.pause_started if player.pause_started else 0.0
                            msg.append("▶️ Resuming game. Time and events continue.")
                            player.last_passive = now
                            player.last_day = now
                            player.last_weather_check = now
                            # Accumulate playtime from before the pause, then reset
                            if player.pause_started and player.session_start < player.pause_started:
                                player.total_playtime += player.pause_started - player.session_start
                            player.session_start = now
                            if player.resting and player.rest_last > 0:
                                player.rest_last = now
                            if player.pause_started and pause_duration > 0:
                                for t in player.active_tasks:
                                    if "paused_remaining" not in t:
                                        t["end"] += pause_duration
                                if getattr(player, "detour_until", 0) > 0:
                                    player.detour_until += pause_duration
                            player.pause_started = 0.0
                            _resume_paused_crafting(player)
                            if hasattr(player, '_last_ach_check'):
                                player._last_ach_check = now
                            weather.last_evap = now
                            weather.last_lightning = now
                            world.last_regen = now
                            world.last_spawn = now
                            world.last_young_spawn = now
                            world.last_survival_check = now
                            world.last_resource_depletion = now
                    msg = msg[-3:]

                # ---- INVENTORY ----
                elif act in ("inv","inventory"):
                    out = ["🎒 INVENTORY", "─"*TERM_WIDTH, ""]
                    # Collect regular inventory items for grid layout
                    items_grid = []
                    for k,v in sorted(player.inventory.items()):
                        if k.startswith("unknown_"): continue
                        if isinstance(v,int) and v > 0:
                            items_grid.append((display_item_name(k), str(v)))

                    # Layout items in grid columns. Use visual-width helpers so emoji
                    # don't break alignment, and add generous gutters between columns.
                    if items_grid:
                        try:
                            cols_term, rows_term = os.get_terminal_size()
                        except Exception:
                            cols_term = TERM_WIDTH; rows_term = 30
                        available_width = max(40, cols_term - 4)
                        # WAY more space between items. Use a visible
                        # separator so the gap is unmistakable even if a
                        # terminal/viewer collapses runs of spaces, and
                        # surround it with several real spaces on each side.
                        SEP = "     │     "  # 5 spaces, bar, 5 spaces
                        SEP_W = vlen(SEP)
                        max_item_w = max(vlen(f"{n}: {q}") for n, q in items_grid) if items_grid else 20
                        col_width = max(max_item_w, 18)
                        # Cap columns so wider terminals get FEWER pages
                        # (more items per row), narrow terminals get MORE
                        # pages. Hard cap at 4 columns so spacing stays huge.
                        cols_per_row = max(1, min(4, (available_width + SEP_W) // (col_width + SEP_W)))
                        for i in range(0, len(items_grid), cols_per_row):
                            row_items = items_grid[i:i+cols_per_row]
                            cells = []
                            for name, qty in row_items:
                                item_str = f"{name}: {qty}"
                                pad = col_width - vlen(item_str)
                                if pad < 0: pad = 0
                                cells.append(item_str + (" " * pad))
                            out.append("  " + SEP.join(cells).rstrip())
                        out.append("")

                    # Unknown items (unchanged)
                    for k,v in sorted(player.inventory.items()):
                        if not k.startswith("unknown_") or not isinstance(v,dict): continue
                        if v.get("qty",0) > 0:
                            cat = k[len("unknown_"):]
                            disp = UNKNOWN_DISPLAY_MAP.get(cat, f"❓ Unknown {cat.replace('_',' ').title()}")
                            out.append(f"  {disp}: {v['qty']}  [🔍 {v.get('inspect_tries',0)}/{MAX_INSPECTIONS} attempts]")
                    if any(v.get("qty",0) > 0 for k,v in player.inventory.items() if k.startswith("unknown_") and isinstance(v,dict)):
                        out.append("")
                    if player.wearing: out.append(f"\n  🛡️ Wearing armor: {player.wearing.replace('_',' ').title()}")
                    if player.wearing_pants:
                        ins = CLOTHING_INSULATION[player.wearing_pants]
                        out.append(f"  👖 Wearing: {player.wearing_pants.replace('_',' ').title()} (insulation +{ins})")
                    if player.wearing_shirt:
                        ins = CLOTHING_INSULATION[player.wearing_shirt]
                        out.append(f"  👕 Wearing: {player.wearing_shirt.replace('_',' ').title()} (insulation +{ins})")
                    total_ins = CLOTHING_INSULATION.get(player.wearing_pants,0) + CLOTHING_INSULATION.get(player.wearing_shirt,0)
                    if total_ins > 0:
                        req = player.arctic_insulation_req
                        status = "✅ Safe in Arctic" if total_ins >= req else f"❌ Need {req:.0f} insulation (have {total_ins})"
                        out.append(f"  🧊 Total insulation: {total_ins} — {status}")
                    if player.wearing_pants and player.wearing_shirt:
                        out.append(f"  ⚠️ Full clothing: Extra heat-sensitive during firestorms!")
                    if player.wearing or player.wearing_pants or player.wearing_shirt:
                        out.append("")
                    # Tools / Weapons durability
                    tools_info = []
                    if player.inventory.get("advanced_axe", 0) > 0:
                        tools_info.append(f"    🪓 Advanced Axe              {int(max(0,player.axe_dur))}/{TOOL_DUR_ADV}  ({int(max(0,player.axe_dur)/TOOL_DUR_ADV*100)}%)")
                    elif player.inventory.get("axe", 0) > 0:
                        tools_info.append(f"    🪓 Axe                       {int(max(0,player.axe_dur))}/{TOOL_DUR}  ({int(max(0,player.axe_dur)/TOOL_DUR*100)}%)")
                    if player.inventory.get("pickaxe", 0) > 0:
                        tools_info.append(f"    ⛏️ Pickaxe                   {int(max(0,player.pickaxe_dur))}/{TOOL_DUR}  ({int(max(0,player.pickaxe_dur)/TOOL_DUR*100)}%)")
                    if player.spear_type and player.inventory.get(player.spear_type, 0) > 0 and player.spear_dur > 0:
                        sdef_h = SPEAR_DEFS.get(player.spear_type, {})
                        tools_info.append(f"    🗡️ {player.spear_type.replace('_',' ').title():<24} {int(max(0,player.spear_dur))}/{sdef_h.get('dur',100)}  ({int(max(0,player.spear_dur)/max(1,sdef_h.get('dur',100))*100)}%)")
                    if player.wearing and player.armor_dur > 0:
                        armor_max = 1800 if player.wearing == "heavy_armor" else (1000 if player.wearing == "medium_armor" else 500)
                        armor_pct = int((player.armor_dur / armor_max) * 100)
                        tools_info.append(f"    🛡️ {player.wearing.replace('_',' ').title():<24} {int(player.armor_dur)} dur ({armor_pct}%)")
                    if tools_info:
                        out.append(""); out.append("  🔧 TOOLS / WEAPONS:")
                        out.extend(tools_info)
                        out.append("")
                    # Station HP
                    st_info = [(st, hp) for st, hp in player.station_hp.items() if player.inventory.get(st, 0) > 0]
                    if st_info:
                        out.append("  🏭 STATIONS (all):")
                        for st, hp in st_info:
                            pct = int(max(0, hp) / STATION_MAX_HP * 100)
                            out.append(f"    {st.replace('_',' ').title():<28} {int(hp):.0f}/{int(STATION_MAX_HP)} GWM  ({pct}%)")
                        out.append("")
                    # Adapt page length to terminal height — narrow/short
                    # terminals get more pages, tall terminals get fewer.
                    try:
                        _, _rows_term = os.get_terminal_size()
                    except Exception:
                        _rows_term = 30
                    LINES_PER_PAGE = max(12, min(40, _rows_term - 8))
                    if len(out) <= LINES_PER_PAGE:
                        term.print_page(out)
                    else:
                        pages = [out[i:i+LINES_PER_PAGE] for i in range(0, len(out), LINES_PER_PAGE)]
                        for pi, page in enumerate(pages):
                            page_hdr = [f"🎒 INVENTORY — page {pi+1}/{len(pages)}"] if pi > 0 else []
                            term.print_page(page_hdr + page)

                # ---- EXPLAIN ----
                elif act == "explain" and arg:
                    target = arg.lower()
                    key_match = target if target in GAME_MECHANICS else next((k for k in GAME_MECHANICS if target in k or k in target), None)
                    if key_match:
                        term.print_page([f"📘 {key_match.replace('_',' ').title()}", "─"*TERM_WIDTH, GAME_MECHANICS[key_match]]); continue
                    tk = target.replace(" ","_")
                    if tk in GATHER_ALIASES: tk = GATHER_ALIASES[tk]
                    if tk in CONSUME_ALIASES: tk = CONSUME_ALIASES[tk]
                    out = [f"📘 {tk.replace('_',' ').title()}", "─"*TERM_WIDTH]
                    # Check if craftable
                    recipe = RECIPES.get(tk)
                    if recipe:
                        out.append("🔨 RECIPE:")
                        mat_parts = []
                        for k_m, v_m in recipe.get("mat",{}).items():
                            label = "any berry" if k_m == "any_berry" else k_m.replace("_"," ")
                            mat_parts.append(f"{v_m} {label}")
                        out.append(f"  Materials: {', '.join(mat_parts) or '—'}")
                        st = recipe.get("station","—") or "—"
                        if isinstance(st,list): st = " + ".join(s.replace("_"," ") for s in st)
                        elif st != "—": st = st.replace("_"," ")
                        out.append(f"  Station: {st}")
                        out.append(f"  Time: {recipe.get('igm',0)}s, Energy: {recipe.get('energy',0)}⚡")
                        # Check what recipes consume this item
                        consumed_in = []
                        for r_name, r_info in RECIPES.items():
                            if tk in r_info.get("mat", {}):
                                consumed_in.append(f"{r_name.replace('_',' ').title()} ({r_info['mat'][tk]})")
                        if consumed_in:
                            out.append(f"  Used in: {', '.join(consumed_in)}")
                        out.append("")
                    # Check if findable (biome resource)
                    found_in = []
                    for biome, resources in [("Forest", BIOME_RESOURCES.get("Forest",{})), ("Arctic", BIOME_RESOURCES.get("Arctic",{}))]:
                        for res_name, res_meta in resources.items():
                            if res_meta.get("item") == tk:
                                found_in.append(f"  {res_name} (🕐 {biome})")
                    if found_in:
                        out.append("📍 FOUND IN:")
                        out.extend(found_in)
                        out.append("")
                    # Check for food effects
                    eff = food_effects.get(tk)
                    if eff:
                        out.append("⚙️ FOOD EFFECTS:")
                        stats = []
                        for stat,icon in [("energy","⚡"),("hunger","🍽️"),("health","❤️"),("thirst","💧"),("fatigue","😴")]:
                            if eff.get(stat): stats.append(f"{icon}{eff[stat]}")
                        if stats: out.append(f"  Stats: {', '.join(stats)}")
                        if eff.get("notes"): out.append(f"  Note: {eff['notes']}")
                        if eff.get("risk_min"): out.append(f"  ⚠️ Risk: {int(eff['risk_min']*100)}-{int(eff['risk_max']*100)}% for {eff.get('risk_dmg',0)} dmg")
                        elif eff.get("risk") == "unknown": out.append("  ❓ UNKNOWN RISK")
                        elif eff.get("risk") == "mystery_mushroom": out.append("  ❓ MYSTERY: Random effects each time!")
                        elif eff.get("risk") == "mystery_moss": out.append("  ❓ MYSTERY MOSS: 50% heal or damage!")
                        out.append("")
                    else:
                        out.append(f"🔍 ID chance per attempt: {int(IDENTIFY_CHANCES.get(tk,0.0)*100)}%")
                        out.append("")
                    # Disease info
                    diseases = getattr(player, "diseases", None) or {}
                    if diseases:
                        out.append("🩺 DISEASES:")
                        for did, st in diseases.items():
                            d = DISEASES.get(did, {})
                            if tk in d.get("recover", {}):
                                out.append(f"  {DISEASE_DISPLAY[did]}: {d['recover'][tk]*100:.0f}% cure chance")
                        out.append("")
                    # Shop info
                    price = ITEM_PRICES.get(tk)
                    if price:
                        out.append("🏪 SHOP:")
                        out.append(f"  Buy: {int(price*1.5)}🪙 | Sell: {price}🪙")
                    else:
                        out.append("🏪 Not sold in shop.")
                    term.print_page(out)
                    qt_on_event(term, player, world, "explain_done", target=arg)


                # ---- RECIPES ----
                elif act == "recipes":
                    cats = {
                        "1. 🍳 Furnace":    ["thin_cut_meat","roasted_berry","cooked_berry","roasted_spotted_mushroom","cooked_shimmer_frostberry","roasted_meat","herbal_tea","chunky_stew","stuffed_thin_meat","thick_cut_meat","stuffed_mushroom","stuffed_thin_meat_berries","stuffed_thin_meat_honey","stuffed_thin_meat_meat","fresh_water","dirty_water","jerky","moss_salve","antidote_tea","frost_tonic","glowing_jam","honey_root_tea"],
                        "2. 🪵 Woodworking":["woodworking_station","sewing_station","axe","advanced_axe","pickaxe","plank","fabric","water_filter","liquifier","necroplastic","compressed_fuel","ash_poultice"],
                        "3. 🧵 Sewing":     ["trap","poison_trap","very_strong_fabric","bandages","light_armor","pants","shirt","medium_pants","medium_shirt","heavy_pants","heavy_shirt","insulated_wrap"],
                        "4. 🔥 Smelting":   ["honey","beeswax","oil","plastic","copper","iron","gold","steel"],
                        "5. 🏭 Stations":    ["woodworking_station","sewing_station","furnace","smelter","water_filter","liquifier"],
                        "6. 🛡️ Armor":      ["light_armor","medium_armor","heavy_armor"],
                        "7. ⚙️ General":    ["poison"],
                        "8. 🏠 Housing":    ["cannon","advanced_cannon","ballista","advanced_ballista"],
                        "9. 🗡️ Weapons":   ["spear","advanced_spear","ice_spear","advanced_ice_spear","throwing_spear","advanced_throwing_spear","heavy_spear","advanced_heavy_spear","simple_shield","standard_shield","advanced_shield","sakos_shield"],
                    }
                    cat_keys = list(cats.keys())
                    term.show_menu(["📜 RECIPES", "─"*TERM_WIDTH] + [f"  {k}" for k in cat_keys] + ["","  Press number. Enter to close."])
                    while True:
                        ch = term.get_key_no_flush(0.5)
                        if ch in ('\r','\n','ESC'):
                            sys.stdout.write("\033[2J"); sys.stdout.flush(); break
                        if ch and ch.isdigit():
                            idx = int(ch)
                            if 1 <= idx <= len(cat_keys):
                                cn = cat_keys[idx-1]
                                out = [f"🔨 {cn.split('. ')[1]} Recipes", "─"*TERM_WIDTH]
                                for n in cats[cn]:
                                    r = RECIPES.get(n,{})
                                    # Show any_berry as "any berry" in display
                                    mat_parts = []
                                    for k_m, v_m in r.get("mat",{}).items():
                                        label = "any berry" if k_m == "any_berry" else k_m.replace("_"," ")
                                        mat_parts.append(f"{v_m} {label}")
                                    mats = ", ".join(mat_parts) or "—"
                                    st = r.get("station","—") or "—"
                                    if isinstance(st,list): st = "+".join(s.replace("_"," ") for s in st)
                                    elif st != "—": st = st.replace("_"," ")
                                    name = vtrunc(n.replace("_"," ").title(), 24)
                                    mats = vtrunc(mats, 45)
                                    st = vtrunc(st, 22)
                                    fuel = r.get("fuel")
                                    if len(out) == 2:
                                        out.append("  Name                      | Materials                                     | Station               | Fuel")
                                        out.append("  " + "-" * 24 + "+" + "-" * 45 + "+" + "-" * 22 + "+------")
                                    fuel_s = f"{fuel}🪵" if fuel is not None else ""
                                    out.append(f"  {name:<24}| {mats:<45}| {st:<22}| {fuel_s}")
                                term.print_page(out); break
                    rn = True

                # ---- SHOP (categorized) ----
                elif act == "shop":
                    cat_keys = list(SHOP_CATEGORIES.keys())
                    term.show_menu(["🏪 SHOP", "─"*TERM_WIDTH] + [f"  {k}" for k in cat_keys] + ["","  Press number. Enter to close."])
                    while True:
                        ch = term.get_key_no_flush(0.5)
                        if ch in ('\r','\n','ESC'):
                            sys.stdout.write("\033[2J"); sys.stdout.flush(); break
                        if ch and ch.isdigit():
                            idx = int(ch)
                            if 1 <= idx <= len(cat_keys):
                                cn = cat_keys[idx-1]
                                out = [f"🏪 {cn.split('. ')[1]}", "─"*TERM_WIDTH, "  Name                       | Buy 🪙 | Sell 🪙"]
                                for ik in SHOP_CATEGORIES[cn]:
                                    p = ITEM_PRICES.get(ik)
                                    if p: out.append(f"  {ik.replace('_',' ').title():<28} | {int(p*1.5):<6} | {p}")
                                term.print_page(out); break
                    rn = True

                # ---- INSPECT / IDENTIFY ----
                elif act in ("inspect","identify"):
                    # Note: actual inspect action is blocked later if paused, but cluster info can be shown
                    if player.active_tasks:
                        msg.append("🔨 Can't inspect while crafting! Wait for it to finish, or use the 'cancel' command."); msg = msg[-3:]; continue
                    if arg:
                        handled = do_inspect_inventory(player, arg, msg, refresh)
                        if not handled:
                            cl = world.clusters.get((int(player.x),int(player.y)))
                            if cl and not cl["is_identified"]:
                                # Pre-checks BEFORE the sleep
                                if cl["inspection_attempts"] >= MAX_INSPECTIONS:
                                    msg.append(f"⚠️ Max inspections reached ({MAX_INSPECTIONS}/{MAX_INSPECTIONS}). Cannot inspect further.")
                                elif player.inventory.get("id_lens",0) == 0 and player.energy < INSPECT_COST:
                                    msg.append(f"⚡ Not enough energy — need {INSPECT_COST}, have {int(player.energy)}.")
                                else:
                                    if getattr(player, "inspect_pending", None):
                                        msg.append("⏳ Already inspecting — please wait.")
                                    else:
                                        player.inspect_pending = {"kind": "cluster", "cx": int(player.x), "cy": int(player.y), "end": time.time() + INSPECT_TIME}
                                        msg.append("🔍 Inspecting cluster... (3 seconds)")
                                        if sound and sound.enabled: sound.play_inspect()
                            elif cl and cl["is_identified"]:
                                msg.append(f"✅ Already known: {cl['name']}.")
                            else:
                                msg.append(f"❌ No unknown item matching '{arg}' found.")
                    else:
                        cl = world.clusters.get((int(player.x),int(player.y)))
                        if not cl: msg.append("🔍 Nothing here. Try 'inspect <item>' for inventory items.")
                        elif cl["is_identified"]: msg.append(f"✅ Already known: {cl['name']}.")
                        else:
                            if paused:
                                msg.append("⏸️ Can't inspect while paused. Resume first."); msg = msg[-3:]
                            elif cl["inspection_attempts"] >= MAX_INSPECTIONS:
                                msg.append(f"⚠️ Max inspections reached ({MAX_INSPECTIONS}/{MAX_INSPECTIONS}). Cannot inspect further.")
                            elif player.inventory.get("id_lens",0) == 0 and player.energy < INSPECT_COST:
                                msg.append(f"⚡ Not enough energy — need {INSPECT_COST}, have {int(player.energy)}.")
                            else:
                                if getattr(player, "inspect_pending", None):
                                    msg.append("⏳ Already inspecting — please wait.")
                                else:
                                    player.inspect_pending = {"kind": "cluster", "cx": int(player.x), "cy": int(player.y), "end": time.time() + INSPECT_TIME}
                                    msg.append("🔍 Inspecting cluster... (3 seconds)")
                                    if sound and sound.enabled: sound.play_inspect()

                # ---- FIGHT OLD_MAN ----
                elif act == "fight" and arg.strip().replace(" ","_").lower() == "old_man":
                    if player.quests.get("fight_old_man") == "active":
                        # Simulate fight with old man — a tough NPC opponent
                        player_power = player.health + player.energy
                        old_man_hp = 150
                        old_man_atk = 25
                        rounds = []
                        om_hp = old_man_hp
                        pl_hp = player.health
                        import random as _r
                        while om_hp > 0 and pl_hp > 0:
                            pl_atk = _r.randint(5, 20)
                            if player.spear_type: pl_atk += 15
                            om_hp -= pl_atk
                            rounds.append(f"  You hit old man for {pl_atk} dmg (Old Man HP: {max(0,om_hp)})")
                            if om_hp <= 0: break
                            om_dmg = _r.randint(10, old_man_atk)
                            pl_hp -= om_dmg
                            rounds.append(f"  Old Man hits you for {om_dmg} dmg (Your HP: {max(0,pl_hp)})")
                        player.health = max(1, pl_hp)  # survive with 1 HP even if lost
                        if om_hp <= 0:
                            player.quests["fight_old_man"] = "completed"
                            player.points += QUESTS["fight_old_man"]["pts"]
                            player.coins += QUESTS["fight_old_man"]["coins"]
                            term.print_page(["⚔️ FIGHT WITH OLD MAN", "─"*40] + rounds + ["", "🏆 You WON! The old man falls back, laughing.", "🧓 Old Man: Har har har! Not bad at all!", f"✅ Quest complete! +{QUESTS['fight_old_man']['pts']} pts, +{QUESTS['fight_old_man']['coins']} coins"])
                        else:
                            term.print_page(["⚔️ FIGHT WITH OLD MAN", "─"*40] + rounds + ["", "💀 You LOST! The old man defeats you.", "🧓 Old Man: Har har! Not yet worthy! Try again!"])
                    elif player.quests.get("fight_old_man") == "completed":
                        msg.append("✅ Already fought the old man — quest complete!")
                    else:
                        msg.append("🧓 The old man isn't challenging you to a fight yet...")
                    msg = msg[-3:]; continue

                # ---- BUILD (place a crafted house into the world) ----
                elif act in ("build","place house","build house","erect"):
                    house_type = arg.strip().lower().replace(" ","_") if arg.strip() else None
                    if house_type == "house":
                        house_type = "teepee"
                    if not house_type or house_type not in HOUSE_DEFS:
                        types_str = ", ".join(HOUSE_DEFS.keys())
                        msg.append(f"❌ Specify a house type: {types_str}")
                    elif player.inventory.get(house_type,0) <= 0:
                        msg.append(f"❌ You don't have a {house_type.replace('_',' ')} in your inventory. Craft one first.")
                    elif _house_find_at(world, int(player.x), int(player.y)):
                        msg.append("❌ There's already a house here!")
                    else:
                        hdef = HOUSE_DEFS[house_type]
                        player.inventory[house_type] -= 1
                        new_house = {
                            "id": f"h{int(time.time()*1000)%999999}",
                            "type": house_type,
                            "x": int(player.x), "y": int(player.y),
                            "hp": hdef["hp"], "max_hp": hdef["hp"],
                            "furniture": [],
                        }
                        world.houses.append(new_house)
                        player.house_built = True
                        fp_b = hdef["footprint"]
                        msg.append(f"🏠 {house_type.replace('_',' ').title()} ({fp_b}×{fp_b}) built at ({int(player.x)},{int(player.y)})! Stepping inside...")
                        # Auto-enter the freshly built house at the build location.
                        player.inside_house_id = new_house["id"]
                        _hmsg_b = enter_house_mode(term, player, world, new_house, weather, msg)
                        for hm in (_hmsg_b or [])[-2:]: msg.append(hm)
                    msg = msg[-3:]

                # ---- ENTER HOUSE ----
                elif act in ("enter","enter house","go inside","inside"):
                    h = _house_find_at(world, int(player.x), int(player.y)) or _house_find_nearby(world, player.x, player.y, radius=2)
                    if not h:
                        msg.append("❌ No house at your location. Step onto a house's footprint and try again.")
                    elif h.get("hp",0)<=0:
                        msg.append("💥 That house is destroyed!")
                    else:
                        player.inside_house_id = h["id"]
                        _hmsg = enter_house_mode(term, player, world, h, weather, msg)
                        for hm in (_hmsg or [])[-2:]: msg.append(hm)
                    msg = msg[-3:]

                # ---- PICKUP TEEPEE (portable) ----
                elif act in ("pickup","pick up","take") and arg.strip().lower() in ("teepee","⛺"):
                    h = _house_find_at(world, int(player.x), int(player.y)) or _house_find_nearby(world, player.x, player.y, radius=1)
                    if h and h["type"]=="teepee":
                        world.houses.remove(h)
                        player.inventory["teepee"] = player.inventory.get("teepee",0)+1
                        msg.append("⛺ You pack up the teepee.")
                    else:
                        msg.append("❌ No teepee nearby.")
                    msg = msg[-3:]

                # ---- HOUSE STATUS ----
                elif act in ("house status","hstatus","house hp","housestat"):
                    h = _house_find_at(world, int(player.x), int(player.y)) or _house_find_nearby(world, player.x, player.y, radius=2)
                    if not h:
                        msg.append("❌ No house nearby.")
                    else:
                        df, ff = _house_protection_pct(h)
                        fu_str = ", ".join(f["type"].replace("_"," ") for f in h.get("furniture",[])) or "none"
                        msg.append(f"🏠 {h['type'].replace('_',' ').title()}: HP {h['hp']}/{h['max_hp']} | Dmg reduction {int((1-df)*100)}% | Fire reduction {int((1-ff)*100)}%")
                        msg.append(f"   Furniture: {fu_str}")
                    msg = msg[-3:]

                # ---- GRID MODE ----
                elif act in ("grid","gridmode","grid_mode"):
                    # Trigger grid combat/hunt mode manually
                    nearby_hostiles = [a for a in world.animals
                                       if a.get("atk",0)>0 and math.hypot(a["x"]-player.x,a["y"]-player.y)<=12.0]
                    nearby_any = [a for a in world.animals if math.hypot(a["x"]-player.x,a["y"]-player.y)<=12.0]
                    targets = nearby_hostiles if nearby_hostiles else nearby_any
                    if not targets:
                        msg.append("❌ No animals within 12 tiles for grid mode.")
                    else:
                        grid_msgs = run_grid_mode(term, player, world, targets, msg)
                        for gm in grid_msgs[-3:]: msg.append(gm)
                    msg = msg[-3:]

                # ---- HUNT ----
                elif act == "hunt":
                    _unlock_and_show_tutorial(term, player, "hunt")
                    parts_hunt = arg.strip().split()
                    do_throw = bool(parts_hunt) and parts_hunt[-1] == "throw"
                    do_grid  = bool(parts_hunt) and parts_hunt[-1] == "grid"
                    if do_throw or do_grid:
                        hunt_type = (" ".join(parts_hunt[:-1])).strip().replace(" ","_")
                    else:
                        hunt_type = (" ".join(parts_hunt)).strip().replace(" ","_")
                    if not hunt_type:
                        # Default: enter grid mode against any nearby animals
                        active_spear = None
                        for sp in ["advanced_ice_spear","ice_spear","advanced_heavy_spear","heavy_spear","advanced_throwing_spear","throwing_spear","advanced_spear","spear"]:
                            if player.inventory.get(sp, 0) > 0:
                                if player.spear_type != sp or player.spear_dur <= 0:
                                    player.spear_type = sp
                                    player.spear_dur = SPEAR_DEFS[sp]["dur"]
                                active_spear = sp; break
                        if not active_spear or player.spear_dur <= 0:
                            msg.append("❌ Need a spear to hunt! 'craft spear' (2 planks + 15 rock)")
                        else:
                            grid_targets = [a for a in world.animals
                                            if math.hypot(a["x"]-player.x, a["y"]-player.y) <= 12.0]
                            if not grid_targets:
                                msg.append("❌ No animals nearby. Explore more!")
                            else:
                                run_grid_mode(term, player, world, grid_targets, msg)
                                msg = msg[-3:]
                    else:
                        # Find best available spear
                        active_spear = None
                        for sp in ["advanced_ice_spear","ice_spear","advanced_heavy_spear","heavy_spear","advanced_throwing_spear","throwing_spear","advanced_spear","spear"]:
                            if player.inventory.get(sp, 0) > 0:
                                if player.spear_type != sp or player.spear_dur <= 0:
                                    player.spear_type = sp
                                    player.spear_dur = SPEAR_DEFS[sp]["dur"]
                                active_spear = sp; break
                        if not active_spear or player.spear_dur <= 0:
                            msg.append("❌ Need a spear to hunt! 'craft spear' (2 planks + 15 rock)")
                        elif hunt_type not in ANIMAL_DEFS:
                            msg.append(f"❓ Unknown animal '{hunt_type.replace('_',' ')}'. Try: rabbit, squirrel, salmon, seal, penguin")
                        else:
                            adef = ANIMAL_DEFS[hunt_type]
                            if not biome_matches(adef, biome_at(player.x, player.y)):
                                target_biomes = adef['biome'] if isinstance(adef['biome'], str) else "/".join(adef['biome'])
                                msg.append(f"❌ {hunt_type.replace('_',' ').title()} only live in the {target_biomes}!")
                            else:
                                nearby = [(a, math.hypot(a["x"]-player.x, a["y"]-player.y))
                                          for a in world.animals if a["type"] == hunt_type]
                                if not nearby:
                                    msg.append(f"❌ No {hunt_type.replace('_',' ')} nearby. Explore more!")
                                else:
                                    nearby.sort(key=lambda z: z[1])
                                    target, dist = nearby[0]
                                    sdef = SPEAR_DEFS[active_spear]
                                    # Vision check: animal may flee before you act
                                    vision = random.triangular(0, target.get("vision_max", adef["vision_max"]), target.get("vision_peak", adef["vision_peak"]))
                                    if dist < vision and random.random() < 0.5:
                                        target["fleeing"] = True
                                        msg.append(f"😱 {hunt_type.replace('_',' ').title()} spotted you and fled! ({dist:.1f} tiles away)")
                                    else:
                                        hit = True
                                        if do_grid:
                                            # Pull all animals of same type (or grots) within 12 tiles
                                            grid_targets = [a for a in world.animals
                                                            if (a["type"] == hunt_type or a.get("is_grot")) and
                                                            math.hypot(a["x"]-player.x, a["y"]-player.y) <= 12.0]
                                            if not grid_targets:
                                                grid_targets = [target]
                                            run_grid_mode(term, player, world, grid_targets, msg)
                                            msg = msg[-3:]
                                            hit = False  # grid mode handles its own kills
                                        elif do_throw:
                                            if sound and sound.enabled:
                                                sound.play_spear_throw()
                                            _show_spear_tutorial_if_first(term, player, active_spear)
                                            hit_zone, cancelled = run_spear_minigame(term, player, hunt_type, dist, active_spear)
                                            if cancelled:
                                                hit = False
                                                msg.append("🛑 Throw cancelled. Spear held.")
                                            elif hit_zone == "miss":
                                                hit = False
                                                target["fleeing"] = True
                                                player.spear_dur -= min(sdef.get("throw_cost", 20), player.spear_dur)
                                                msg.append(f"💨 Threw spear — MISSED! ({dist:.1f} tiles)")
                                            else:
                                                hit_mult = {"head":1.5,"body":1.0,"graze":0.5,"near_miss":0.25}.get(hit_zone, 0.0)
                                                target["fleeing"] = True
                                                dmg = max(1, int(sdef.get("throw", 0) * hit_mult * (2 if player.inventory.get("poison",0)>0 else 1)))
                                                if player.inventory.get("poison",0)>0: player.inventory["poison"] -= 1
                                                target["hp"] -= dmg
                                                _flash_hit(target.get("type",""))
                                                player.spear_dur -= min(sdef.get("throw_cost", 20), player.spear_dur)
                                                if active_spear == "ice_spear": player.spear_dur = 0
                                                zone_desc = {"head":"HEAD HIT","body":"body hit","graze":"graze","near_miss":"near miss"}.get(hit_zone,"hit")
                                                msg.append(f"🗡️ Spear throw — {zone_desc}! -{dmg} dmg ({max(0,target['hp']):.0f} HP left)")
                                        else:
                                            if dist > 2:
                                                msg.append(f"❌ Too far to strike! ≤2 tiles needed (you're {dist:.1f} away).")
                                                hit = False
                                            else:
                                                if sound and sound.enabled:
                                                    sound.play_attack()
                                                dmg = sdef.get("strike", 0) * (2 if player.inventory.get("poison",0)>0 else 1)
                                                if player.inventory.get("poison",0)>0: player.inventory["poison"] -= 1
                                                target["hp"] -= dmg
                                                _flash_hit(target.get("type",""))
                                                player.spear_dur -= sdef.get("strike_cost", dmg)
                                                msg.append(f"⚔️ Strike! -{dmg} HP ({max(0,target['hp']):.0f} HP left)")
                                        if player.spear_dur <= 0:
                                            player.inventory[active_spear] = max(0, player.inventory.get(active_spear,0)-1)
                                            player.spear_type = None; player.spear_dur = 0
                                            msg.append(f"💥 {active_spear.replace('_',' ').title()} broke!")
                                        if target["hp"] <= 0:
                                            resolve_animal_kill(player, world, target, msg)
                                        elif hit:
                                            target["fleeing"] = True
                                            animal_retaliation(player, world, target, msg)
                    msg = msg[-3:]

                # ---- ACHIEVEMENTS ----
                elif act in ("achievements","achievement","achievments","achievment","achieve","achives","achiev"):
                    cur_pt = player.total_playtime + (time.time() - player.session_start)
                    out = [f"🏆 ACHIEVEMENTS  —  {int(player.points)} total points", "═" * TERM_WIDTH, ""]
                    earned_set = set(player.earned_achievements)
                    for aid, ach in ACHIEVEMENTS.items():
                        status = "✅" if aid in earned_set else "🔒"
                        out.append(f"  {status} {ach['name']:<28}  {ach['pts']:>3} pts  +{ach['coins']}🪙")
                        out.append(f"       {ach['desc']}")
                        out.append("")
                    out.append(f"  {len(earned_set)}/{len(ACHIEVEMENTS)} earned")
                    term.print_page(out)

                elif act == "quests":
                    if getattr(player, "qt_active", False):
                        msg.append("📖 Normal quests are disabled during the interactive tutorial.")
                        msg = msg[-3:]
                        continue
                    menu_lines = ["📝 QUESTS", "═" * TERM_WIDTH, "", "  1. Active quests", "  2. Completed quests", "", "Press 1 or 2 to view a quest list. Press Enter to cancel."]
                    term.show_menu(menu_lines)
                    while True:
                        ch = term.get_key_no_flush(0.5)
                        if not ch:
                            continue
                        if ch in ('\r','\n','ESC'):
                            break
                        if ch == '1':
                            show_quest_screen(term, player, preface="🧓 Active quests:", status_filter="active")
                            break
                        if ch == '2':
                            show_quest_screen(term, player, preface="🧓 Completed quests:", status_filter="completed")
                            break
                    msg.append("📝 Quest menu closed. Type 'quests' again anytime.")
                    msg = msg[-3:]

                # ---- GATHER ALL ----
                # ---- DROP ----
                elif act == "drop":
                    drop_parts = arg.strip().split()
                    drop_qty = 1; drop_item = ""
                    if drop_parts:
                        try:
                            drop_qty = int(drop_parts[0])
                            drop_item = " ".join(drop_parts[1:]).replace(" ","_").lower()
                        except ValueError:
                            drop_item = " ".join(drop_parts).replace(" ","_").lower()
                    if not drop_item:
                        msg.append("❌ Usage: drop <item> [qty]  e.g.  drop meat 3")
                    else:
                        if drop_item == "house":
                            drop_item = "teepee"
                        _inv_entry = player.inventory.get(drop_item, 0)
                        _have = _inv_entry.get("qty", 0) if isinstance(_inv_entry, dict) else _inv_entry
                        if _have < drop_qty:
                            msg.append(f"❌ You only have {_have} {drop_item.replace('_',' ')}.")
                        elif drop_item in HOUSE_DEFS:
                            # Place a house item from inventory as a world house.
                            drop_qty = 1
                            if _house_find_at(world, int(player.x), int(player.y)):
                                msg.append("❌ There's already a house here!")
                            else:
                                if isinstance(_inv_entry, dict):
                                    _inv_entry["qty"] = _have - 1
                                else:
                                    player.inventory[drop_item] = _have - 1
                                hdef = HOUSE_DEFS[drop_item]
                                new_house = {
                                    "id": f"h{int(time.time()*1000)%999999}",
                                    "type": drop_item,
                                    "x": int(player.x), "y": int(player.y),
                                    "hp": hdef["hp"], "max_hp": hdef["hp"],
                                    "furniture": [],
                                }
                                world.houses.append(new_house)
                                msg.append(f"🏠 {drop_item.replace('_',' ').title()} placed at ({int(player.x)},{int(player.y)})! Type 'enter' to go inside.")
                        else:
                            if isinstance(_inv_entry, dict):
                                _inv_entry["qty"] = _have - drop_qty
                            else:
                                player.inventory[drop_item] = _have - drop_qty
                            player.dropped_items.append({"item":drop_item,"qty":drop_qty,"x":player.x,"y":player.y,"dropped_at":time.time()})
                            lbl = drop_item.replace("_"," ")
                            msg.append(f"📦 Dropped {drop_qty}× {lbl} at your location.")
                            # Drop creates a mini-cluster at the nearest empty spot
                            _dpos = (int(player.x),int(player.y))
                            for _dr in range(0,4):
                                for _ddx in range(-_dr,_dr+1):
                                    for _ddy in range(-_dr,_dr+1):
                                        _cp=(int(player.x)+_ddx,int(player.y)+_ddy)
                                        if _cp not in world.clusters and _cp not in world.depleted:
                                            world.clusters[_cp]={"qty":max(1,drop_qty),"real_item":drop_item,"is_identified":True,"meta":{"regrows":False,"hazard":False,"hazard_key":None,"tool_req":"","locked":False,"is_ash":False},"display":f"📦 {lbl.title()}"}
                                            _dpos=None; break
                                    if _dpos is None: break
                                if _dpos is None: break
                            if drop_item == "meat":
                                nearby_cats = [a for a in world.animals if a.get("type")=="cat" and math.hypot(a["x"]-player.x,a["y"]-player.y)<10.0]
                                if nearby_cats and not player.cat_following:
                                    for c in nearby_cats[:1]:
                                        c["_following_player"] = True
                                    player.cat_following = True
                                    msg.append("🐈 The cat sniffs the meat and decides to follow you!")
                                    msg.append("🎉 Feral Cat Adopted! Good Job!")
                            elif drop_item == "catnip":
                                live_cats = [a for a in world.animals if a.get("type")=="cat" and a.get("hp",1)>0]
                                close_cats = [a for a in live_cats if math.hypot(a["x"]-player.x,a["y"]-player.y)<3.0]
                                coming = [a for a in live_cats if math.hypot(a["x"]-player.x,a["y"]-player.y)<30.0]
                                if close_cats and not player.cat_following:
                                    c = close_cats[0]
                                    c["_following_player"] = True
                                    c.setdefault("loyalty", 0); c["loyalty"] += 3
                                    c["_pet_ok"] = False
                                    c["_pet_ok_at"] = getattr(player, "unpaused_clock", 0.0) + random.uniform(240.0, 480.0)
                                    player.cat_following = True
                                    msg.append("🐈 A cat right beside you nuzzles the catnip and starts following you! (loyalty +3)")
                                    msg.append("🎉 Feral Cat Adopted! Good Job!")
                                elif close_cats:
                                    for c in close_cats:
                                        c.setdefault("loyalty", 0); c["loyalty"] += 3
                                        # Catnip immediately makes the cat willing to be petted
                                        c["_pet_ok"] = True
                                        c["_pet_ok_at"] = getattr(player, "unpaused_clock", 0.0) + random.uniform(240.0, 480.0)
                                    msg.append("🌿 Your cat munches the catnip and rolls over! (loyalty +3)")
                                else:
                                    msg.append(f"🌿 Catnip dropped! {len(coming)} cat(s) in range will come running...")

                elif act == "gather" and (arg in ("all", "everything") or arg.strip().isdigit()):
                    if paused:
                        msg.append("⏸️ Can't gather while paused. Resume first."); msg = msg[-3:]; continue
                    if player.active_tasks:
                        msg.append("🔨 Can't gather while crafting! Wait for it to finish, or use the 'cancel' command."); msg = msg[-3:]; continue
                    if getattr(player, "gather_all", None):
                        msg.append("⏳ Already gathering all. Wait for it to finish."); msg = msg[-3:]; continue
                    if player.fatigue <= 0:
                        msg.append("😴 Too exhausted to gather! Type 'rest' to recover Fatigue."); continue
                    cl = world.clusters.get((int(player.x),int(player.y)))
                    if not cl or cl.get("qty",0) <= 0:
                        msg.append("🔍 Nothing here to gather."); continue
                    qty = cl["qty"]
                    # "gather N" — cap to the requested amount.
                    if arg.strip().isdigit():
                        qty = min(qty, max(1, int(arg.strip())))
                    # Energy-limited: 1 energy per item. You can only gather as
                    # many as you have energy for (e.g. 5 energy → 5 of a 10-cluster).
                    avail = int(player.energy)
                    if avail <= 0:
                        msg.append("⚡ Too exhausted — need at least 1 energy to gather."); continue
                    if avail < qty:
                        msg.append(f"⚡ Low energy — only gathering {avail} of {qty}.")
                        qty = avail
                    energy_cost = qty

                    tool_req = cl["meta"].get("tool_req","")
                    if cl["meta"].get("locked"):
                        has_tool = player.has_axe() if tool_req == "axe" else player.inventory.get(tool_req, 0) > 0
                        if not has_tool:
                            article = "an" if tool_req[0] in "aeiou" else "a"
                            msg.append(f"🔒 Need {article} {tool_req} first"); continue
                    countdown_secs = math.ceil(qty / 2.0)
                    # Schedule the gather-all as an async pending task so the player
                    # can still use inventory/help/recipes/other read-only commands.
                    player.gather_all = {
                        "x": int(player.x),
                        "y": int(player.y),
                        "item": cl.get("real_item"),
                        "qty": qty,
                        "energy_cost": energy_cost,
                        "end": time.time() + countdown_secs,
                        "total": countdown_secs,
                    }
                    msg.append(f"⏳ Gather all activated. ({countdown_secs}s — you can still type commands)")
                    msg = msg[-3:]
                    if sound and sound.enabled: sound.loop_gather(cl.get("real_item"))
                    rn = True


                # ---- GATHER ----
                elif act == "gather":
                    if paused:
                        msg.append("⏸️ Can't gather while paused. Resume first."); msg = msg[-3:]; continue
                    # Blocked while crafting
                    if player.active_tasks:
                        msg.append("🔨 Can't gather while crafting! Wait for it to finish, or use the 'cancel' command."); msg = msg[-3:]; continue
                    if player.fatigue <= 0:
                        msg.append("😴 Too exhausted to gather! Type 'rest' to recover Fatigue."); continue
                    cl = world.clusters.get((int(player.x),int(player.y)))
                    if not cl or cl.get("qty",0) <= 0: msg.append("🔍 Nothing here to gather."); continue
                    # Determine how many items will be gathered
                    a = 1 if cl["real_item"] == "bee_hive" else min(2, cl["qty"])
                    # Energy-limited: 1 energy per item. With only 1 energy you
                    # can still gather, but you'll only pick up 1.
                    avail = int(player.energy)
                    if avail <= 0:
                        msg.append("⚡ Too exhausted — need at least 1 energy to gather."); continue
                    if avail < a:
                        a = avail
                    energy_cost = a

                    # Tool check — accept axe or advanced_axe for "axe" requirement
                    tool_req = cl["meta"].get("tool_req","")
                    if cl["meta"].get("locked"):
                        if tool_req == "axe":
                            has_tool = player.has_axe()
                        else:
                            has_tool = player.inventory.get(tool_req, 0) > 0
                        if not has_tool:
                            article = "an" if tool_req[0] in "aeiou" else "a"
                            msg.append(f"🔒 Need {article} {tool_req} first"); continue
                    cl["qty"] -= a; real = cl["real_item"]
                    if real == "sand" and random.random() < 0.05:
                        real = "gunpowder"
                    if real == "rock":
                        roll = random.random()
                        if roll < 0.005:   player.inventory["gold_ore"] = player.inventory.get("gold_ore",0)+1; msg.append("✨ Gold Ore!")
                        elif roll < 0.105: player.inventory["copper_ore"] = player.inventory.get("copper_ore",0)+1; msg.append("🔶 Copper Ore!")
                        elif roll < 0.255: player.inventory["iron_ore"] = player.inventory.get("iron_ore",0)+1; msg.append("⚙️ Iron Ore!")
                    if not cl["is_identified"]:
                        cat = UNKNOWN_CATEGORY_MAP.get(real,"misc")
                        inv_key, inv_entry = player.get_unknown_entry(cat)
                        inv_entry["qty"] += a; inv_entry["items"].extend([real]*a)
                        inv_entry["inspect_tries"] = max(inv_entry.get("inspect_tries",0), cl.get("inspection_attempts",0))
                        disp = UNKNOWN_DISPLAY_MAP.get(cat, f"❓ Unknown {cat.title()}")
                        msg.append(f"➕ {a} {disp}")
                        qt_on_event(term, player, world, "gather_done", item=real)
                    else:
                        player.inventory[real] = player.inventory.get(real,0) + a
                        msg.append(f"➕ {a} {display_item_name(real)}")
                        qt_on_event(term, player, world, "gather_done", item=real)

                    if cl.get("meta",{}).get("hazard"):
                        hk = cl["meta"].get("hazard_key"); h = HAZARDS.get(hk,{}); base_dmg = h.get("dmg",0)
                        final_dmg = base_dmg
                        if player.wearing:
                            reduction = player.armor_hazard_reduction(hk)
                            final_dmg = max(0, base_dmg - reduction)
                        if player.wearing and final_dmg < base_dmg:
                            player.armor_dur -= final_dmg
                            if player.armor_dur <= 0:
                                player.wearing = None
                                player.armor_dur = 0
                                msg.append("💥 Armor broke!")
                        if random.random() < h.get("chance",0.5):
                            if final_dmg > 0:
                                player.note_damage_cause(f"Hit by {hk.replace('_', ' ').title()}")
                                player.health -= final_dmg
                                hazard_name = hk.replace("_", " ").title() if hk else "Unknown"
                                msg.append(f"💥 Hit by {hazard_name}! -{final_dmg} HP")
                                flash_damage(final_dmg)
                            elif player.wearing:
                                msg.append("🛡️ Attack blocked by armor!")
                            else:
                                msg.append("🛡️ Attack blocked!")
                    if cl["qty"] <= 0:
                        _gpos = (int(player.x), int(player.y))
                        _sub = cl.get("sub_cluster")
                        if _sub and _sub.get("qty", 0) > 0:
                            # Promote hidden sub_cluster to dominant
                            _sub["dominant"] = True; _sub["pos"] = list(_gpos)
                            world.clusters[_gpos] = _sub
                            world.depleted.discard(_gpos)
                            msg.append(f"🌿 Beneath it: {_sub.get('name','?')} (x{_sub['qty']})!")
                        else:
                            world.depleted.add(_gpos)
                            world.clusters.pop(_gpos, None)
                            # Replace with biome-appropriate ground cover
                            _pos_biome = biome_at(player.x, player.y)
                            if _pos_biome == "Arctic":
                                _gitem = random.choice(["snow", "ice_chunk"])
                                _gname = "❄️ Snow Patch" if _gitem == "snow" else "🧊 Ice Chunk"
                                _gqty  = random.randint(2, 6)
                            else:
                                _gitem = "dirt"; _gname = "🟫 Dirt Patch"; _gqty = random.randint(3, 7)
                            world.clusters[_gpos] = {
                                "name": _gname, "real_item": _gitem, "category": "material",
                                "is_identified": True, "inspection_attempts": 0,
                                "pos": list(_gpos), "qty": _gqty,
                                "meta": {"item": _gitem, "regrows": False, "hazard": False,
                                         "hazard_key": None, "tool_req": "", "locked": False},
                                "dominant": True, "sub_cluster": None,
                            }
                            world.depleted.discard(_gpos)
                    player.energy = max(0, player.energy - energy_cost)
                    if sound and sound.enabled:
                        if real == "wood": sound.play_chop()
                        elif real in ("rock","ice_chunk"): sound.play_pickaxe()
                        else: sound.play_collect()
                    if real == "wood":
                        player.wood_gathered += a
                        used, brk = player.use_axe(a)
                        if brk:
                            msg.append(brk)
                            if sound and sound.enabled: sound.play_tool_break()
                    if real in BERRY_ITEMS:
                        player.berries_gathered += a
                    if real in MUSHROOM_ITEMS:
                        player.mushrooms_gathered += a
                    if real == "bee_hive":
                        player.bee_hives_collected += a
                    if real == "spider_silk":
                        player.spider_silk_gathered += a
                    if real == "rock":
                        used, brk = player.use_pickaxe(a)
                        if brk:
                            msg.append(brk)
                            if sound and sound.enabled: sound.play_tool_break()

                # ---- CRAFT ----
                elif act == "craft":
                    target = arg.lower().replace(" ","_")
                    # Shortcuts
                    if target in ("filter_water", "filter", "filter water"):
                        target = "filtered_water"
                    # Special: campfire is instant — converts 1 fire_fuel into FIRE_FUEL_PARTS campfire fuel
                    if paused:
                        msg.append("⏸️ Can't craft while paused. Resume first."); msg = msg[-3:]; continue
                    if player.fatigue <= 0:
                        msg.append("😴 Too exhausted to craft! Type 'rest' to recover Fatigue."); msg = msg[-3:]; continue
                    # For filtered_water, ensure water_filter station exists
                    if target == "filtered_water" and player.station_hp.get("water_filter", 0) <= 0:
                        msg.append("❌ Need a water_filter station. Craft one at woodworking_station."); msg = msg[-3:]; continue
                    if target == "campfire":
                        if player.active_tasks:
                            msg.append("🔨 Can't light a campfire while crafting!")
                        elif player.inventory.get("fire_fuel", 0) <= 0:
                            msg.append("❌ Need 1 Fire Fuel (craft: 1 oil + 50 wood at woodworking_station).")
                        else:
                            player.inventory["fire_fuel"] -= 1
                            player.campfire_fuel += FIRE_FUEL_PARTS
                            msg.append(f"🔥 Campfire lit! {player.campfire_fuel} fuel parts. Type 'rest' to rest safely.")
                        msg = msg[-3:]; continue
                    r = RECIPES.get(target)
                    if not r:
                        msg.append("❌ Recipe not found. Type 'recipes' to browse.")
                    else:
                        # Handle any_berry wildcard
                        if "any_berry" in r.get("mat", {}):
                            ok, err = resolve_any_berry(player, r)
                            if not ok:
                                msg.append(err)
                            else:
                                # Ask which berries to use
                                needed = r["mat"]["any_berry"]
                                avail_berries = [(b, player.inventory.get(b, 0)) for b in BERRY_ITEMS if player.inventory.get(b, 0) > 0]
                                if len(avail_berries) > 1:
                                    # Show menu to select berries
                                    menu_lines = [f"🫐 SELECT BERRIES (need {needed} total)", "─"*TERM_WIDTH]
                                    for i, (berry, qty) in enumerate(avail_berries, 1):
                                        menu_lines.append(f"  {i}. {display_item_name(berry)}: {qty}")
                                    menu_lines.append("")
                                    menu_lines.append("  Press number to select berry type, or Enter to use any available.")
                                    term.show_menu(menu_lines)
                                    selected_berry = None
                                    while True:
                                        ch = term.get_key_no_flush(0.5)
                                        if ch in ('\r','\n'):
                                            break
                                        if ch and ch.isdigit():
                                            idx = int(ch)
                                            if 1 <= idx <= len(avail_berries):
                                                selected_berry = avail_berries[idx-1][0]
                                                break
                                    sys.stdout.write("\033[2J"); sys.stdout.flush()
                                    if selected_berry:
                                        if player.inventory.get(selected_berry, 0) >= needed:
                                            player.inventory[selected_berry] -= needed
                                            patched = dict(r)
                                            patched["mat"] = {k:v for k,v in r["mat"].items() if k != "any_berry"}
                                            ok2, m2 = player.start_task(target, patched)
                                            if not ok2:
                                                player.inventory[selected_berry] = player.inventory.get(selected_berry,0) + needed
                                            msg.append(m2)
                                        else:
                                            msg.append(f"❌ Not enough {selected_berry.replace('_',' ')}.")
                                    else:
                                        # Use any berries
                                        player.deduct_any_berry(needed)
                                        patched = dict(r)
                                        patched["mat"] = {k:v for k,v in r["mat"].items() if k != "any_berry"}
                                        ok2, m2 = player.start_task(target, patched)
                                        if not ok2:
                                            player.inventory["wild_berries"] = player.inventory.get("wild_berries",0) + needed
                                        msg.append(m2)
                                    rn = True
                                else:
                                    # Only one berry type available, use it
                                    player.deduct_any_berry(needed)
                                    patched = dict(r)
                                    patched["mat"] = {k:v for k,v in r["mat"].items() if k != "any_berry"}
                                    ok2, m2 = player.start_task(target, patched)
                                    if not ok2:
                                        player.inventory["wild_berries"] = player.inventory.get("wild_berries",0) + needed
                                    msg.append(m2)
                        else:
                            # Quantity: craft N or "all" (until materials run out).
                            if qty_req == "all":
                                _n = 9999
                            else:
                                _n = max(1, int(qty_req))
                            _crafted = 0; _lastmsg = ""
                            for _ci in range(_n):
                                ok2, m2 = player.start_task(target, r)
                                _lastmsg = m2
                                if not ok2:
                                    break
                                _crafted += 1
                                if target == "plank":
                                    player.planks_made += 1
                                if target == "poison_trap":
                                    player.poison_traps_crafted += 1
                                if target == "bandages":
                                    player.bandages_made += 1
                                if target == "water_filter":
                                    player.filtered_water_drank = False
                                if target == "fire_fuel":
                                    player.fire_fuel_crafted += 1
                                if target == "oil":
                                    player.oil_made += 1
                                if target == "smelter":
                                    player.smelter_crafted = True
                            if _crafted <= 1:
                                msg.append(_lastmsg)
                            else:
                                msg.append(f"🔨 Queued {_crafted}× {target.replace('_',' ').title()} to craft.")

                elif act == "cancel":
                    if player.active_tasks:
                        t = player.active_tasks[0]
                        now_c = time.time()
                        elapsed = t["igm"] - max(0, t["end"] - now_c)
                        pct_done = elapsed / max(1, t["igm"])
                        item_name = t["item"].replace("_", " ").title()
                        print(f"\n🔨 Cancelling: {item_name} ({int(pct_done*100)}% done)")
                        print("  1. Refund materials")
                        print("  2. Save progress (get half-finished item, resume later)")
                        try:
                            ch = input("  Choice [1/2]: ").strip()
                        except (EOFError, KeyboardInterrupt):
                            ch = "1"
                        if ch == "2":
                            # Save partial progress
                            half_key = "half_" + t["item"]
                            player.inventory[half_key] = player.inventory.get(half_key, 0) + 1
                            # Store time remaining so next craft is faster
                            if not hasattr(player, "craft_progress"):
                                player.craft_progress = {}
                            player.craft_progress[t["item"]] = {"pct": pct_done, "elapsed": elapsed}
                            player.active_tasks.clear()
                            if sound and sound.enabled: sound.stop_craft()
                            msg.append(f"📦 Saved half-finished {item_name}. Next time you craft it, it will be {int(pct_done*100)}% done already.")
                        else:
                            refund_parts = []
                            for mat_k, mat_v in t.get("mat_used", {}).items():
                                player.inventory[mat_k] = player.inventory.get(mat_k, 0) + mat_v
                                refund_parts.append(f"{mat_v} {mat_k.replace('_',' ')}")
                            player.active_tasks.clear()
                            if sound and sound.enabled: sound.stop_craft()
                            refund_str = ", ".join(refund_parts) if refund_parts else "none"
                            msg.append(f"❌ Crafting cancelled. Refunded: {refund_str}")
                    else:
                        msg.append("ℹ️ No crafting task to cancel.")
                    msg = msg[-3:]; continue

                # ---- FILTER WATER ----
                elif act == "filter":
                    if paused:
                        msg.append("⏸️ Can't filter water while paused. Resume first."); msg = msg[-3:]; continue
                    if player.active_tasks:
                        msg.append("🔨 Can't filter water while crafting! Wait for it to finish."); msg = msg[-3:]; continue
                    if player.station_hp.get("water_filter", 0) <= 0:
                        msg.append("❌ Need a water_filter station. Craft one first."); msg = msg[-3:]; continue
                    target = (arg or "").strip().lower().replace(" ", "_")
                    if not target or target in ("all", "water"):
                        for candidate in ("dirty_water", "water", "freezing_dirty_water", "arctic_water"):
                            if player.inventory.get(candidate, 0) > 0:
                                target = candidate
                                break
                    if target not in {"dirty_water", "water", "freezing_dirty_water", "arctic_water"}:
                        msg.append("❌ Filter needs dirty or unfiltered water to turn into filtered_water."); msg = msg[-3:]; continue
                    if player.inventory.get(target, 0) <= 0:
                        msg.append(f"❌ No {target.replace('_',' ')} to filter."); msg = msg[-3:]; continue
                    player.inventory[target] -= 1
                    player.inventory["filtered_water"] = player.inventory.get("filtered_water", 0) + 1
                    msg.append(f"💧 Filtered {target.replace('_',' ')} into filtered water.")
                    msg = msg[-3:]
                    continue

                # ---- PET / FEED CAT ----
                elif act in ("pet","feed"):
                    if paused:
                        msg.append("⏸️ You can't pet a cat while paused. Resume first."); msg = msg[-3:]; continue
                    if player.resting:
                        msg.append("😴 You can't pet a cat while resting. Stop resting first."); msg = msg[-3:]; continue
                    if player.active_tasks:
                        msg.append("🔨 You can't pet a cat while crafting! Wait for it to finish."); msg = msg[-3:]; continue
                    arg_clean = (arg or "").strip().lower()
                    with_meat = False
                    if act == "feed" or ("meat" in arg_clean):
                        if player.inventory.get("roasted_meat",0) > 0:
                            player.inventory["roasted_meat"] -= 1; with_meat = True
                        elif player.inventory.get("raw_game",0) > 0:
                            player.inventory["raw_game"] -= 1; with_meat = True
                        elif player.inventory.get("meat",0) > 0:
                            player.inventory["meat"] -= 1; with_meat = True
                        else:
                            msg.append("🥩 No meat to give the cat."); msg = msg[-3:]; continue
                    pet_cat(player, world, msg, with_meat=with_meat)
                    continue

                # ---- EAT / DRINK ----
                elif act in ("eat","drink") and arg:
                    if player.active_tasks and not (getattr(player, "fast_mode", False) and act in ("eat", "drink")):
                        msg.append("🔨 Can't eat while crafting! Wait for it to finish, or use the 'cancel' command."); msg = msg[-3:]; continue
                    raw_in = arg.lower().strip(); raw_k = raw_in.replace(" ","_")
                    real_item = CONSUME_ALIASES.get(raw_in, CONSUME_ALIASES.get(raw_k, raw_k))
                    unk_key = find_unknown_inv_key(player, raw_in)
                    if not unk_key and "unknown" in raw_in:
                        unk_key = find_unknown_inv_key(player, raw_in.replace("unknown","").strip())
                    if unk_key and isinstance(player.inventory.get(unk_key),dict) and player.inventory[unk_key].get("qty",0) > 0:
                        eat_unknown_item(player, unk_key, msg); continue
                    inv_key = ""; found_item = False
                    for k,v in player.inventory.items():
                        if k.startswith("unknown_"): continue
                        if isinstance(v,int) and v > 0 and (k == real_item or k.endswith(real_item)):
                            inv_key = k; found_item = True; break
                    if not found_item:
                        msg.append("❌ Item not found."); continue
                    eff = food_effects.get(inv_key)
                    if inv_key in ("bandages", "enhanced_bandage"):
                        msg.append(f"🩹 Use the 'bandage' command to apply bandages, not 'eat'."); msg = msg[-3:]; continue
                    if not eff: msg.append(f"❌ {inv_key.replace('_',' ').title()} is not edible."); continue
                    # ---- Quantity: eat/drink N or all of this item ----
                    if qty_req == "all":
                        _n = int(player.inventory.get(inv_key, 0))
                    else:
                        _n = min(int(qty_req), int(player.inventory.get(inv_key, 0)))
                    _n = max(1, _n)
                    _eaten = 0; _premsg = len(msg)
                    for _ei in range(_n):
                        if player.inventory.get(inv_key, 0) <= 0:
                            break
                        if eff.get("risk") == "mystery_mushroom":
                            mm = roll_mystery_mushroom()
                            if random.random() < mm["risk_pct"] / 100.0:
                                player.note_damage_cause("Mystery mushroom poisoning")
                                player.health = max(0, player.health - mm["damage"])
                                msg.append(f"☠️ Mystery mushroom backfired! -{mm['damage']} HP.")
                                player.health = min(MAX_STAT_CAP, player.health + 0)
                                try: _infect_player(player, "mystery", msg)
                                except Exception: pass
                            else:
                                player.health = min(MAX_STAT_CAP, player.health + mm["health"])
                                msg.append("✅ Mystery mushroom was safe this time.")
                                try: _remove_one_disease(player, msg)
                                except Exception: pass
                            player.hunger = min(MAX_STAT_CAP, player.hunger + mm["hunger"])
                            player.energy = min(MAX_STAT_CAP, player.energy + mm["energy"])
                            player.thirst = min(MAX_STAT_CAP, player.thirst + mm["thirst"])
                            if mm["fatigue"]:
                                player.fatigue = min(MAX_STAT_CAP, player.fatigue + mm["fatigue"])
                        elif eff.get("risk") == "mystery_moss":
                            if random.random() < 0.5:
                                player.health = min(MAX_STAT_CAP,player.health+50); msg.append("💚 Healed! (+50 HP)")
                                try: _remove_one_disease(player, msg)
                                except Exception: pass
                            else:
                                player.health = max(0,player.health-random.randint(10,50)); msg.append("☠️ Cursed!")
                                try: _infect_player(player, "mystery", msg)
                                except Exception: pass
                        elif eff.get("risk_min"):
                            if random.random() < random.uniform(eff["risk_min"],eff["risk_max"]):
                                player.health = max(0,player.health-eff.get("risk_dmg",0)); msg.append("😖 You feel sick!")
                            else: msg.append("✅ Safe this time.")
                        if eff.get("risk") != "mystery_mushroom":
                            player.hunger = min(MAX_STAT_CAP, player.hunger+eff.get("hunger",0))
                            player.energy = min(MAX_STAT_CAP, player.energy+eff.get("energy",0))
                            player.thirst = min(MAX_STAT_CAP, player.thirst+eff.get("thirst",0))
                            player.health = min(MAX_STAT_CAP, player.health+eff.get("health",0))

                        if sound and sound.enabled:
                            if act == "drink":
                                sound.play_drink()
                            else:
                                sound.play_eat()
                        if eff.get("fatigue"): player.fatigue = min(MAX_STAT_CAP, player.fatigue + eff["fatigue"])
                        if inv_key in BERRY_ITEMS and inv_key not in player.berry_types_eaten:
                            player.berry_types_eaten.append(inv_key)
                        if inv_key in MUSHROOM_ITEMS and inv_key not in player.mushroom_types_eaten:
                            player.mushroom_types_eaten.append(inv_key)
                        if inv_key == "filtered_water":
                            player.filtered_water_drank = True
                        # --- Disease hooks ---
                        try:
                            _beginner = getattr(player, "difficulty_mult", NORMAL_HUNGER_MULT) <= BEGINNER_HUNGER_MULT
                            # Dirty/unfiltered water no longer deals flat damage —
                            # instead it rolls for water-borne diseases.
                            if inv_key in ("water", "dirty_water", "freezing_dirty_water"):
                                if random.random() < 0.30:
                                    _infect_player(player, "water", msg)
                            elif inv_key == "fresh_water":
                                if random.random() < 0.05:
                                    _infect_player(player, "water", msg)
                            # Uncooked foods → food disease risk (beginner skip)
                            UNCOOKED = {"raw_game","wild_berries","sweet_berries","sour_berries",
                                        "glowing_berries","frostberry","shimmer_frostberry",
                                        "mushrooms","black_trumpets","spotted_mushrooms",
                                        "poisonous_berry","mushroom_death_cap"}
                            if (not _beginner) and inv_key in UNCOOKED:
                                if random.random() < 0.05:
                                    _infect_player(player, "food", msg)
                            # Mystery mushroom backfire → also infect; safe → 25% cure
                            if eff.get("risk") == "mystery_mushroom":
                                if "_mm_backfire_marker" in msg[-3:]:
                                    pass
                            # Recovery rolls
                            _apply_disease_recovery(player, inv_key, msg)
                        except Exception:
                            pass
                        player.inventory[inv_key] -= 1
                        note = f" ({eff['notes']})" if eff.get("notes") else ""
                        msg.append(f"🍽️ Consumed {arg.title()}{note}")
                        qt_on_event(term, player, world, "eat_done", item=inv_key)
                        _eaten += 1
                    if _n > 1:
                        del msg[_premsg:]
                        _verb = "Drank" if act == "drink" else "Ate"
                        msg.append(f"🍽️ {_verb} {_eaten}× {inv_key.replace(chr(95),' ').title()}")


                # ---- BANDAGE ----
                elif act in ("bandage", "apply"):
                    if player.inventory.get("enhanced_bandage", 0) > 0:
                        btype = "enhanced_bandage"
                    elif player.inventory.get("bandages", 0) > 0:
                        btype = "bandages"
                    else:
                        btype = None
                    if not btype:
                        msg.append("🩹 No bandages in inventory. Craft them: 10 spider_silk at sewing_station.")
                    elif player.health >= player.max_health:
                        msg.append("❤️ Already at full health!")
                    else:
                        eff = food_effects.get(btype, {})
                        heal = eff.get("health", 20)
                        player.health = min(player.max_health, player.health + heal)
                        player.inventory[btype] -= 1
                        msg.append(f"🩹 Applied {btype.replace('_',' ')}! +{heal} HP (now {int(player.health)} HP)")
                    msg = msg[-3:]

                # ---- WALK ----
                elif act == "walk" and arg:
                    if paused:
                        msg.append("⏸️ Can't walk while paused. Resume first."); msg = msg[-3:]; continue
                    if player.fatigue <= 0:
                        msg.append("😴 Too exhausted to walk. Rest now!"); msg = msg[-3:]; continue
                    if player.active_tasks: msg.append("🔨 Cannot walk while crafting!"); continue
                    arg_clean = arg.strip().lower()
                    if arg_clean.startswith("to "):
                        arg_clean = arg_clean[3:].strip()
                    # Check if arg is coordinates (format: "5,3", "@5,3", or "(-1, 4)")
                    coords_str = arg_clean.lstrip("@ ").strip()
                    if coords_str.startswith("(") and coords_str.endswith(")"):
                        coords_str = coords_str[1:-1].strip()
                    coords_str = coords_str.replace(" ", "")
                    try:
                        if "," in coords_str:
                            cx, cy = map(float, coords_str.split(",", 1))
                            cx, cy = int(cx), int(cy)
                            dist = math.hypot(cx - player.x, cy - player.y)
                            if dist <= FOG_RADIUS:
                                player.start_auto_walk(cx, cy, world, msg)
                                rn = True
                            else:
                                msg.append(f"❌ Coordinates @({cx},{cy}) are out of range (beyond {FOG_RADIUS} tiles).")
                            continue
                    except (ValueError, IndexError):
                        pass
                    # Quick tutorial: force "walk to berries" to the guaranteed
                    # tutorial berry tile. The normal nearest-name search can choose a
                    # different berry bush, leaving the tutorial waiting forever.
                    search = arg_clean.replace("to ", "").strip()
                    if getattr(player, "qt_active", False) and getattr(player, "qt_step", "") == "find_berries" and "berr" in search:
                        target = getattr(player, "qt_berries_pos", None)
                        if not _qt_valid_berry_target(world, target):
                            target = _qt_ensure_cluster(world, player, "wild_berries", "🫐 Berry Bush", qty=6)
                            player.qt_berries_pos = target
                        if _qt_valid_berry_target(world, target):
                            player.start_auto_walk(target[0], target[1], world, msg)
                            _qt_trigger_berries_if_here(term, player, world)
                            rn = True
                            continue
                    # Otherwise search for resource by name, then nearby animals.
                    best = None; best_pos = None; bd = 9999
                    search_key = search.replace(" ", "_")
                    for k, c in world.clusters.items():
                        if (search in c["real_item"] or search_key in c["real_item"] or
                                search in c["name"].lower() or
                                search in UNKNOWN_NAME_MAP.get(c["real_item"],"").lower() or
                                search in UNKNOWN_DISPLAY_MAP.get(UNKNOWN_CATEGORY_MAP.get(c["real_item"],""),"").lower()):
                            dist = math.hypot(k[0]-player.x, k[1]-player.y)
                            if dist < bd: bd = dist; best = c; best_pos = k
                    if not best:
                        for a in world.animals:
                            if a.get("hp", 1) <= 0:
                                continue
                            animal_name = str(a.get("type", "")).replace("_", " ").lower()
                            if search_key in animal_name.replace(" ", "_") or search in animal_name or search in a.get("type", "").replace("_", " "):
                                dist = math.hypot(a["x"] - player.x, a["y"] - player.y)
                                if dist < bd:
                                    bd = dist; best_pos = (a["x"], a["y"])
                    if best_pos:
                        player.start_auto_walk(best_pos[0], best_pos[1], world, msg)
                        rn = True
                    else: msg.append(f"❌ No cluster or animal matching '{search}'.")

                # ---- BUY / SELL ----
                elif act in ("buy","sell"):
                    ik = arg.replace(" ","_")
                    if ik == "house":
                        ik = "teepee"
                    if act == "buy" and ik == "textbook":
                        if player.inventory.get("textbook",0) >= 3:
                            msg.append("❌ Max 3 textbooks.")
                        elif player.coins >= 300:
                            player.coins -= 300
                            player.inventory["textbook"] = player.inventory.get("textbook",0)+1
                            player.textbooks_bought = getattr(player, "textbooks_bought", 0) + 1
                            msg.append("✅ Bought 📚 Textbook.")
                            if sound and sound.enabled: sound.play_buy()
                        else:
                            msg.append("❌ Need 300🪙")
                    elif act == "buy" and ik == "id_lens":
                        if player.coins >= 50:
                            player.coins -= 50
                            player.inventory["id_lens"] = player.inventory.get("id_lens",0)+1
                            player.id_lens_bought = getattr(player, "id_lens_bought", 0) + 1
                            msg.append("✅ Bought 🔍 ID Lens.")
                            if sound and sound.enabled: sound.play_buy()
                        else:
                            msg.append("❌ Need 50🪙")
                    elif ik not in ITEM_PRICES: msg.append("❌ Not in shop. Type 'shop' to browse.")
                    elif act == "buy":
                        c = int(ITEM_PRICES[ik]*1.5)
                        # Quantity: buy N or "all" (as many as coins allow).
                        if qty_req == "all":
                            _n = int(player.coins // c) if c > 0 else 0
                        else:
                            _n = int(qty_req)
                        _n = max(1, _n)
                        _bought = 0
                        for _bi in range(_n):
                            if player.coins < c:
                                break
                            player.coins -= c; player.inventory[ik] = player.inventory.get(ik,0)+1
                            if ik == "axe": player.axe_dur = TOOL_DUR
                            if ik == "advanced_axe": player.axe_dur = TOOL_DUR_ADV
                            if ik == "pickaxe": player.pickaxe_dur = TOOL_DUR
                            if ik in player.station_hp: player.station_hp[ik] = STATION_MAX_HP
                            # Auto-equip spears bought if no spear currently equipped
                            if ik in SPEAR_DEFS and (not player.spear_type or player.spear_dur <= 0):
                                player.spear_type = ik
                                player.spear_dur = SPEAR_DEFS[ik]["dur"]
                            _bought += 1
                        if _bought > 0:
                            if _bought == 1:
                                msg.append(f"✅ Bought {ik.replace('_',' ').title()} for {c}🪙")
                            else:
                                msg.append(f"✅ Bought {_bought}× {ik.replace('_',' ').title()} for {c*_bought}🪙")
                            if sound and sound.enabled: sound.play_buy()
                        else:
                            msg.append(f"❌ Need {c}🪙")
                    else:
                        if ik in ["textbook","id_lens"]: msg.append("❌ Cannot sell.")
                        elif player.inventory.get(ik,0) > 0:
                            # Quantity: sell N or "all" of this item.
                            have = int(player.inventory.get(ik,0))
                            if qty_req == "all":
                                _n = have
                            else:
                                _n = min(int(qty_req), have)
                            _n = max(1, _n)
                            _sold = 0
                            for _si in range(_n):
                                if player.inventory.get(ik,0) <= 0:
                                    break
                                player.coins += ITEM_PRICES[ik]; player.inventory[ik] -= 1
                                if ik in ("ice_chunk","freezing_water","freezing_dirty_water","arctic_water","snow"):
                                    player.arctic_items_sold = getattr(player, "arctic_items_sold", 0) + 1
                                _sold += 1
                            if _sold == 1:
                                msg.append(f"✅ Sold {ik.replace('_',' ').title()} for {ITEM_PRICES[ik]}🪙")
                            else:
                                msg.append(f"✅ Sold {_sold}× {ik.replace('_',' ').title()} for {ITEM_PRICES[ik]*_sold}🪙")
                            if sound and sound.enabled: sound.play_sell()
                        else: msg.append("❌ None to sell.")

                # ---- UNEQUIP (alias) ----
                elif act == "unequip":
                    target = arg.strip().replace(" ","_").lower() if arg else "all"
                    if target in ("pants", "none_pants", "all", ""):
                        if player.wearing_pants:
                            player.inventory[player.wearing_pants] = player.inventory.get(player.wearing_pants,0)+1
                            ins = CLOTHING_INSULATION.get(player.wearing_pants, 0)
                            msg.append(f"👖 {player.wearing_pants.replace('_',' ').title()} removed. -{ins} insulation.")
                            player.wearing_pants = None
                        else: msg.append("❌ No pants being worn.")
                    if target in ("shirt", "none_shirt", "all", ""):
                        if player.wearing_shirt:
                            player.inventory[player.wearing_shirt] = player.inventory.get(player.wearing_shirt,0)+1
                            ins = CLOTHING_INSULATION.get(player.wearing_shirt, 0)
                            msg.append(f"👕 {player.wearing_shirt.replace('_',' ').title()} removed. -{ins} insulation.")
                            player.wearing_shirt = None
                    if target in ("armor", "all", ""):
                        if player.wearing:
                            player.inventory[player.wearing] = player.inventory.get(player.wearing,0)+1
                            msg.append(f"🛡️ {player.wearing.replace('_',' ').title()} removed.")
                            player.wearing = None
                    if target in ("shield","all",""):
                        if player.shield_type:
                            player.inventory[player.shield_type] = player.inventory.get(player.shield_type,0)+1
                            msg.append(f"🛡️ {player.shield_type.replace('_',' ').title()} stowed ({player.shield_dur_blocks} blocks / {player.shield_dur_absorb} absorb left).")
                            player.shield_type = None; player.shield_dur_blocks = 0; player.shield_dur_absorb = 0
                    if target not in ("pants","none_pants","shirt","none_shirt","armor","shield","all",""):
                        msg.append(f"❌ Can't unequip '{target}'. Try: unequip pants / shirt / armor / shield / (blank for all)")

                # ---- EQUIP ----
                elif act == "equip":
                    target = arg.strip().replace(" ","_").lower(); equipped = True
                    # --- Pants slot ---
                    if target in CLOTHING_PANTS:
                        if player.inventory.get(target,0) > 0:
                            if player.wearing_pants:
                                player.inventory[player.wearing_pants] = player.inventory.get(player.wearing_pants,0)+1
                            player.wearing_pants = target; player.inventory[target] -= 1
                            ins = CLOTHING_INSULATION[target]
                            msg.append(f"👖 {target.replace('_',' ').title()} equipped! +{ins} insulation.")
                        else:
                            msg.append(f"❌ No {target.replace('_',' ')} in inventory.")
                    elif target in ("none_pants","remove_pants"):
                        if player.wearing_pants:
                            player.inventory[player.wearing_pants] = player.inventory.get(player.wearing_pants,0)+1
                            ins = CLOTHING_INSULATION.get(player.wearing_pants, 0)
                            msg.append(f"👖 {player.wearing_pants.replace('_',' ').title()} removed. -{ins} insulation.")
                            player.wearing_pants = None
                        else: msg.append("❌ No pants being worn.")
                    # --- Shirt slot ---
                    elif target in CLOTHING_SHIRTS:
                        if player.inventory.get(target,0) > 0:
                            if player.wearing_shirt:
                                player.inventory[player.wearing_shirt] = player.inventory.get(player.wearing_shirt,0)+1
                            player.wearing_shirt = target; player.inventory[target] -= 1
                            ins = CLOTHING_INSULATION[target]
                            msg.append(f"👕 {target.replace('_',' ').title()} equipped! +{ins} insulation.")
                        else:
                            msg.append(f"❌ No {target.replace('_',' ')} in inventory.")
                    elif target in ("none_shirt","remove_shirt"):
                        if player.wearing_shirt:
                            player.inventory[player.wearing_shirt] = player.inventory.get(player.wearing_shirt,0)+1
                            ins = CLOTHING_INSULATION.get(player.wearing_shirt, 0)
                            msg.append(f"👕 {player.wearing_shirt.replace('_',' ').title()} removed. -{ins} insulation.")
                            player.wearing_shirt = None
                        else: msg.append("❌ No shirt being worn.")
                    # --- Armor slot ---
                    elif target in ("heavy_armor","medium_armor","light_armor"):
                        if player.inventory.get(target,0) > 0:
                            # Return old armor to inventory if already wearing one
                            if player.wearing:
                                player.inventory[player.wearing] = player.inventory.get(player.wearing,0)+1
                            player.wearing = target
                            player.armor_dur = 1800 if target=="heavy_armor" else (1000 if target=="medium_armor" else 500)
                            player.inventory[target] -= 1
                            msg.append(f"🛡️ Equipped {target.replace('_',' ').title()}!")
                        else:
                            msg.append(f"❌ No {target.replace('_',' ')} in inventory.")
                    elif target in ("none", "armor", "unequip_armor"):
                        if player.wearing:
                            player.inventory[player.wearing] = player.inventory.get(player.wearing,0)+1
                            old_armor = player.wearing
                            player.wearing = None; msg.append(f"🛡️ {old_armor.replace('_',' ').title()} removed and returned to inventory.")
                        else: msg.append("❌ No armor being worn.")
                    # --- Equip spear ---
                    elif target in SPEAR_DEFS:
                        sdef_eq = SHIELD_DEFS.get(player.shield_type, {})
                        if sdef_eq.get("no_heavy_spear") and target in ("heavy_spear","advanced_heavy_spear"):
                            msg.append("❌ Cannot use heavy spear while a shield is equipped.")
                        elif player.inventory.get(target,0) > 0:
                            player.spear_type = target
                            player.spear_dur = SPEAR_DEFS[target]["dur"]
                            msg.append(f"🗡️ Equipped {target.replace('_',' ').title()}!")
                        else:
                            msg.append(f"❌ No {target.replace('_',' ')} in inventory.")
                    # --- Equip shield ---
                    elif target in SHIELD_DEFS:
                        if target in ("heavy_spear","advanced_heavy_spear"):
                            msg.append("❌ Cannot equip shield with heavy spear.")
                        elif player.inventory.get(target,0) > 0:
                            if player.shield_type:
                                player.inventory[player.shield_type] = player.inventory.get(player.shield_type,0)+1
                                msg.append(f"🛡️ Stowed {player.shield_type.replace('_',' ').title()}.")
                            sdef_eq = SHIELD_DEFS[target]
                            player.shield_type = target
                            player.shield_dur_blocks = sdef_eq["max_blocks"]
                            player.shield_dur_absorb = sdef_eq["max_absorb"]
                            player.inventory[target] -= 1
                            msg.append(f"🛡️ Equipped {target.replace('_',' ').title()}! ({sdef_eq['max_blocks']} blocks / {sdef_eq['max_absorb']} absorb)")
                        else:
                            msg.append(f"❌ No {target.replace('_',' ')} in inventory.")
                    else:
                        equipped = False
                        msg.append("❌ Cannot equip that. Try: equip pants/shirt/armor/spear/shield or equip none_pants/none_shirt/none")

                # ---- REST ----
                elif act in ("rest", "unrest"):
                    if act == "unrest" and not player.resting:
                        msg.append("❓ You're not resting right now."); continue
                    if getattr(player, "gather_all", None):
                        msg.append("⏳ Can't rest while gathering all.")
                    elif player.resting:
                        # Resume paused crafting
                        _resume_paused_crafting(player)
                        player.resting = False; player.rest_mode = None
                        msg.append("🛑 Stopped resting. (any paused crafting resumes)")
                    else:
                        # Pause any active crafting so countdown freezes while resting
                        now_pc = time.time()
                        for t in player.active_tasks:
                            if "paused_remaining" not in t:
                                t["paused_remaining"] = max(0, int(t["end"] - now_pc))
                        if getattr(player, "gather_all", None) and "paused_remaining" not in player.gather_all:
                            player.gather_all["paused_remaining"] = max(0, int(player.gather_all["end"] - now_pc))
                        # Check if resting inside a house (safe floor rest + bed bonus)
                        _inside_h = None
                        if player.inside_house_id:
                            for _hh in world.houses:
                                if _hh["id"]==player.inside_house_id and _hh.get("hp",0)>0:
                                    _inside_h=_hh; break
                        _has_bed = _inside_h and any(f["type"] in ("bed","couch") for f in _inside_h.get("furniture",[]))
                        if player.campfire_fuel > 0:
                            player.resting = True; player.rest_mode = "campfire"
                            player.rest_last = time.time()
                            player.used_campfire = True
                            player.campfire_rested = True
                            msg.append(f"🔥 Resting at campfire ({player.campfire_fuel} fuel parts). +30😴 +15❤️ +5⚡/game-hr. (crafting paused, type 'rest' to stop)")
                        elif _has_bed:
                            player.resting = True; player.rest_mode = "house_bed"
                            player.rest_last = time.time()
                            msg.append("🛏️ Resting in bed! +30😴 +19❤️ +6⚡/game-hr. No damage! (type 'rest' to stop)")
                        elif _inside_h:
                            player.resting = True; player.rest_mode = "house_floor"
                            player.rest_last = time.time()
                            msg.append("🏠 Resting on house floor. +30😴/game-hr, no damage! (type 'rest' to stop)")
                        else:
                            player.resting = True; player.rest_mode = "floor"
                            player.rest_last = time.time()
                            msg.append("😴 Resting on floor. +30😴/game-hr but -10❤️/hr. (crafting paused, type 'rest' to stop)")
                    if paused:
                        msg.append("⏸️ Game is paused. Resting still works, but time is frozen.")

                # ---- TRAP ----
                elif act in ("trap", "traps"):
                    sub = arg.lower().strip() if act == "trap" else "list"
                    now_t = time.time()
                    px, py = int(player.x), int(player.y)

                    if sub == "set":
                        if player.fatigue <= 0:
                            msg.append("😴 Too exhausted to set traps! Type 'rest' to recover Fatigue."); msg = msg[-3:]; continue
                        # Prefer poison_trap if available, else regular trap
                        trap_type = None
                        if player.inventory.get("poison_trap", 0) > 0:
                            trap_type = "poison_trap"
                        elif player.inventory.get("trap", 0) > 0:
                            trap_type = "trap"
                        if trap_type is None:
                            msg.append("❌ No traps in inventory. Craft one: 'craft trap'.")
                        elif any(t["pos"] == [px, py] for t in player.traps):
                            msg.append("⚠️ A trap is already set here. Check or remove it first.")
                        else:
                            player.inventory[trap_type] -= 1
                            if not player.first_trap_set:
                                player.first_trap_set = True
                            player.traps_set += 1
                            icon = "☠️" if trap_type == "poison_trap" else "🪤"
                            player.traps.append({
                                "pos": [px, py], "type": trap_type, "status": "setting",
                                "set_time": now_t, "catch_time": now_t + TRAP_CATCH_TIME,
                                "uses": 0, "max_uses": random.randint(4, 5),
                            })
                            msg.append(f"{icon} {trap_type.replace('_',' ').title()} set at ({px},{py})! Check in ~{int(TRAP_CATCH_TIME)}s.")

                    elif sub in ("check", "collect"):
                        here = [t for t in player.traps if t["pos"] == [px, py]]
                        if not here:
                            msg.append(f"🪤 No traps at ({px},{py}). Use 'trap list' to see all traps.")
                        else:
                            collected = False
                            for trap in here:
                                if trap["status"] == "caught":
                                    meat = random.randint(1, 3)
                                    player.inventory["meat"] = player.inventory.get("meat", 0) + meat
                                    extra = ""
                                    if trap["type"] == "poison_trap":
                                        player.inventory["bone"] = player.inventory.get("bone", 0) + 1
                                        extra = " + 1 Bone"
                                        player.poison_kills += 1
                                    player.trap_successes += 1
                                    trap["uses"] = trap.get("uses", 0) + 1
                                    max_uses = trap.get("max_uses", 4)
                                    icon = "☠️" if trap["type"] == "poison_trap" else "🪤"
                                    if trap["uses"] >= max_uses:
                                        player.traps.remove(trap)
                                        msg.append(f"{icon} Collected {meat} Meat{extra}! Trap broke after {trap['uses']} uses.")
                                    else:
                                        # Return the trap to inventory so the player can reuse it elsewhere.
                                        player.traps.remove(trap)
                                        player.inventory[trap["type"]] = player.inventory.get(trap["type"], 0) + 1
                                        msg.append(f"{icon} Collected {meat} Meat{extra}! Trap returned to inventory ({trap['uses']}/{max_uses} uses).")
                                    collected = True
                                else:
                                    rem = max(0, int(trap["catch_time"] - now_t))
                                    msg.append(f"⏳ Trap still waiting... (~{rem}s until next check)")
                            if not collected:
                                pass  # message already appended above

                    elif sub == "remove":
                        here = [t for t in player.traps if t["pos"] == [px, py]]
                        if not here:
                            msg.append(f"🪤 No traps at ({px},{py}).")
                        else:
                            trap = here[0]
                            player.traps.remove(trap)
                            player.inventory[trap["type"]] = player.inventory.get(trap["type"], 0) + 1
                            msg.append(f"🪤 Trap retrieved. ({trap['type'].replace('_',' ').title()} returned to inventory)")

                    elif sub in ("list", ""):
                        if not player.traps:
                            msg.append("🪤 No active traps. Use 'trap set' to place one.")
                        else:
                            out = ["🪤 ACTIVE TRAPS", "─" * TERM_WIDTH,
                                   "  #  Type         Position    Dist   Status"]
                            for i, trap in enumerate(player.traps, 1):
                                tp = trap["pos"]
                                d  = math.hypot(tp[0] - player.x, tp[1] - player.y)
                                if trap["status"] == "caught":
                                    st = "🟢 CAUGHT — run 'trap check'!"
                                else:
                                    rem = max(0, int(trap["catch_time"] - now_t))
                                    st = f"⏳ setting (~{rem}s)"
                                icon = "☠️" if trap["type"] == "poison_trap" else "🪤"
                                tname = trap["type"].replace("_"," ").title()
                                out.append(f"  {i:<3} {icon}{tname:<12} @({tp[0]},{tp[1]})  {d:>4.0f}   {st}")
                            term.print_page(out)

                    else:
                        msg.append("🪤 Usage: trap set | trap check | trap remove | trap list")

                # ---- POISON SPEAR (apply 1 vial: lasts 4 strikes OR 1 throw) ----
                elif act == "poison" and arg.strip() == "spear":
                    if not player.spear_type or player.spear_dur <= 0:
                        msg.append("❌ No spear equipped to poison.")
                    elif player.inventory.get("poison", 0) <= 0:
                        msg.append("❌ No poison vial in inventory. Craft poison first.")
                    elif player.spear_poison_strikes > 0 or player.spear_poison_throw:
                        msg.append("☠️ Spear is already poisoned.")
                    else:
                        player.inventory["poison"] -= 1
                        player.spear_poison_strikes = 4
                        player.spear_poison_throw   = True
                        msg.append("☠️ Poison applied! Doubles damage for 4 strikes OR 1 throw.")

                # ---- ATTACK (a/s): auto-target nearest, range 2, 10%/tile miss ----
                elif act in ("a", "attack", "s"):
                    if not getattr(player, "in_combat", False):
                        msg.append("❌ The a/s attack command only works in grid combat mode. Use 'hunt <animal>' to engage prey.")
                    elif not player.spear_type or player.spear_dur <= 0 or player.inventory.get(player.spear_type,0) <= 0:
                        msg.append("❌ No spear equipped. Craft a spear first.")
                    else:
                        sdef = SPEAR_DEFS[player.spear_type]
                        nearby = [(a, math.hypot(a["x"]-player.x, a["y"]-player.y)) for a in world.animals]
                        nearby = [(a,d) for (a,d) in nearby if d <= 2.0]
                        if not nearby:
                            msg.append("❌ No animal within 2 tiles to attack.")
                        else:
                            nearby.sort(key=lambda z: z[1])
                            target, dist = nearby[0]
                            tname = target["type"].replace("_"," ").title()
                            miss_chance = min(0.95, max(0.0, math.ceil(dist) * 0.10))
                            if sound and sound.enabled:
                                sound.play_attack()
                            if random.random() < miss_chance:
                                msg.append(f"💨 Strike at {tname} ({dist:.1f}t) — MISSED! ({int(miss_chance*100)}% miss)")
                            else:
                                mult = 2 if player.spear_poison_strikes > 0 else 1
                                dmg = sdef["strike"] * mult
                                target["hp"] -= dmg
                                _flash_hit(target.get("type",""))
                                player.spear_dur -= sdef.get("strike_cost", dmg)
                                pmark = " ☠️" if mult == 2 else ""
                                if player.spear_poison_strikes > 0:
                                    player.spear_poison_strikes -= 1
                                    if player.spear_poison_strikes == 0: player.spear_poison_throw = False
                                msg.append(f"⚔️ Strike{pmark} {tname}! -{dmg} HP ({max(0,target['hp']):.0f} left)")
                                if player.spear_dur <= 0:
                                    broke = player.spear_type
                                    player.inventory[broke] = max(0, player.inventory.get(broke,0)-1)
                                    player.spear_type = None; player.spear_dur = 0
                                    player.spear_poison_strikes = 0; player.spear_poison_throw = False
                                    msg.append(f"💥 {broke.replace('_',' ').title()} broke!")
                                if target["hp"] <= 0:
                                    resolve_animal_kill(player, world, target, msg)
                                else:
                                    animal_retaliation(player, world, target, msg)

                # ---- THROW (t): auto-target nearest, use spear minigame ----
                elif act in ("t", "throw"):
                    if not player.spear_type or player.spear_dur <= 0 or player.inventory.get(player.spear_type,0) <= 0:
                        msg.append("❌ No spear equipped. Craft a spear first.")
                    else:
                        sdef = SPEAR_DEFS[player.spear_type]
                        nearby = [(a, math.hypot(a["x"]-player.x, a["y"]-player.y)) for a in world.animals]
                        if not nearby:
                            msg.append("❌ No animal in sight to throw at.")
                        else:
                            nearby.sort(key=lambda z: z[1])
                            target, dist = nearby[0]
                            tname = target["type"].replace("_"," ").title()
                            throw_cost = min(sdef["throw_cost"], player.spear_dur)
                            if sound and sound.enabled:
                                sound.play_attack()
                            _show_spear_tutorial_if_first(term, player, player.spear_type)
                            hit_zone, cancelled = run_spear_minigame(term, player, target.get("type","deer"), dist, player.spear_type)
                            if cancelled:
                                msg.append("🛑 Throw cancelled. Spear held.")
                            elif hit_zone == "miss":
                                player.spear_dur -= throw_cost
                                if player.spear_type == "ice_spear":
                                    player.spear_dur = 0
                                target["fleeing"] = True
                                msg.append(f"💨 Threw spear at {tname} ({dist:.1f}t) — MISSED!")
                            else:
                                mult = 2 if player.spear_poison_throw else 1
                                dmg = sdef["throw"] * mult
                                target["hp"] -= dmg
                                _flash_hit(target.get("type",""))
                                player.spear_dur -= throw_cost
                                if player.spear_type == "ice_spear":
                                    player.spear_dur = 0
                                pmark = " ☠️" if mult == 2 else ""
                                msg.append(f"🗡️ Threw spear{pmark}! {tname} -{dmg} HP ({max(0,target['hp']):.0f} left)")
                            if player.spear_poison_throw:
                                player.spear_poison_throw = False
                                player.spear_poison_strikes = 0
                            if player.spear_dur <= 0:
                                spear_name = player.spear_type
                                player.inventory[spear_name] = max(0, player.inventory.get(spear_name,0)-1)
                                player.spear_type = None; player.spear_dur = 0
                                player.spear_poison_strikes = 0; player.spear_poison_throw = False
                                msg.append(f"💥 {spear_name.replace('_',' ').title()} broke!")
                            if hit_zone != "miss" and not cancelled:
                                if target["hp"] <= 0:
                                    resolve_animal_kill(player, world, target, msg)
                                else:
                                    animal_retaliation(player, world, target, msg)

                elif act in ("commands","togglecommands","toggle commands","showcmds","hidecmds"):
                    if not getattr(player, "graphics_mode", False):
                        msg.append("ℹ️ 'commands' toggle only applies in Graphics Mode.")
                    else:
                        player.show_commands = not getattr(player, "show_commands", True)
                        state = "ON (showing commands panel)" if player.show_commands else "OFF (more map breathing room)"
                        msg.append(f"📜 Commands panel: {state}")
                    msg = msg[-3:]; rn = True; continue

                elif cmd == "save":
                    try:
                        do_save(player, world, save_path, biome, paused=paused)
                        msg.append("💾 Game saved!")
                    except Exception as e:
                        msg.append(f"⚠️ Save failed: {e}")
                elif cmd in ("quit","exit"): game_over = True
                else:
                    all_cmds = ["help","gather","gather all","craft","rest","hunt","eat","drink","inv","inventory",
                                "recipes","shop","buy","sell","quests","achievements","explain","inspect",
                                "identify","trap","traps","wear","remove","equip","unequip","fire","walk","go",
                                "cancel","pause","resume","save","quit","exit","bandage","apply","status","filter",
                                "tutorials","tutorial","commands"]
                    close = [c for c in all_cmds if act and (act in c or c in act or sum(a==b for a,b in zip(act,c)) >= max(1, min(len(act),len(c))-2))]
                    if close:
                        if act and any(c.isalnum() for c in act):
                            msg.append(f"❓ Unknown command '{act}'. Did you mean: {', '.join(close[:3])}? Type 'help' for guide.")
                        else:
                            msg.append("❓ Unknown command. Type 'help' for guide.")
                    else:
                        if act and any(c.isalnum() for c in act):
                            msg.append(f"❓ Unknown command '{act}'. Type 'help' for guide.")
                        else:
                            msg.append("❓ Unknown command. Type 'help' for guide.")
                msg = msg[-3:]

            elif key == '\t':
                # Tab cycles through typeable commands in SIDEBAR_COMMANDS
                if _TAB_CMDS:
                    _tab_idx = (_tab_idx + 1) % len(_TAB_CMDS)
                    buf = _TAB_CMDS[_tab_idx]
                    player._gm_tab_idx = _tab_idx   # pass to renderer for highlight
                    rn = True
            elif key in ('\x7f','\x08'):
                if buf:
                    buf = buf[:-1]
                    _tab_idx = -1
                    player._gm_tab_idx = -1
                rn = True
            elif key == '\x03': game_over = True
            elif key and key.isprintable() and len(key) == 1:
                buf += key
                _tab_idx = -1
                player._gm_tab_idx = -1
                rn = True

            flash_pending_damage()
            # Show any full-screen popup queued by world events (e.g. old-man tips)
            _ppop = getattr(player, "_pending_popup", None)
            if _ppop:
                player._pending_popup = None
                try:
                    term.print_page(_ppop)
                except Exception:
                    pass
            if rn: refresh()
            else:
                # Refresh much more often when an animal is on-screen so its
                # smooth fractional movement is actually visible.
                _anim_near = any(math.hypot(a["x"]-player.x, a["y"]-player.y) <= FOG_RADIUS
                                 for a in world.animals)
                _refresh_iv = 0.1 if _anim_near else 1.0
                if time.time()-last_render >= _refresh_iv: refresh()

    except KeyboardInterrupt: print("\n⚠️ Interrupted")
    except Exception as e:
        crashed = True
        try: term.cleanup()
        except Exception: pass
        print(f"\n⚠️ Error: {e}")
        import traceback; traceback.print_exc()
        try: input("\nTraceback shown above. Press Enter to close...")
        except Exception: pass
    finally:
        if not crashed:
            term.cleanup()
        if save_path:
            try:
                do_save(player, world, save_path, biome,
                        dead=player_died, death_reason=death_reason,
                        paused=paused)
                if player_died:
                    print("\n💀 Run recorded in Past Games.")
                else:
                    print("\n💾 Auto-saved.")
            except Exception as e:
                print(f"\n⚠️ Auto-save failed: {e}")

# ==================== ARCTIC AMBIENCE ("Flowing Into The Darkness" by Nyoko, CC BY 3.0) ====================
_ARCTIC_BGM_OGG_B64 = None  # loaded from assets/arctic_ambience.ogg

_MENU_BGM_OGG_B64 = None  # loaded from assets/audiomass-output-_1_.ogg


if __name__ == "__main__":
    # Returning to the main menu after quit/death: keep relaunching the menu
    # until the player explicitly chooses Exit (which raises SystemExit) or a
    # fatal setup error returns the "exit" sentinel.
    while True:
        try:
            if main() == "exit":
                break
        except SystemExit:
            break
