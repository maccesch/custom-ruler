use crate::cad::{self, CadMsg, Model};
use crate::dial::{
    baseline_y, compute_dial, cut_outline_path, fmt_step, latch_fold_lines, step_label_dx_mm,
    tick_angle_deg, tick_length, Dial, CAP_HEIGHT_RATIO, CROSSHAIR_HALF_MM, CUT_STROKE_MM,
    FOLD_DASH_MM, LATCH_OUTER_R_MM, NUM_R_MM, NUM_SIZE_MM, STEP_ICON_ARROW_MM,
    STEP_ICON_ARROW_STROKE_MM, STEP_ICON_GAP_MM, STEP_ICON_HEAD, STEP_ICON_H_MM,
    STEP_ICON_LABEL_GAP_MM, STEP_ICON_STROKE_MM, STEP_ICON_TAIL_MM, STEP_ICON_W_MM, TICK_OUTER_MM,
    UNIT_LABEL_Y_MM, UNIT_SIZE_MM,
};
use crate::paper::PaperSize;
use crate::scale::{
    compute_ticks, density_units_per_mm, parse_copies, parse_font_mm, parse_mm, parse_units, Tick,
    TickKind,
};
use leptos::prelude::*;
use leptos_meta::{provide_meta_context, MetaTags, Stylesheet, Title};
use leptos_router::{
    components::{Route, Router, Routes},
    StaticSegment,
};

/// Fallback label size when the input is mid-edit or invalid.
const DEFAULT_FONT_MM: f64 = 3.0;

/// Rough advance width of a digit as a fraction of font size, for sans-serif.
/// Labels are rotated, so this sets how far they reach *down* the page.
const DIGIT_ADVANCE: f64 = 0.62;

/// Vertical gap between stacked copies, applied as inline margin-bottom.
const COPY_GAP_MM: f64 = 4.0;

/// Baseline the rotated labels start from; they read upward from here.
const LABEL_BASE_Y: i8 = 13;

/// Horizontal row under the rotated numerals: the step label at the 0 end and
/// the optional ruler name at the max end.
const FOOTER_GAP_MM: f64 = 2.0;
/// Distance from the 0 end to the start of the step label.
const FOOTER_STEP_MARGIN_MM: f64 = 2.0;
/// Distance from the max end to the right edge of the name.
const FOOTER_NAME_MARGIN_MM: f64 = 1.0;
/// Room below the footer baseline for descenders, as a fraction of the font.
const FOOTER_DESCENDER: f64 = 0.25;
/// Blank paper below the footer row.
const FOOTER_BOTTOM_PAD_MM: f64 = 0.5;
/// The footer's step icon and label are a little smaller than the name and
/// the scale numerals, so they read as an annotation.
const FOOTER_STEP_SIZE_FACTOR: f64 = 0.75;

/// Size of the footer's step icon + label text.
fn footer_step_size_mm(font_mm: f64) -> f64 {
    font_mm * FOOTER_STEP_SIZE_FACTOR
}

/// Bottom of the rotated number labels, as a function of the longest label
/// and the font size.  Labels start at [`LABEL_BASE_Y`] and advance down the
/// page by roughly [`DIGIT_ADVANCE`] per digit.
fn labels_bottom_mm(label_digits: usize, font_mm: f64) -> f64 {
    LABEL_BASE_Y as f64 + label_digits as f64 * font_mm * DIGIT_ADVANCE
}

/// Baseline of the horizontal footer row, clear of the rotated labels.
fn footer_baseline_mm(label_digits: usize, font_mm: f64) -> f64 {
    labels_bottom_mm(label_digits, font_mm) + FOOTER_GAP_MM + font_mm * CAP_HEIGHT_RATIO
}

/// Height of the scale SVG: the footer row plus its descender allowance.
fn scale_svg_height_mm(label_digits: usize, font_mm: f64) -> f64 {
    footer_baseline_mm(label_digits, font_mm) + font_mm * FOOTER_DESCENDER + FOOTER_BOTTOM_PAD_MM
}

/// The footer's step icon and label laid out as one horizontal group: the
/// icon is scaled to the label's x-height, sits left of the text, and its
/// bars bottom on the baseline.
#[derive(Clone, Copy, Debug, PartialEq)]
struct FooterStepLayout {
    icon_scale: f64,
    icon_x: f64,
    icon_y: f64,
    label_x: f64,
}

fn footer_step_layout(size_mm: f64, footer_y: f64) -> FooterStepLayout {
    let icon_scale = size_mm / UNIT_SIZE_MM;
    let icon_w = STEP_ICON_W_MM * icon_scale;
    let gap = STEP_ICON_LABEL_GAP_MM * icon_scale;
    FooterStepLayout {
        icon_scale,
        icon_x: FOOTER_STEP_MARGIN_MM + icon_w / 2.0,
        icon_y: footer_y - STEP_ICON_H_MM * icon_scale / 2.0,
        label_x: FOOTER_STEP_MARGIN_MM + icon_w + gap,
    }
}

/// Blank paper round the outermost cut line (the latch ends), in the print
/// view.  Kept off the sheet edge so the cut guides print completely.
const DIAL_MARGIN_MM: f64 = 2.0;

/// Half the printed dial sheet, centre to edge: the rim plus the latches,
/// plus the blank margin.
fn dial_sheet_r_mm() -> f64 {
    LATCH_OUTER_R_MM + DIAL_MARGIN_MM
}

/// Every tick starts here and hangs down; the rule's edge runs along the top.
const TICK_TOP_Y: i8 = 2;

/// Schematic preview of the ruler bar's 0 end, in the ruler tab.  Not to
/// scale: it only has to show where the 0 tick lands.
const PREVIEW_W: i8 = 112;
const PREVIEW_TOP: i8 = 5;
const PREVIEW_BAR_H: i8 = 22;
const PREVIEW_CORNER_R: i8 = 3;
/// Room around the bar so its outline is not clipped by the viewBox; the
/// open right side runs into the bleed and off the edge.
const PREVIEW_BLEED: i8 = 1;
const PREVIEW_STROKE: i8 = 1;
const PREVIEW_SPACING: i8 = 4;
/// Tick intervals drawn
const PREVIEW_INTERVALS: usize = 30;
/// Distance from the bar's edge to the 0 tick when Margin at 0 is on: about
/// two minor intervals, as at the defaults (ruler.py's PAD at 1 unit/mm).
const PREVIEW_GAP: i8 = 6;

/// Length and stroke width of preview tick `i`: majors every 10 units,
/// mediums every 5, minors otherwise.
fn preview_tick(i: usize) -> (i8, i8) {
    match (i % 10, i % 5) {
        (0, _) => (13, 3),
        (_, 0) => (10, 2),
        _ => (8, 1),
    }
}

/// The preview's viewBox: the bar plus the stroke bleed on every side.
fn preview_view_box() -> String {
    format!(
        "{} {} {} {}",
        -PREVIEW_BLEED,
        PREVIEW_TOP - PREVIEW_BLEED,
        PREVIEW_W + 2 * PREVIEW_BLEED,
        PREVIEW_BAR_H + 2 * PREVIEW_BLEED,
    )
}

/// The preview bar's outline: a left end with rounded corners, open at the
/// right because the bar carries on, so the top and bottom edges run out to
/// the viewBox edge.
fn preview_bar_path() -> String {
    let w = PREVIEW_W + PREVIEW_BLEED;
    format!(
        "M {w} {top} H {r} A {r} {r} 0 0 0 0 {left_top} V {left_bottom} \
         A {r} {r} 0 0 0 {r} {bottom} H {w}",
        top = PREVIEW_TOP,
        r = PREVIEW_CORNER_R,
        left_top = PREVIEW_TOP + PREVIEW_CORNER_R,
        left_bottom = PREVIEW_TOP + PREVIEW_BAR_H - PREVIEW_CORNER_R,
        bottom = PREVIEW_TOP + PREVIEW_BAR_H,
    )
}

impl TickKind {
    /// Where a tick of this level ends. Tops are shared, so the level reads
    /// from the depth.
    fn bottom(self) -> f64 {
        match self {
            TickKind::Minor => 7.0,
            TickKind::Medium => 9.5,
            TickKind::Major => 11.0,
        }
    }

    fn stroke(self) -> &'static str {
        match self {
            TickKind::Minor => "0.15",
            TickKind::Medium => "0.2",
            TickKind::Major => "0.3",
        }
    }
}

pub fn shell(options: LeptosOptions) -> impl IntoView {
    view! {
        <!DOCTYPE html>
        <html lang="en">
            <head>
                <meta charset="utf-8"/>
                <meta name="viewport" content="width=device-width, initial-scale=1"/>
                <AutoReload options=options.clone() />
                <HydrationScripts options/>
                <MetaTags/>
            </head>
            <body>
                <App/>
            </body>
        </html>
    }
}

#[component]
pub fn App() -> impl IntoView {
    provide_meta_context();

    view! {
        <Stylesheet id="leptos" href="/pkg/custom-ruler.css"/>
        <Title text="Scale Generator"/>

        <Router>
            <main>
                <Routes fallback=|| "Page not found.".into_view()>
                    <Route path=StaticSegment("") view=AppContent/>
                </Routes>
            </main>
        </Router>
    }
}

/// The step icon drawn left of the dial's unit label: two tick bars with solid
/// arrowheads pointing inward and a line out to each side, as between two
/// adjacent dial ticks.  Centred on (`x`, `y`) in the SVG's millimetres;
/// `cad/dial_svg.py` draws the same mark.
#[component]
fn StepIcon(x: f64, y: f64, scale: f64) -> impl IntoView {
    let gap = STEP_ICON_GAP_MM * scale;
    let arrow = STEP_ICON_ARROW_MM * scale;
    let tail = STEP_ICON_TAIL_MM * scale;
    let height = STEP_ICON_H_MM * scale;
    let stroke = STEP_ICON_STROKE_MM * scale;
    let arrow_stroke = STEP_ICON_ARROW_STROKE_MM * scale;
    (0..2)
        .map(|side| {
            let s = if side == 0 { -1.0 } else { 1.0 };
            let bar_x = x + s * gap / 2.0;
            let base_x = bar_x + s * arrow;
            let tail_x = base_x + s * tail;
            let head = arrow * STEP_ICON_HEAD;
            view! {
                <line
                    x1=format!("{bar_x:.4}")
                    y1=format!("{:.4}", y - height / 2.0)
                    x2=format!("{bar_x:.4}")
                    y2=format!("{:.4}", y + height / 2.0)
                    stroke="black"
                    stroke-width=format!("{stroke}")
                />

                // Arrow
                <path
                    d=format!(
                        "M {base_x:.4} {:.4} L {bar_x:.4} {y:.4} L {base_x:.4} {:.4} Z",
                        y - head,
                        y + head,
                    )
                    fill="black"
                    stroke="none"
                />
                <line
                    x1=format!("{base_x:.4}")
                    y1=format!("{y:.4}")
                    x2=format!("{tail_x:.4}")
                    y2=format!("{y:.4}")
                    stroke="black"
                    stroke-width=format!("{arrow_stroke}")
                />
            }
        })
        .collect_view()
}

/// The printable dial face: the print view draws this at 1:1.
fn dial_face(d: &Dial, name: &str) -> impl IntoView {
    let c = dial_sheet_r_mm();
    let size = 2.0 * c;
    let step_txt = fmt_step(d.step);
    let label = format!("{step_txt} {name}");
    // icon and label are one group, centred on the dial; both rows share the
    // label's y so the icon's bars straddle the numerals' height
    let dx = step_label_dx_mm(&label, UNIT_SIZE_MM);
    let icon_cx = c + dx.icon;
    let label_cx = c + dx.label;
    let row_y = c + UNIT_LABEL_Y_MM;
    let label_baseline = baseline_y(row_y, UNIT_SIZE_MM);
    // icon height is the font's x-height, and its bottom sits on the baseline
    let icon_y = label_baseline - STEP_ICON_H_MM / 2.0;

    view! {
        <svg
            width=format!("{size:.4}mm")
            height=format!("{size:.4}mm")
            viewBox=format!("0 0 {size:.4} {size:.4}")
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="Printable caliper dial face"
            class="block bg-white text-black"
        >
            <path
                d=cut_outline_path(c)
                fill="none"
                stroke="black"
                stroke-width=format!("{CUT_STROKE_MM}")
            />
            {(0..d.divisions)
                .map(|i| {
                    let a = tick_angle_deg(i, d.divisions).to_radians();
                    let r1 = TICK_OUTER_MM - tick_length(i, d.label_every);
                    view! {
                        <line
                            x1=format!("{:.4}", c + r1 * a.cos())
                            y1=format!("{:.4}", c - r1 * a.sin())
                            x2=format!("{:.4}", c + TICK_OUTER_MM * a.cos())
                            y2=format!("{:.4}", c - TICK_OUTER_MM * a.sin())
                            stroke="black"
                            stroke-width="0.3"
                        />
                    }
                })
                .collect_view()}
            {(0..d.divisions)
                .step_by(d.label_every.max(1))
                .map(|i| {
                    let deg = tick_angle_deg(i, d.divisions);
                    let a = deg.to_radians();
                    let x = c + NUM_R_MM * a.cos();
                    let y = c - NUM_R_MM * a.sin();
                    let val = format!("{:.4}", i as f64 * d.step).trim_end_matches('0').trim_end_matches('.').to_string();
                    view! {
                        <text
                            x=format!("{x:.4}")
                            y=format!("{y:.4}")
                            transform=format!("rotate({:.2} {x:.4} {y:.4})", 90.0 - deg)
                            text-anchor="middle"
                            dominant-baseline="central"
                            font-size=format!("{NUM_SIZE_MM}")
                            fill="black"
                            font-family="AlteDIN, sans-serif"
                            font-weight="400"
                        >{val}</text>
                    }
                })
                .collect_view()}
            <StepIcon x=icon_cx y=icon_y scale=1.0/>
            <text
                x=format!("{label_cx:.4}")
                y=format!("{label_baseline:.4}")
                text-anchor="middle"
                font-size=format!("{UNIT_SIZE_MM}")
                fill="black"
                font-family="AlteDIN Bold, sans-serif"
                font-weight="700"
            >{label}</text>
            <line
                x1=format!("{:.4}", c - CROSSHAIR_HALF_MM)
                y1=format!("{c:.4}")
                x2=format!("{:.4}", c + CROSSHAIR_HALF_MM)
                y2=format!("{c:.4}")
                stroke="black"
                stroke-width=format!("{CUT_STROKE_MM}")
            />
            <line
                x1=format!("{c:.4}")
                y1=format!("{:.4}", c - CROSSHAIR_HALF_MM)
                x2=format!("{c:.4}")
                y2=format!("{:.4}", c + CROSSHAIR_HALF_MM)
                stroke="black"
                stroke-width=format!("{CUT_STROKE_MM}")
            />
            // dashed fold lines: where each latch bends up out of the disc
            {latch_fold_lines(c)
                .into_iter()
                .map(|(x1, y1, x2, y2)| {
                    view! {
                        <line
                            x1=format!("{x1:.4}")
                            y1=format!("{y1:.4}")
                            x2=format!("{x2:.4}")
                            y2=format!("{y2:.4}")
                            stroke="black"
                            stroke-width=format!("{CUT_STROKE_MM}")
                            stroke-dasharray=FOLD_DASH_MM
                        />
                    }
                })
                .collect_view()}
        </svg>
    }
}

#[component]
fn AppContent() -> impl IntoView {
    let (units_raw, set_units_raw) = signal("150".to_string());
    let (sample_mm_raw, set_sample_mm_raw) = signal("10".to_string());
    let (max_raw, set_max_raw) = signal("1000".to_string());
    let (font_raw, set_font_raw) = signal("3.0".to_string());
    let (copies_raw, set_copies_raw) = signal("1".to_string());
    let (paper_raw, set_paper_raw) = signal("A4".to_string());
    let (ruler_name, set_ruler_name) = signal(String::new());

    let units_res = Memo::new(move |_| parse_units(&units_raw.get()).map_err(|e| e.to_string()));
    let max_res = Memo::new(move |_| parse_units(&max_raw.get()).map_err(|e| e.to_string()));
    let sample_mm_res =
        Memo::new(move |_| parse_mm(&sample_mm_raw.get()).map_err(|e| e.to_string()));
    let font_res = Memo::new(move |_| parse_font_mm(&font_raw.get()).map_err(|e| e.to_string()));
    let copies_res = Memo::new(move |_| parse_copies(&copies_raw.get()).map_err(|e| e.to_string()));
    let paper = Memo::new(move |_| PaperSize::parse(&paper_raw.get()).unwrap_or(PaperSize::A4));
    let printable_mm = Memo::new(move |_| paper.get().printable_mm());

    let density = Memo::new(move |_| match (units_res.get(), sample_mm_res.get()) {
        (Ok(u), Ok(mm)) => density_units_per_mm(u, mm),
        _ => None,
    });

    // Everything the 3D generator needs, or None while an input is invalid.
    let cad_params =
        Memo::new(
            move |_| match (units_res.get(), sample_mm_res.get(), max_res.get()) {
                (Ok(u), Ok(mm), Ok(max)) => {
                    Some((u, mm, max, font_res.get().unwrap_or(DEFAULT_FONT_MM)))
                }
                _ => None,
            },
        );

    let scale = Memo::new(move |_| match (max_res.get(), density.get()) {
        (Ok(max), Some(d)) => compute_ticks(max, d),
        _ => None,
    });

    let ticks = Memo::new(move |_| match scale.get() {
        Some((_steps, ticks)) => ticks,
        None => Vec::new(),
    });
    let steps = Memo::new(move |_| scale.get().map(|(steps, _ticks)| steps));

    let total_mm = Memo::new(move |_| steps.get().map(|s| s.total_mm).unwrap_or(0.0));

    let font_mm = Memo::new(move |_| font_res.get().unwrap_or(DEFAULT_FONT_MM));

    let pad_mm = Memo::new(move |_| (font_mm.get() * 0.75).max(2.0));
    let svg_mm = Memo::new(move |_| total_mm.get() + 2.0 * pad_mm.get());

    let label_digits = Memo::new(move |_| {
        ticks
            .get()
            .iter()
            .filter(|t| t.show_label)
            .map(|t| t.value)
            .max()
            .map(|v| v.to_string().len())
            .unwrap_or(1)
    });
    let svg_h = Memo::new(move |_| scale_svg_height_mm(label_digits.get(), font_mm.get()));

    let copies_eff = Memo::new(move |_| copies_res.get().unwrap_or(1));

    let stack_h_mm = Memo::new(move |_| {
        let n = copies_eff.get() as f64;
        n * svg_h.get() + (n - 1.0).max(0.0) * COPY_GAP_MM
    });

    // Paper dial face for the caliper: same derivation as src/dial.rs.
    // The unit name lives here so the print view and the 3D build share it.
    let unit_name = RwSignal::new("u".to_string());
    let dial = Memo::new(move |_| density.get().and_then(compute_dial));
    let dial_size_mm = Memo::new(move |_| 2.0 * dial_sheet_r_mm());

    let dial_view = move || dial.get().map(|d| dial_face(&d, &unit_name.get()));

    let scale_svg = move || {
        let steps_now = steps.get();
        let footer_y = footer_baseline_mm(label_digits.get(), font_mm.get());
        let step_size = footer_step_size_mm(font_mm.get());
        let footer_step = footer_step_layout(step_size, footer_y);
        let step_label = steps_now.map(|s| {
            let unit = unit_name.get();
            let unit = unit.trim();
            if unit.is_empty() {
                s.minor_units.to_string()
            } else {
                format!("{} {}", s.minor_units, unit)
            }
        });
        let ruler_name = ruler_name.get().trim().to_string();
        let has_scale = steps_now.is_some();
        view! {
            <svg
                width=move || format!("{:.4}mm", svg_mm.get())
                height=move || format!("{:.4}mm", svg_h.get())
                viewBox=move || {
                    format!(
                        "{:.4} 0 {:.4} {:.4}",
                        -pad_mm.get(),
                        svg_mm.get(),
                        svg_h.get(),
                    )
                }
                preserveAspectRatio="xMinYMin meet"
                role="img"
                aria-label="Printable measuring scale"
                class="block bg-white text-black"
            >
                <For
                    each=move || ticks.get()
                    key=|t: &Tick| (t.value, t.x_mm.to_bits(), t.kind, t.show_label)
                    let:tick
                >
                    {
                        let y2 = tick.kind.bottom();
                        let x = format!("{:.4}", tick.x_mm);
                        let line = view! {
                            <line
                                x1=x.clone()
                                y1=format!("{TICK_TOP_Y}")
                                x2=x.clone()
                                y2=format!("{y2}")
                                stroke="black"
                                stroke-width=tick.kind.stroke()
                            />
                        };
                        let label = tick.show_label.then(|| {
                            view! {
                                <text
                                    x=x.clone()
                                    y=format!("{LABEL_BASE_Y}")
                                    transform=format!("rotate(90 {x} {LABEL_BASE_Y})")
                                    text-anchor="start"
                                    dominant-baseline="central"
                                    font-size=move || {
                                        format!("{:.3}", font_mm.get())
                                    }
                                    fill="black"
                                    font-family="AlteDIN, sans-serif"
                                    font-weight="400"
                                >{tick.value}</text>
                            }
                        });
                        view! { {line} {label} }
                    }
                </For>
                {step_label.map(|label| {
                    view! {
                        <StepIcon
                            x=footer_step.icon_x
                            y=footer_step.icon_y
                            scale=footer_step.icon_scale
                        />
                        <text
                            x=format!("{:.4}", footer_step.label_x)
                            y=format!("{footer_y:.4}")
                            text-anchor="start"
                            font-size=format!("{:.3}", step_size)
                            fill="black"
                            font-family="AlteDIN Bold, sans-serif"
                            font-weight="700"
                        >{label}</text>
                    }
                })}
                {(has_scale && !ruler_name.is_empty())
                    .then(|| {
                        view! {
                            <text
                                x=format!(
                                    "{:.4}",
                                    total_mm.get() - FOOTER_NAME_MARGIN_MM,
                                )
                                y=format!("{footer_y:.4}")
                                text-anchor="end"
                                font-size=format!("{:.3}", font_mm.get())
                                fill="black"
                                font-family="AlteDIN, sans-serif"
                                font-weight="400"
                            >{ruler_name}</text>
                        }
                    })}
            </svg>
        }
    };

    view! {
        <main class="min-h-screen bg-muted/40">
            <style>
                {move || format!("@page {{ size: {}; }}", paper.get().css_size())}
            </style>
            <div class="print-page mx-auto max-w-4xl px-4 py-8">
                <header class="no-print mb-6">
                    <h1 class="text-2xl font-semibold tracking-tight">"Scale Generator"</h1>
                    <p class="text-sm text-muted-foreground">
                        "Prints an exact 1:1 measuring scale. Calibrate with a sample you counted and measured, then set where the scale ends."
                    </p>
                </header>

                <section class="no-print card mb-6">
                    <header>
                        <h3>"Inputs"</h3>
                        <p>"Units counted ÷ measured mm = units per mm. The scale runs 0 to Max units at that density."</p>
                    </header>
                    <section>
                        <div class="grid gap-4 sm:grid-cols-3">
                            <div role="group" class="field">
                                <label for="units">"Units counted"</label>
                                <input
                                    id="units"
                                    class="input"
                                    type="number"
                                    min="1"
                                    step="1"
                                    bind:value=(units_raw, set_units_raw)
                                    aria-invalid=move || {
                                        if units_res.get().is_err() { "true" } else { "false" }
                                    }
                                />
                                {move || {
                                    units_res
                                        .get()
                                        .err()
                                        .map(|e| {
                                            view! { <p role="alert" class="text-sm text-destructive">{e}</p> }
                                        })
                                }}
                            </div>

                            <div role="group" class="field">
                                <label for="sample-mm">"per mm"</label>
                                <input
                                    id="sample-mm"
                                    class="input"
                                    type="number"
                                    min="0"
                                    step="any"
                                    bind:value=(sample_mm_raw, set_sample_mm_raw)
                                    aria-invalid=move || {
                                        if sample_mm_res.get().is_err() { "true" } else { "false" }
                                    }
                                />
                                {move || {
                                    sample_mm_res
                                        .get()
                                        .err()
                                        .map(|e| {
                                            view! { <p role="alert" class="text-sm text-destructive">{e}</p> }
                                        })
                                }}
                            </div>

                            <div role="group" class="field">
                                <label for="max-units">"Max units (scale ends here)"</label>
                                <input
                                    id="max-units"
                                    class="input"
                                    type="number"
                                    min="1"
                                    step="1"
                                    bind:value=(max_raw, set_max_raw)
                                    aria-invalid=move || {
                                        if max_res.get().is_err() { "true" } else { "false" }
                                    }
                                />
                                {move || {
                                    max_res
                                        .get()
                                        .err()
                                        .map(|e| {
                                            view! { <p role="alert" class="text-sm text-destructive">{e}</p> }
                                        })
                                }}
                            </div>

                            <div role="group" class="field">
                                <label for="unit-name">"Unit name"</label>
                                <input
                                    id="unit-name"
                                    class="input"
                                    type="text"
                                    maxlength="6"
                                    bind:value=(unit_name, unit_name.write_only())
                                />
                                <p class="text-sm text-muted-foreground">
                                    "Suffix for the printed scale, the paper dial and the 3D build."
                                </p>
                            </div>

                            <div role="group" class="field">
                                <label for="label-size">"Label size (mm)"</label>
                                <input
                                    id="label-size"
                                    class="input"
                                    type="number"
                                    min="0.5"
                                    max="20"
                                    step="0.1"
                                    bind:value=(font_raw, set_font_raw)
                                    aria-invalid=move || {
                                        if font_res.get().is_err() { "true" } else { "false" }
                                    }
                                />
                                {move || {
                                    font_res
                                        .get()
                                        .err()
                                        .map(|e| {
                                            view! { <p role="alert" class="text-sm text-destructive">{e}</p> }
                                        })
                                }}
                            </div>

                            <div role="group" class="field">
                                <label for="ruler-name">"Name (on ruler)"</label>
                                <input
                                    id="ruler-name"
                                    class="input"
                                    type="text"
                                    maxlength="32"
                                    placeholder="Optional"
                                    bind:value=(ruler_name, set_ruler_name)
                                />
                                <p class="text-sm text-muted-foreground">
                                    "Printed horizontally near the max end of the scale."
                                </p>
                            </div>

                            <div role="group" class="field">
                                <label for="copies">"Scales per page"</label>
                                <input
                                    id="copies"
                                    class="input"
                                    type="number"
                                    min="1"
                                    max="50"
                                    step="1"
                                    bind:value=(copies_raw, set_copies_raw)
                                    aria-invalid=move || {
                                        if copies_res.get().is_err() { "true" } else { "false" }
                                    }
                                />
                                {move || {
                                    copies_res
                                        .get()
                                        .err()
                                        .map(|e| {
                                            view! { <p role="alert" class="text-sm text-destructive">{e}</p> }
                                        })
                                }}
                            </div>

                            <div role="group" class="field">
                                <label for="paper">"Paper size"</label>
                                <select
                                    id="paper"
                                    class="input"
                                    bind:value=(paper_raw, set_paper_raw)
                                >
                                    <option value="A4">"A4"</option>
                                    <option value="US Letter">"US Letter"</option>
                                </select>
                                <p class="text-sm text-muted-foreground">
                                    "Landscape sheet the print dialog targets."
                                </p>
                            </div>
                        </div>
                    </section>
                    <footer class="flex flex-wrap items-center gap-3">
                        <button class="btn" onclick="window.print()">"Print scale"</button>
                        <p class="text-sm text-muted-foreground">
                            {move || {
                                steps
                                    .get()
                                    .map(|s| {
                                        let last = ticks.get().last().map(|t| t.value).unwrap_or(0);
                                        format!(
                                            "{} u / {} mm = {:.3} units/mm · Scale 0–{} u · Length {:.2} mm · minor every {} u ({:.2} mm) · major every {} u · last tick {} u · {} ticks · labels {:.2} mm · {} per page ({:.1} mm tall) · {}",
                                            units_raw.get(),
                                            sample_mm_raw.get(),
                                            density.get().unwrap_or(0.0),
                                            max_raw.get(),
                                            s.total_mm,
                                            s.minor_units,
                                            s.minor_mm,
                                            s.major_units,
                                            last,
                                            ticks.get().len(),
                                            font_mm.get(),
                                            copies_eff.get(),
                                            stack_h_mm.get(),
                                            paper.get().label(),
                                        )
                                    })
                                    .unwrap_or_else(|| "Enter valid values to render.".to_string())
                            }}
                        </p>
                    </footer>
                </section>

                <section class="card print-area mb-6">
                    <header class="no-print">
                        <h3>"Scale (exact size in print)"</h3>
                    </header>
                    <section>
                        {move || {
                            if stack_h_mm.get() > printable_mm.get().1 {
                                Some(
                                    view! {
                                        <p class="no-print mb-2 text-sm text-destructive">
                                            {format!(
                                                "Taller than one {} page — the last copies will spill onto another sheet. Reduce Scales per page or Label size.",
                                                paper.get().label(),
                                            )}
                                        </p>
                                    },
                                )
                            } else {
                                None
                            }
                        }}
                        {move || {
                            if svg_mm.get() > printable_mm.get().0 {
                                Some(
                                    view! {
                                        <p class="no-print mb-2 text-sm text-destructive">
                                            {format!(
                                                "Longer than one {} page — it will scroll / span pages. Reduce Max units, or re-check the calibration.",
                                                paper.get().label(),
                                            )}
                                        </p>
                                    },
                                )
                            } else {
                                None
                            }
                        }}
                        <div class="overflow-x-auto">
                            <div class="scale-stack">
                                {move || {
                                    let n = copies_eff.get();
                                    (0..n)
                                        .map(|i| {
                                            let mb = if i + 1 < n {
                                                format!("margin-bottom: {COPY_GAP_MM}mm")
                                            } else {
                                                String::new()
                                            };
                                            view! {
                                                <div style=mb>{scale_svg()}</div>
                                            }
                                        })
                                        .collect_view()
                                }}
                            </div>
                        </div>
                    </section>
                </section>

                <section class="card print-area mb-6">
                    <header class="no-print">
                        <h3>"Caliper dial (exact size in print)"</h3>
                        <p>
                            "Paper face for the dial caliper below: cut on the outer circle, and fit it where the printed dial used to go. Print at 100% scale."
                        </p>
                    </header>
                    <section>
                        {move || {
                            dial.get().map(|d| {
                                let step_txt = fmt_step(d.step);
                                let name = unit_name.get();
                                view! {
                                    <p class="no-print mb-2 text-sm text-muted-foreground">
                                        {format!(
                                            "{} {} per turn · {} divisions of {} {} ({:.3} mm apart)",
                                            d.units_per_rev,
                                            name,
                                            d.divisions,
                                            step_txt,
                                            name,
                                            d.mm_per_rev / d.divisions as f64,
                                        )}
                                    </p>
                                }
                            })
                        }}
                        {move || {
                            if dial_size_mm.get() > printable_mm.get().0
                                || dial_size_mm.get() > printable_mm.get().1
                            {
                                Some(
                                    view! {
                                        <p class="no-print mb-2 text-sm text-destructive">
                                            "Wider than the printable area — it will be clipped. Use a larger paper size."
                                        </p>
                                    },
                                )
                            } else {
                                None
                            }
                        }}
                        <div class="overflow-x-auto">{dial_view()}</div>
                    </section>
                </section>

                <ModelCard params=cad_params unit_name/>
            </div>
        </main>
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Phase {
    Idle,
    Booting,
    Building,
    Done,
    Failed,
}

/// File sizes as the build log shows them.
fn human_size(bytes: usize) -> String {
    if bytes >= 1_000_000 {
        format!("{:.1} MB", bytes as f64 / 1.0e6)
    } else {
        format!("{} kB", bytes / 1000)
    }
}

/// Everything the 3D generator needs: the calibration, where the scale ends,
/// and the label size the ruler engraves at.  The unit name is printed on the
/// paper dial above and passed through to the 3D build.
type CadParams = (usize, f64, usize, f64);

/// Generates the printable 3D models for the current scale, in the browser.
///
/// The models are the build123d ones in `cad/`; they run on Pyodide with the
/// OpenCascade bindings from OCP.wasm, in a worker, so the page stays
/// responsive and nothing is uploaded.
#[component]
fn ModelCard(params: Memo<Option<CadParams>>, unit_name: RwSignal<String>) -> impl IntoView {
    let (model, set_model) = signal(Model::DEFAULT);
    let (thick_raw, set_thick_raw) = signal("2".to_string());
    let (zero_margin, set_zero_margin) = signal(false);
    let thick_mm_res = Memo::new(move |_| {
        parse_mm(&thick_raw.get())
            .map_err(|e| e.to_string())
            .and_then(|v| {
                if (1.0..=10.0).contains(&v) {
                    Ok(v)
                } else {
                    Err("Between 1 and 10 mm".to_string())
                }
            })
    });
    // the parts grid starts with every part checked; each model only ever
    // builds its own (`Model::parts_to_build` drops the others)
    let selected = RwSignal::new(
        Model::ALL
            .iter()
            .flat_map(|m| m.all_parts())
            .collect::<Vec<_>>(),
    );
    let log = RwSignal::new(Vec::<String>::new());
    let summary = RwSignal::new(None::<String>);
    let warnings = RwSignal::new(Vec::<String>::new());
    let phase = RwSignal::new(Phase::Idle);

    let note = move |line: String| {
        log.update(|l| {
            if l.len() >= 300 {
                l.remove(0);
            }
            l.push(line);
        })
    };

    let run = move |_| {
        let Some((units, per_mm, max_units, font)) = params.get_untracked() else {
            return;
        };
        let m = model.get_untracked();
        let parts = m.parts_to_build(&selected.get_untracked());
        if parts.is_empty() {
            return;
        }
        // the ruler bar thickness comes from its own field
        let thick = match m {
            Model::Ruler => match thick_mm_res.get_untracked() {
                Ok(mm) => Some(mm),
                Err(_) => return,
            },
            Model::Caliper => None,
        };
        log.update(Vec::clear);
        warnings.update(Vec::clear);
        summary.set(None);
        phase.set(Phase::Booting);

        let mut env = vec![
            ("CALIPER_UNITS".to_string(), units.to_string()),
            ("CALIPER_PER_MM".to_string(), per_mm.to_string()),
            ("CALIPER_MAX_UNITS".to_string(), max_units.to_string()),
            ("CALIPER_UNIT_NAME".to_string(), unit_name.get_untracked()),
            ("CALIPER_FONT_MM".to_string(), font.to_string()),
        ];
        if let Some(mm) = thick {
            env.push(("CALIPER_THICK".to_string(), mm.to_string()));
            env.push((
                "CALIPER_ZERO_MARGIN".to_string(),
                zero_margin.get_untracked().to_string(),
            ));
        }

        let started = cad::start(move |msg| match msg {
            CadMsg::Ready => {
                phase.set(Phase::Building);
                if let Err(e) = cad::generate(m, &env, &parts) {
                    phase.set(Phase::Failed);
                    note(e);
                }
            }
            CadMsg::Log(text) => note(text),
            CadMsg::Summary { text, warnings: w } => {
                summary.set(Some(text));
                warnings.set(w);
            }
            CadMsg::File {
                filename,
                url,
                bytes,
            } => {
                note(format!(
                    "  {filename} — {}, download started",
                    human_size(bytes)
                ));
                if let Err(e) = cad::download(&filename, &url) {
                    note(format!("  the download did not start: {e}"));
                }
            }
            CadMsg::Done => phase.set(Phase::Done),
            CadMsg::Error(text) => {
                phase.set(Phase::Failed);
                note(text);
            }
        });
        if let Err(e) = started {
            phase.set(Phase::Failed);
            note(e);
        }
    };

    let busy = move || matches!(phase.get(), Phase::Booting | Phase::Building);

    view! {
        <section class="no-print card mb-6">
            <header>
                <h3>"3D printable models"</h3>
                <p>
                    "A ruler or a working rack-and-pinion dial caliper, graduated in the same units as the scale above. \
                     Generated here in your browser - build123d on "
                    <a class="underline" href="https://github.com/yeicor/OCP.wasm" target="_blank" rel="noreferrer">
                        "OCP.wasm"
                    </a>
                    " - so nothing is uploaded. The first run downloads about 40 MB of WebAssembly, \
                     which the browser then caches."
                </p>
            </header>
            <section>
                <div class="tabs mb-4">
                    <nav role="tablist" aria-orientation="horizontal">
                        {Model::ALL
                            .iter()
                            .copied()
                            .map(|m| {
                                view! {
                                    <button
                                        type="button"
                                        role="tab"
                                        id=format!("model-tab-{}", m.id())
                                        aria-controls=format!("model-panel-{}", m.id())
                                        aria-selected=move || (model.get() == m).to_string()
                                        on:click=move |_| set_model.set(m)
                                    >
                                        {m.label()}
                                    </button>
                                }
                            })
                            .collect_view()}
                    </nav>

                    {Model::ALL
                        .iter()
                        .copied()
                        .map(|m| {
                            view! {
                                <div
                                    role="tabpanel"
                                    id=format!("model-panel-{}", m.id())
                                    aria-labelledby=format!("model-tab-{}", m.id())
                                    tabindex="-1"
                                    hidden=move || model.get() != m
                                >
                                    <p class="mb-4 text-sm text-muted-foreground">{m.blurb()}</p>
                                    {(m == Model::Ruler)
                                        .then(|| {
                                            let bar = preview_bar_path();
                                            view! {
                                                <div class="grid gap-4 sm:grid-cols-3">
                                                    <div role="group" class="field">
                                                        <label for="ruler-thickness">"Thickness (mm)"</label>
                                                        <input
                                                            id="ruler-thickness"
                                                            class="input"
                                                            type="number"
                                                            min="1"
                                                            max="10"
                                                            step="0.5"
                                                            bind:value=(thick_raw, set_thick_raw)
                                                            aria-invalid=move || {
                                                                if thick_mm_res.get().is_err() { "true" } else { "false" }
                                                            }
                                                        />
                                                        {move || {
                                                            thick_mm_res
                                                                .get()
                                                                .err()
                                                                .map(|e| {
                                                                    view! { <p role="alert" class="text-sm text-destructive">{e}</p> }
                                                                })
                                                        }}
                                                    </div>
                                                    <div role="group" class="field">
                                                        <label for="zero-margin">"Margin at 0"</label>
                                                        <div class="flex items-center gap-2">
                                                            <input
                                                                id="zero-margin"
                                                                class="input"
                                                                type="checkbox"
                                                                role="switch"
                                                                bind:checked=(zero_margin, set_zero_margin)
                                                            />
                                                            <span class="text-sm text-muted-foreground">
                                                                {move || if zero_margin.get() { "On" } else { "Off" }}
                                                            </span>
                                                        </div>
                                                        <p class="text-sm text-muted-foreground">
                                                            "When off: the bar starts on the 0 tick's centre, so the left edge is the zero line."
                                                        </p>
                                                    </div>
                                                    <div role="group" class="field">
                                                        <span class="flex items-center">"Bar end"</span>
                                                        <svg
                                                            viewBox=preview_view_box()
                                                            class="w-full max-w-56"
                                                            role="img"
                                                            aria-label="Left end of the ruler bar, showing where the 0 tick lands"
                                                        >
                                                            <defs>
                                                                <clipPath id="ruler-bar-end">
                                                                    <path d=bar.clone()/>
                                                                </clipPath>
                                                            </defs>
                                                            <path
                                                                d=bar.clone()
                                                                fill="white"
                                                                stroke="black"
                                                                stroke-width=format!("{}", PREVIEW_STROKE)
                                                            />
                                                            <g clip-path="url(#ruler-bar-end)">
                                                                {move || {
                                                                    let x0 = if zero_margin.get() {
                                                                        PREVIEW_GAP
                                                                    } else {
                                                                        1
                                                                    };
                                                                    (0..=PREVIEW_INTERVALS)
                                                                        .map(|i| {
                                                                            let (len, width) = preview_tick(i);
                                                                            let x = x0 as usize + i * PREVIEW_SPACING as usize;
                                                                            view! {
                                                                                <line
                                                                                    x1=format!("{x}")
                                                                                    y1=format!("{}", PREVIEW_TOP)
                                                                                    x2=format!("{x}")
                                                                                    y2=format!("{}", PREVIEW_TOP + len)
                                                                                    stroke="black"
                                                                                    stroke-width=format!("{width}")
                                                                                />
                                                                            }
                                                                        })
                                                                        .collect_view()
                                                                }}
                                                            </g>
                                                        </svg>
                                                    </div>
                                                </div>
                                            }
                                        })}
                                    {(m.buildable().len() > 1)
                                        .then(|| {
                                            view! {
                                                <div class="mt-4 grid gap-4 sm:grid-cols-3">
                                                    {m
                                                        .buildable()
                                                        .iter()
                                                        .map(|(name, label)| {
                                                            let checked_for = name.to_string();
                                                            let toggled = name.to_string();
                                                            let slow = m.slow().contains(name);
                                                            view! {
                                                                <label class="flex items-center gap-2 text-sm">
                                                                    <input
                                                                        type="checkbox"
                                                                        prop:checked=move || selected.get().contains(&checked_for)
                                                                        on:change=move |ev| {
                                                                            let on = event_target_checked(&ev);
                                                                            selected
                                                                                .update(|s| {
                                                                                    if on {
                                                                                        if !s.contains(&toggled) {
                                                                                            s.push(toggled.clone());
                                                                                        }
                                                                                    } else {
                                                                                        s.retain(|x| x != &toggled);
                                                                                    }
                                                                                });
                                                                        }
                                                                    />
                                                                    <span>{*label}</span>
                                                                    {slow
                                                                        .then(|| {
                                                                            view! {
                                                                                <span class="text-xs text-muted-foreground">"(slow)"</span>
                                                                            }
                                                                        })}
                                                                </label>
                                                            }
                                                        })
                                                        .collect_view()}
                                                </div>
                                            }
                                        })}

                                    {(!m.prebuilt_parts().is_empty())
                                        .then(|| {
                                            view! {
                                                <div class="mt-4 border-t pt-3">
                                                    <p class="mb-2 text-sm text-muted-foreground">
                                                        "These come out the same whatever the scale, so they are ready now:"
                                                    </p>
                                                    <div class="flex flex-wrap gap-2">
                                                        {m
                                                            .prebuilt_parts()
                                                            .into_iter()
                                                            .map(|(name, label, url)| {
                                                                view! {
                                                                    <a
                                                                        class="btn-outline"
                                                                        href=url
                                                                        download=format!("{name}.stl")
                                                                        title=label
                                                                    >
                                                                        {format!("{name}.stl")}
                                                                    </a>
                                                                }
                                                            })
                                                            .collect_view()}
                                                    </div>
                                                </div>
                                            }
                                        })}
                                </div>
                            }
                        })
                        .collect_view()}
                </div>

                <div class="flex flex-wrap items-center gap-3">
                    <button
                        class="btn"
                        disabled=move || {
                            busy() || params.get().is_none()
                                || (model.get().buildable().len() > 1 && selected.get().is_empty())
                                || (model.get() == Model::Ruler && thick_mm_res.get().is_err())
                        }
                        on:click=run
                    >
                        {move || match phase.get() {
                            Phase::Booting => "Starting build123d…".to_string(),
                            Phase::Building => "Building…".to_string(),
                            _ => "Generate 3MF file".to_string(),
                        }}
                    </button>
                    <p class="text-sm text-muted-foreground">
                        {move || match model.get() {
                            Model::Ruler => "Runs on your machine - a few seconds.",
                            Model::Caliper => {
                                "Runs on your machine — a few seconds per part once build123d has loaded."
                            }
                        }}
                    </p>
                </div>

                {move || {
                    summary
                        .get()
                        .map(|text| {
                            view! {
                                <pre class="mt-4 overflow-x-auto rounded-md bg-muted p-3 text-xs">
                                    {text}
                                </pre>
                            }
                        })
                }}

                {move || {
                    let w = warnings.get();
                    (!w.is_empty())
                        .then(|| {
                            view! {
                                <ul class="mt-2 text-sm text-destructive">
                                    {w
                                        .into_iter()
                                        .map(|line| view! { <li>{line}</li> })
                                        .collect_view()}
                                </ul>
                            }
                        })
                }}

                {move || {
                    let lines = log.get();
                    (!lines.is_empty())
                        .then(|| {
                            view! {
                                <pre class="mt-4 max-h-56 overflow-auto rounded-md bg-muted p-3 text-xs">
                                    {lines.join("\n")}
                                </pre>
                            }
                        })
                }}
            </section>
        </section>
    }
}

#[cfg(all(test, feature = "ssr"))]
mod tests {
    use super::*;
    use crate::dial::{label_width_mm, BORE_R_MM, STEP_ICON_W_MM, X_HEIGHT_RATIO};

    #[test]
    fn dial_face_centres_the_step_icon_and_label_as_one_group() {
        let d = compute_dial(1.0).unwrap();
        let html = dial_face(&d, "mm").into_view().to_html();
        let label = format!("{} mm", fmt_step(d.step));
        let c = dial_sheet_r_mm();
        let row_y = c + UNIT_LABEL_Y_MM;
        let dx = step_label_dx_mm(&label, UNIT_SIZE_MM);
        let text_w = label_width_mm(&label, UNIT_SIZE_MM);

        // the label sits on an explicit baseline, its numerals centred on the row
        assert!(
            html.contains(&format!(
                "<text x=\"{:.4}\" y=\"{:.4}\"",
                c + dx.label,
                baseline_y(row_y, UNIT_SIZE_MM),
            )),
            "{html}"
        );
        assert!(html.contains(&format!(">{label}</text>")), "{html}");
        assert_eq!(
            html.matches("font-family=\"AlteDIN Bold, sans-serif\"")
                .count(),
            1,
            "only the step label is bold: {html}"
        );

        // the icon's bars are its full x-height, bottoming on the label baseline
        let icon_y = baseline_y(row_y, UNIT_SIZE_MM) - STEP_ICON_H_MM / 2.0;
        for s in [-1.0, 1.0] {
            assert!(
                html.contains(&format!(
                    "<line x1=\"{:.4}\" y1=\"{:.4}\" x2=\"{:.4}\" y2=\"{:.4}\"",
                    c + dx.icon + s * STEP_ICON_GAP_MM / 2.0,
                    icon_y - STEP_ICON_H_MM / 2.0,
                    c + dx.icon + s * STEP_ICON_GAP_MM / 2.0,
                    icon_y + STEP_ICON_H_MM / 2.0,
                )),
                "{html}"
            );
        }

        // icon + gap + label straddle the dial centre
        let left = c + dx.icon - STEP_ICON_W_MM / 2.0;
        let right = c + dx.label + text_w / 2.0;
        assert!(((left + right) / 2.0 - c).abs() < 1e-12);

        // two arrowheads on the step icon, plus the cut outline
        assert_eq!(html.matches("<path").count(), 3);

        // the cut outline is one thin path that carries the latches
        assert!(
            html.contains(&format!("<path d=\"{}\"", cut_outline_path(c))),
            "{html}"
        );
        assert!(
            html.contains(&format!("stroke-width=\"{CUT_STROKE_MM}\"")),
            "{html}"
        );
        assert!(!html.contains(&format!("r=\"{BORE_R_MM:.4}\"")), "{html}");

        // the centre crosshair is cut at the same width as the outer line
        assert!(
            html.contains(&format!(
                "<line x1=\"{:.4}\" y1=\"{c:.4}\" x2=\"{:.4}\" y2=\"{c:.4}\" \
                 stroke=\"black\" stroke-width=\"{CUT_STROKE_MM}\"",
                c - CROSSHAIR_HALF_MM,
                c + CROSSHAIR_HALF_MM,
            )),
            "{html}"
        );
        assert!(
            html.contains(&format!(
                "<line x1=\"{c:.4}\" y1=\"{:.4}\" x2=\"{c:.4}\" y2=\"{:.4}\" \
                 stroke=\"black\" stroke-width=\"{CUT_STROKE_MM}\"",
                c - CROSSHAIR_HALF_MM,
                c + CROSSHAIR_HALF_MM,
            )),
            "{html}"
        );
    }

    #[test]
    fn footer_row_sits_below_the_rotated_labels() {
        let font = 3.0;
        for digits in 1..=6 {
            let labels_bottom = labels_bottom_mm(digits, font);
            let footer = footer_baseline_mm(digits, font);
            assert!(footer > labels_bottom + FOOTER_GAP_MM);
            assert!(
                (footer - labels_bottom - FOOTER_GAP_MM - font * CAP_HEIGHT_RATIO).abs() < 1e-9
            );
            assert!(scale_svg_height_mm(digits, font) > footer);
        }
    }

    #[test]
    fn footer_step_icon_sits_left_of_the_label_on_the_baseline() {
        let font = 3.0;
        let size = footer_step_size_mm(font);
        let footer_y = footer_baseline_mm(4, font);
        let layout = footer_step_layout(size, footer_y);
        let icon_w = STEP_ICON_W_MM * layout.icon_scale;
        let gap = STEP_ICON_LABEL_GAP_MM * layout.icon_scale;

        assert!(
            size < font,
            "the footer step group is smaller than the name"
        );
        // group starts at the footer margin, icon first, then the label
        assert!((layout.icon_x - icon_w / 2.0 - FOOTER_STEP_MARGIN_MM).abs() < 1e-12);
        assert!((layout.label_x - (layout.icon_x + icon_w / 2.0) - gap).abs() < 1e-12);

        // the icon is the label's x-height and bottoms on the text baseline
        assert!((STEP_ICON_H_MM * layout.icon_scale - size * X_HEIGHT_RATIO).abs() < 1e-12);
        assert!(
            (layout.icon_y + STEP_ICON_H_MM * layout.icon_scale / 2.0 - footer_y).abs() < 1e-12
        );
    }

    #[test]
    fn ruler_svg_has_footer_step_label_and_name_input() {
        let html = Owner::new().with(|| AppContent().into_view().to_html());
        assert!(
            html.contains("aria-label=\"Printable measuring scale\""),
            "{html}"
        );
        // The defaults: 150 u measured at 10 mm, a 1000-u scale, minor every 20 u.
        let density = density_units_per_mm(150, 10.0).unwrap();
        let (steps, _) = compute_ticks(1000, density).unwrap();
        assert!(
            html.contains(&format!(">{} u</text>", steps.minor_units)),
            "{html}"
        );
        assert!(html.contains("id=\"ruler-name\""), "{html}");
    }
}
