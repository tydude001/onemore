# Design system for this project (DS Remix export).
# Treat every value below as a hard constraint for UI work.
# Import styles.css instead of recreating these tokens.

taste:
  id: pale
  name: Pale
  summary: >-
    A comfortable, light interface UI pairing soft cool-green and pale lavender accents with stark
    flat-bordered surfaces and elegant editorial typography.
  app_type: WEB_APP
  project_types:
    - saas
  styles:
    - editorial
    - minimal
    - premium
  industry: software
  aesthetics:
    - editorial
    - minimal
    - premium
  tags:
    - editorial
    - minimal
    - premium
  theme:
    default_mode: LIGHT_MODE
    palette_note: >-
      Only the 500 anchor is provided per palette; the full 17-step ramp (100-900) is derived from
      it by the system's heuristic shade tool.
    palettes:
      neutral:
        '500': '#6B736F'
        description: Observed neutral ramp carrying a soft graphite and cool grey tone.
      brand:
        '500': '#589878'
        description: Muted cool-green brand anchor.
      danger:
        '500': '#D9383A'
      warning:
        '500': '#FFFFEB'
      success:
        '500': '#4E8C5A'
      info:
        '500': '#2B6CB0'
      accent:
        '500': '#AE4278'
    colors:
      background:
        light: '#F1F9F5'
        dark: neutral/900
      foreground:
        light: '#161E1A'
        dark: neutral/100
      card:
        light: '#F1F9F5'
        dark: neutral/800
      card-foreground:
        light: '#161E1A'
        dark: neutral/100
      popover:
        light: '#F1F9F5'
        dark: neutral/800
      popover-foreground:
        light: '#161E1A'
        dark: neutral/100
      primary:
        light: accent/500
        dark: accent/500
      primary-foreground:
        light: '#161E1A'
        dark: '#161E1A'
      secondary:
        light: brand/200
        dark: neutral/800
      secondary-foreground:
        light: '#161E1A'
        dark: neutral/100
      muted:
        light: neutral/100
        dark: neutral/800
      muted-foreground:
        light: '#565E5A'
        dark: neutral/400
      accent:
        light: brand/200
        dark: neutral/700
      accent-foreground:
        light: '#161E1A'
        dark: neutral/100
      destructive:
        light: '#B52427'
        dark: danger/600
      destructive-foreground:
        light: '#F7FEFA'
        dark: '#F7FEFA'
      border:
        light: '#161E1A'
        dark: neutral/700
      input:
        light: '#161E1A'
        dark: neutral/700
      ring:
        light: brand/500
        dark: brand/500
      chart-1:
        light: '#589878'
        dark: '#A2CAB6'
      chart-2:
        light: '#AE4278'
        dark: '#AE4278'
      chart-3:
        light: '#4E8C5A'
        dark: '#4E8C5A'
      chart-4:
        light: '#2B6CB0'
        dark: '#2B6CB0'
      chart-5:
        light: '#D9383A'
        dark: '#D9383A'
      sidebar:
        light: brand/150
        dark: neutral/900
      sidebar-foreground:
        light: '#161E1A'
        dark: neutral/100
      sidebar-primary:
        light: accent/500
        dark: brand/400
      sidebar-primary-foreground:
        light: '#161E1A'
        dark: '#161E1A'
      sidebar-accent:
        light: brand/250
        dark: neutral/800
      sidebar-accent-foreground:
        light: '#161E1A'
        dark: neutral/100
      sidebar-border:
        light: '#161E1A'
        dark: neutral/700
      sidebar-ring:
        light: brand/500
        dark: brand/500
    radius:
      base:
        value: 12px
        description: Measured 12px large radius mapping to standard buttons and main containers.
    shadows:
      xs:
        value: 0 1px 2px rgba(15, 23, 42, 0.04)
      sm:
        value: 0 2px 6px rgba(15, 23, 42, 0.06)
      md:
        value: 0 4px 12px -2px rgba(15, 23, 42, 0.08)
      lg:
        value: 0 8px 20px -4px rgba(15, 23, 42, 0.10)
      xl:
        value: 0 12px 28px -6px rgba(15, 23, 42, 0.12)
    gradients:
      brand_wash:
        value: 'linear-gradient(135deg, #FAFAF7 0%, #E3E3CE 100%)'
    fonts:
      sans:
        family: IBM Plex Sans
        description: Editorial serif face used for UI body copy and content.
      display:
        family: DM Serif Display
        description: Clean modern sans-serif face optimized for headings and display labels.
      mono:
        family: JetBrains Mono
        description: Code, metrics, and tabular data.
    typography:
      hero:
        font: display
        size_px: 64
        line_height_px: 61
        weight: 400
        letter_spacing_em: -0.03
        transform: none
      title:
        font: display
        size_px: 32
        line_height_px: 30
        weight: 400
        letter_spacing_em: -0.03
        transform: none
      heading:
        font: sans
        size_px: 20
        line_height_px: 28
        weight: 700
        letter_spacing_em: 0
        transform: none
      body:
        font: sans
        size_px: 16
        line_height_px: 16
        weight: 600
        letter_spacing_em: 0
        transform: none
      caption:
        font: sans
        size_px: 14
        line_height_px: 18
        weight: 500
        letter_spacing_em: 0
        transform: none
      label:
        font: display
        size_px: 14
        line_height_px: 18
        weight: 600
        letter_spacing_em: 0
        transform: none
      overline:
        font: display
        size_px: 12
        line_height_px: 16
        weight: 700
        letter_spacing_em: 0.08
        transform: uppercase
  style_guidelines:
    visual_direction:
      title: Visual Direction
      recommendations:
        - >-
          Combine soft warm-white surfaces with stark flat-black hairline borders and hard offset
          shadows to create a tactile, paper-like interface.
    hierarchy:
      title: Hierarchy
      recommendations:
        - >-
          Lead each core view with an oversized, light-weight display headline to establish an
          editorial rhythm before dropping into dense content grids.
        - >-
          Differentiate primary triggers using the signature pale lavender fill, while framing
          secondary settings with crisp, high-contrast borders.
    layout:
      title: Layout
      recommendations:
        - >-
          Align interactive controls to a strict four-pixel base unit to ensure perfect mechanical
          alignment across wide data views.
    components:
      title: Components
      recommendations:
        - >-
          Render buttons and interactive inputs with a generous twelve-pixel corner radius to
          contrast against sharp-bordered data blocks.
    typography:
      title: Typography
      recommendations:
        - >-
          Set body text and labels in the warm, editorial serif face to establish a premium,
          literary feel across dense informational layouts.
        - >-
          Use the clean sans-serif display face exclusively for high-impact headers and numerical
          indicators to maximize visual punch and legibility.
    color_and_effects:
      title: Color & Effects
      recommendations:
        - >-
          Deploy a restrained palette of muted cool greens and pale lavenders, reserving pure black
          solely for borders, primary ink, and hard shadows.
        - >-
          Ensure all dark mode transitions shift to deep graphite surfaces while maintaining the
          flat-bordered, hard-shadow personality.
  quality_bar:
    title: Quality Bar
    checks:
      - id: pill-corner-contrast
        label: Pill Corner Contrast
        recommendation: >-
          Primary interactive elements must carry a 12px corner radius to clearly contrast against
          the sharp, flat grid layouts.
      - id: editorial-type-hierarchy
        label: Editorial Type Hierarchy
        recommendation: >-
          The primary page heading must render at exactly 64px with a light 400 weight and tight
          letter-spacing, immediately establishing the brand's editorial character.
      - id: contrast-compliance
        label: Contrast Compliance
        recommendation: >-
          All body copy set in Source Serif 4 must maintain a minimum 4.5:1 contrast ratio against
          the warm-white page background, using the dark neutral/800 ink.
active_remix:
  mode: light
  brand: '#589878'
  display_font: DM Serif Display
  shape: soft
  depth: soft
  spacing: system
  spacing_value: null
craft: >
  # Craft (universal core + conditional craft)


  How to apply this design system well. These rules contain no brand look of their own — all

  per-system character comes from the tokens and taste notes above; this section only governs

  how they are composed. **Precedence:** the design system above is the authority on how things

  look — where its own notes conflict with a rule here, the design system wins. And the user's

  request is the authority on what the screen IS — notes above that describe the source

  product's screens (workspaces, dashboards, panels) are its aesthetic heritage, not an

  instruction to build that kind of screen.


  ## Universal — applies to every screen (screen-agnostic craft)


  - **Surface definition.** Every container is visually separable from what it sits on — at least
  one
    honest edge cue: a hairline border, a ≥4% tonal step from its parent, or a real shadow. Never a card
    whose fill matches its section with no border; never nested surfaces that dissolve together.
  - **Accent discipline.** The brand/primary color is a scalpel, not paint: spend it on the primary
    action, the active/selected/focused state, and at most **one** brand or data highlight per screen.
    Everything else rides neutral background / card / muted / border tokens. A screen flooded with brand
    color reads unfinished, not bold.
  - **Restraint ledger.** Beauty is also what you don't do: at most one glow and two gradient
  directions
    screen-wide; decoration only where content doesn't reach; no ornament between a heading and its own
    action. Every decorative element must answer "what does this make clearer or more felt?" — if the
    answer is "nothing," remove it.
  - **Type with intent.** The measured faces/scale are fixed; character comes from *usage*, and the
  move
    must fit the surface — a marketing page earns a dramatic display move; a working screen earns a
    crisp, tight, legible hierarchy at UI scale (display-hero type on a dense tool is a smell). Chrome
    and wayfinding are never display type; data numerals are tabular (mono or sans), never the
    decorative face. Headings stay roman — italics live as emphasis inside running text, not as
    display styling (unless the system's own type says otherwise).
  - **Anti-default.** If the screen could pass for a generic template with the colors swapped, it is
  not
    done. Make the brand unmistakable through the accent's *use*, the type, the radius + density, and
    **one** signature detail — never by importing another surface's clichés.
  - **Honest content.** Never invent proof — no made-up adoption counts, growth percentages,
    testimonials, client logos, or awards. Use the user's real content, a neutral placeholder, or
    leave the element out and let the layout carry it. Never hand-draw fake browser bars, phone
    frames, or editor chrome around content — show the content itself, or nothing.
  - **Interaction integrity.** Buttons, links, tabs, and nav labels never wrap to two lines; display
    headlines wrap cleanly, never clipping mid-word; nothing overflows horizontally at any width;
    keyboard focus gets an instant, clearly visible ring.
  - **Token fidelity.** Every design value comes from a token: colors, radii, shadows, and fonts
  from
    the system's variables — never a literal hex, a hand-picked shadow, or a substitute font. For a
    translucent or composited value (a scrim, a glow, a hairline over a fill), derive it from a token
    (an opacity modifier or color-mix), never a literal rgba. If the system specifies square corners and
    a hard shadow, the screen shows square corners and that hard shadow — not a rounded, soft substitute.

  ## Conditional — apply ONLY the layer that matches the screen the user asked for


  **First name the screen honestly from the user's prompt.** Then apply the matching guidance. Do
  not

  cross layers, and **do not add elements from a layer the screen doesn't call for** — a screen that
  is

  not a data view must not sprout KPI tiles, charts, filter bars, or data tables to satisfy a
  template.


  - **If it's a data / dashboard / admin / table view:** density done well (comfortable rows, tight
    control clusters, one spacing rhythm); a populated working state (real rows/cards, not empty feature
    boxes); tables with aligned tabular numerals, status as badges, row hover, one visible selected row,
    and control states that agree with the data shown. KPI tiles, *if the screen has them*, are
    value + label + delta. **At most one** chart, of a real metric for this domain, token-colored and
    axis-labeled — never a decorative sine wave or filler sparkline. Exactly one unambiguous primary
    action.

  - **If it's a focused task / tool / player / capture / monitor / form / wizard (not a data
  view):**
    the screen's real job dominates the frame; chrome recedes. Honor the screen's own nature — a player
    looks like a player, a monitor like a monitor, a form like a form — with the design system's color,
    type, radius, and depth applied to *those* elements. **No dashboard furniture**: no KPI tiles, no
    charts, no data tables, no filter chrome unless the task itself is about that data. Real-time or
    safety-critical readouts get calm, unambiguous, high-legibility treatment over decoration.

  - **If it's a marketing / landing surface:** editorial art direction belongs here — section rhythm
    (modulate surface temperature, density, and scale; one oversized moment; at least one full-bleed
    band) and considered visual treatments. Never put this on a working app screen.

  - **Mobile:** follow the platform's native idioms for the screen's type (e.g. an app screen:
  compact
    top bar, one focused column, a bottom tab bar, ≥44px targets, safe areas) — the same conditional
    rules above still decide what content belongs.

  ## Imagery (universal)


  - **Imagery is content, not decoration** on working screens: images are data (covers, products,
    avatars, places) in purposeful containers, one consistent treatment across siblings — never a lone
    photo floating in a box, never marketing's decorative fades on a work screen. When a moment needs
    atmosphere, build it from the token system (tinted panels, token gradients, geometry).
