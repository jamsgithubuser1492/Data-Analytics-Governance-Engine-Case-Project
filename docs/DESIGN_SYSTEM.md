# MMGE design system

**Design north star: make complex measurement feel simple, trustworthy and actionable.**

The product tells one story: data, then understanding, then validation, then a decision, then human action. It never tells the story "data, then AI, then magic".

MMGE should feel like a mature enterprise product that sits between analytics, finance, marketing strategy and executive decision making: clean, calm, intelligent, trustworthy, human, considered and transparent. It should not feel futuristic, "AI first", developer centric, over automated, dark and neon, glossy or overloaded with metrics.

## 1. Principles
1. **Evidence before intelligence.** Every recommendation answers five questions: What happened? Why does it matter? How sure are we? What do we suggest? What should the person do?
2. **Business outcome first.** The visual order is: business outcome, recommendation, evidence, confidence and governance, human decision.
3. **Simple on the surface, rigorous underneath.** Governance sits quietly under every decision and opens when someone wants the detail.
4. **A person is always in control.** The interface makes the approval boundary obvious: analyzed, recommended, reviewed by a person, approved by a person, handed off.
5. **Every screen answers one question:** "What does the user need to know or decide here?" Anything that does not help answer it is removed.

## 2. Colour
Light and predominantly white. No large blocks of saturated colour.

| Token | Value | Use |
| --- | --- | --- |
| `navy-950` / `navy-900` / `navy-800` | #10284A / #18345B / #24466F | Headlines, navigation, primary buttons, key controls. Trust and authority |
| `background` | #F6F8FB | Page, with a faint cool glow at the top right |
| `surface` | #FFFFFF | Cards |
| `surface-subtle` | #F1F5F9 | Quiet panels, segmented controls |
| `surface-blue` | #EDF3FA | Callouts and highlighted panels |
| `border` | #E0E7EF | Hairline card and table borders |
| `border-strong` | #C7D2DF | Inputs and secondary buttons |
| `green-700` / `600` / `500` / `100` | #087F6A / #159A83 / #43B69F / #E5F5F0 | The decision colour: evidence supports action |
| `blue-500` / `100` | #4E8FE7 / #EAF2FC | Analytical information, platform reported results |
| `purple-500` / `100` | #8D82D8 / #F0EDFB | A second method, the attribution model |
| `amber-500` / `100` | #D89B28 / #FFF5DE | Needs review, uncertainty |
| `red-500` / `100` | #D95C63 / #FDEBEC | Risk, invalid, stop |

**Meaning of colour.** Green means "the evidence supports action", not merely "success". Blue is analytical, purple is an alternate method, amber is review, red is risk, navy is the decision and navigation layer.

**Audience tier charts** use blue for what the platform credits and green for what ads caused, with a stacked red and green bar for the spend split. Red marks spend paying for sales that would have happened anyway.

**The three measurement methods** keep the same colours everywhere: platform reported is blue, attribution model is purple, holdout proven is green. They are shown as complementary parts of one story, never as rival products.

Status is never shown by colour alone. Each status pill carries a distinct shape and a text label.

Dark mode exists for people whose system uses it. It keeps the same navy based palette and is not the default look.

## 3. Typography
* **Application text:** Inter, falling back to the system sans serif.
* **Editorial moments:** Georgia, sparingly, for the executive briefing headline and similar hero statements.
* Page title 32 to 38 px, semibold, tight letter spacing. Section heading 18 to 22 px. Card title 15 to 17 px. Body 14 to 15 px with a 1.5 line height. Supporting text 12 to 13 px in the muted colour. Key numbers 28 to 36 px.
* Not every number is large. The hierarchy tells the story rather than competing for attention.

## 4. Layout
* Spacious: 32 px page padding, 24 px between sections, 20 to 24 px card padding, 10 to 14 px corner radius.
* Cards are white with a 1 px border and a very light shadow. They are quiet containers, never floating glass.
* Few metrics per screen. No walls of tiny cards or dense tables.
* Desktop: sidebar plus content, two column analytical layouts. Tablet: stacked cards. Mobile keeps the decision order: briefing, impact, key insight, recommendation, evidence, approval.

## 5. Components
| Component | What it is for |
| --- | --- |
| **Brand mark** | A small branching leaf (data branching into evidence and decisions) in navy and teal green, with the wordmark "MMGE" and "Media Measurement and Governance Engine". Abstract, like an analytics company, not an environmental one |
| **Executive briefing** | The first thing on the home page: the business finding in a serif headline, a plain summary, an impact panel with three supporting figures and a measurement confidence line with a link to the methodology. It interprets the dashboard for the executive and still shows its evidence |
| **Confidence strip** | Four small cards: confidence level, statistically significant campaigns, campaigns ready for a decision, test coverage |
| **Measurement validity** | A ring with the average measurement score and a short breakdown (data coverage, statistical validity, quality checks passed, campaigns ready) |
| **Measurement comparison** | Platform, attribution model and holdout side by side with their colours |
| **Recommendation card** | A decision memo: action, expected impact, evidence, confidence, reason and the human controls |
| **Governance status** | A short list of checks passed for this decision, drawn with check marks and shapes, never emoji |
| **Human decision flow** | Evidence analyzed, recommendation prepared, person reviews, person signs, hand off. The current step is highlighted |
| **Cannibalization meter** | A bar showing how much of a tier's spend pays for sales that would have happened anyway, with the dollar split and the 95% range beneath it. Red, amber or green follows the policy thresholds, and the figure is always printed |
| **Control match card** | The comparison markets' quality: Match passed or Review required, three measures against their standards, the markets used and what matching on audience added. Technical terms stay out of the card |
| **Status pills** | Small, subtle, shape plus text |
| **Buttons** | Primary: navy fill, white text, 7 to 9 px radius. Secondary: white with a light border and navy text |
| **Charts** | Flat, minimal, lightly gridded, annotated where it matters. No 3D, gradients, glow or decorative animation |
| **Empty states** | Helpful and human: "Let's get your first measurement run started." |

## 6. Language
Use: Confident, Leaning, Not yet reliable, Review required, Governance check, Measurement confidence, View evidence, Signed by a person.
Avoid: AI confidence, autonomous, smart engine, neural, next generation, revolutionary, magic.
Where a recommendation is shown, say where it came from: "Recommendation prepared from verified evidence." Recommendations stay tentative ("Consider..."), and facts stay objective. See `docs/VOICE_GUIDE.md`.

The design guidance lists the trust labels Verified, Decision grade, Directional and Needs review. On screen the product uses plainer equivalents for non specialists: **Confident** (Verified), **Leaning** (Directional) and **Not yet reliable** (Needs review). The technical names remain in the Sources section and the methodology.

AI is subordinate to the business decision. It is described as "Recommendations" and "Decision support", never as an autonomous agent. Specialist workers, where shown, read like review steps ("Measurement review: completed"), not characters.

## 6b. Light mode refinement
Light mode is the primary experience and follows five research backed habits of calm, trustworthy interfaces:
1. **Depth through light, not lines.** A white card on a cool off white page, a hairline border and two soft shadows (a 1 px contact shadow and a larger diffuse one) separate surfaces without heavy outlines. Cards lift slightly on hover.
2. **One clear action per area.** Primary buttons are navy and filled; secondary buttons are white with a stronger border; page links look like quiet buttons; the demo notice is a slim quiet strip rather than a heavy callout.
3. **Controls that look like controls.** Segmented choices are a single rounded group with a raised selected option; tabs use a green underline; inputs share one radius and a stronger border; selected tags are soft blue chips.
4. **Visible focus and calm motion.** A 2 px green focus ring and a soft focus halo on inputs support keyboard use; transitions are 150 to 250 ms and switch off for people who prefer reduced motion.
5. **Rhythm and measure.** Generous spacing, line lengths capped near 70 characters, tabular figures for numbers, and a larger gap before each numbered section.

## 6c. Legibility and smoothness standards
* **Contrast:** all body text and labels meet at least 4.5 to 1 against their surface (large text and chart marks 3 to 1), in light and dark. A test checks the token pairs, and the check scans every page for text below the standard, including text dimmed by opacity.
* **Size:** nothing renders below about 12 px. Captions, notes and source lines use the muted colour at full opacity, not a faded one.
* **Form controls:** inputs, selects, radio buttons and checkboxes have a visible border before they are used; disabled buttons stay readable.
* **No sideways scrolling:** tables, including those inside the guides, scroll within their own frame at phone width.
* **Smoothness:** anchor links and scrolling are smooth with a stable scrollbar gutter (no layout jump), charts reserve their height while loading, content that is refreshing fades gently instead of flashing, and motion switches off for people who prefer reduced motion.

## 7. Motion
150 to 250 ms, ease out, for card expansion, navigation, dropdowns and chart changes. No particles, glow, animated gradients, bouncing or typing effects.

## 8. Imagery
Natural, bright, understated and professional: a desk, notebook, coffee, plant, daylight, a laptop, a person reviewing information. Never holograms, neon, robots or futuristic screens. In marketing images the product is the hero (about 60 to 70 percent) and the environment gives human context.

## 9. Where it lives in the code
| Part | File |
| --- | --- |
| Colour, type and spacing tokens, CSS, components | `app/ui.py` |
| Streamlit theme colours | `.streamlit/config.toml` |
| Chart colours and layout | `app/charts.py` |
| Sidebar, brand mark | `app/common.py` |
| Executive briefing and confidence | `app/app.py` |
| Cannibalization meter, control match card | `app/ui.py`; the tier charts are in `app/charts.py` |
| Recommendation, governance status, decision flow | `app/pages/12_Signoff.py` and the decision cards in `app/app.py` |
| Logo file | `docs/img/logo.svg` |
