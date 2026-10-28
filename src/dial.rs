//! Paper dial-face derivation: the dial of the 3D caliper, as numbers.
//!
//! The calibration gives units-per-mm (see [`crate::scale`]); one needle
//! turn is then a round number of units near 20 mm of travel, and the face
//! is divided into the finest nice unit step that keeps the ticks printable.
//! This mirrors `cad/caliper.py` (transmission block).

use std::f64::consts::PI;

/// How much travel one needle turn should be, in mm.
pub const TARGET_MM_PER_REV: f64 = 20.0;
/// Never more divisions than this, so ticks stay >= ~1.2 mm apart.
pub const MAX_DIAL_DIVISIONS: usize = 100;

/// Outer cut line of the paper disc: light and thin, so it reads as a cut
/// guide without shouting over the dial.
pub const DIAL_R_MM: f64 = 24.9;
/// Stroke width of the cut lines.
pub const CUT_STROKE_MM: f64 = 0.15;
/// Dash pattern of the latch fold lines.
pub const FOLD_DASH_MM: &str = "0.8 0.6";
/// Half-length of each of the centre crosshair's two cut lines.
pub const CROSSHAIR_HALF_MM: f64 = 3.7;
/// Outer end of every tick.
pub const TICK_OUTER_MM: f64 = 22.0;
/// Radial tick lengths: labelled majors, the unlabelled majors halfway
/// between them, and the minors.
pub const TICK_LABEL_MM: f64 = 3.4;
pub const TICK_MAJOR_MM: f64 = 2.7;
pub const TICK_MINOR_MM: f64 = 1.3;
/// Numeral ring radius.
pub const NUM_R_MM: f64 = 16.0;
/// Numeral cap height.
pub const NUM_SIZE_MM: f64 = 3.0;
/// "step unit" label under the centre.
pub const UNIT_SIZE_MM: f64 = 2.2;
/// AlteDIN x-height (OS/2 sxHeight / unitsPerEm); the icon is sized to this.
pub const X_HEIGHT_RATIO: f64 = 0.5063;
/// Step icon ("two ticks apart") drawn left of the label: clear space
/// between the bars, arrowhead length, the line beyond each arrowhead, and
/// the bar height, which matches the full arrowhead height.
///
/// The whole icon is uniformly scaled so that height is the label's x-height
/// at UNIT_SIZE_MM; it is positioned so its bottom sits on the text baseline.
const STEP_ICON_BASE_H_MM: f64 = 2.0 * 1.4 * 0.32; // 0.896 mm
const STEP_ICON_SCALE: f64 = UNIT_SIZE_MM * X_HEIGHT_RATIO / STEP_ICON_BASE_H_MM;
pub const STEP_ICON_GAP_MM: f64 = 1.0 * STEP_ICON_SCALE;
pub const STEP_ICON_ARROW_MM: f64 = 1.4 * STEP_ICON_SCALE;
pub const STEP_ICON_TAIL_MM: f64 = 0.7 * STEP_ICON_SCALE;
/// Stroke width of the icon's bars.
pub const STEP_ICON_STROKE_MM: f64 = 0.15 * STEP_ICON_SCALE;
/// Stroke width of the icon's arrow tails.
pub const STEP_ICON_ARROW_STROKE_MM: f64 = 0.2 * STEP_ICON_SCALE;
/// Arrowhead half-height as a fraction of its length.
pub const STEP_ICON_HEAD: f64 = 0.32;
/// Full icon height: the font's x-height at UNIT_SIZE_MM.
pub const STEP_ICON_H_MM: f64 = STEP_ICON_BASE_H_MM * STEP_ICON_SCALE;
/// Clear gap between the icon and the label text.
pub const STEP_ICON_LABEL_GAP_MM: f64 = 0.5;
/// Total width of the icon.
pub const STEP_ICON_W_MM: f64 = STEP_ICON_GAP_MM + 2.0 * (STEP_ICON_ARROW_MM + STEP_ICON_TAIL_MM);
/// Bore the paper slips over: manual boss + pinion play + clearance.
pub const BORE_R_MM: f64 = 3.5 + 0.35 + 0.20;
/// Latches round the rim (6 at 60 deg) that lock the disc into the bezel:
/// width, total length, and how deep each bites inside the cut line.  The
/// rest of the length stands proud of the rim.
pub const LATCH_W_MM: f64 = 10.0;
pub const LATCH_LEN_MM: f64 = 3.0;
pub const LATCH_IN_MM: f64 = 1.4;
pub const LATCH_OUT_MM: f64 = LATCH_LEN_MM - LATCH_IN_MM;
pub const LATCH_COUNT: usize = 6;
pub const LATCH_STEP_DEG: f64 = 60.0;
/// Radii of a latch's inner (cut into the disc) and outer (standing proud)
/// edges, measured along the latch axis from the disc centre.
pub const LATCH_INNER_R_MM: f64 = DIAL_R_MM - LATCH_IN_MM;
pub const LATCH_OUTER_R_MM: f64 = DIAL_R_MM + LATCH_OUT_MM;
/// How far round the rim a latch spans, half-angle at the cut circle.
pub fn latch_half_angle_deg() -> f64 {
    (LATCH_W_MM / 2.0 / DIAL_R_MM).asin().to_degrees()
}
/// Radial distance at which a latch's straight sides cross the cut circle.
pub fn latch_side_r_mm() -> f64 {
    (DIAL_R_MM * DIAL_R_MM - (LATCH_W_MM / 2.0).powi(2)).sqrt()
}
/// Centre height of the step icon and unit label row, below the centre.
pub const UNIT_LABEL_Y_MM: f64 = 8.5;

/// Where round the rim (degrees, 0 = 12 o'clock, clockwise) each latch sits.
pub fn latch_angles_deg() -> impl Iterator<Item = f64> {
    (0..LATCH_COUNT).map(|k| k as f64 * LATCH_STEP_DEG)
}

/// Polar (radius, degrees clockwise from 12 o'clock) to SVG x/y, y down.
fn polar(r: f64, deg: f64, c: f64) -> (f64, f64) {
    let a = deg.to_radians();
    (c + r * a.sin(), c - r * a.cos())
}

/// A point `r` mm out along a latch's axis, `off` mm to one side of it.
fn latch_at(centre_deg: f64, r: f64, off: f64, c: f64) -> (f64, f64) {
    let a = centre_deg.to_radians();
    // outward radial unit vector, and its perpendicular (SVG y is down)
    let u = (a.sin(), -a.cos());
    let p = (a.cos(), a.sin());
    (c + r * u.0 + off * p.0, c + r * u.1 + off * p.1)
}

/// One continuous cut outline: the rim arc between each latch, and round each
/// latch a slit 1.4 mm into the disc, the tab's two parallel sides 10 mm
/// apart, and its outer end.  The tab stays attached along the inner edge, so
/// it can fold out.  Returns SVG path data.
pub fn cut_outline_path(c: f64) -> String {
    let half = LATCH_W_MM / 2.0;
    // radial distance to where a tab's side crosses the cut circle
    let side_r = latch_side_r_mm();
    let mut d = String::new();
    for (k, centre) in latch_angles_deg().enumerate() {
        let at = |r: f64, off: f64| {
            let (x, y) = latch_at(centre, r, off, c);
            format!("{x:.4} {y:.4}")
        };
        let (lead, trail) = (at(side_r, -half), at(side_r, half));
        if k == 0 {
            d.push_str(&format!("M {lead}"));
        }
        // slit in, out along the tab, across its end, and back to the rim
        d.push_str(&format!(
            " L {inner_lead} L {outer_lead} L {outer_trail} L {inner_trail} L {trail}",
            inner_lead = at(LATCH_INNER_R_MM, -half),
            outer_lead = at(LATCH_OUTER_R_MM, -half),
            outer_trail = at(LATCH_OUTER_R_MM, half),
            inner_trail = at(LATCH_INNER_R_MM, half),
        ));
        // rim arc round to the next latch's leading edge
        let (nx, ny) = polar(
            DIAL_R_MM,
            centre + LATCH_STEP_DEG - latch_half_angle_deg(),
            c,
        );
        d.push_str(&format!(
            " A {r:.4} {r:.4} 0 0 1 {nx:.4} {ny:.4}",
            r = DIAL_R_MM
        ));
    }
    d.push_str(" Z");
    d
}

/// The fold line of each latch: a straight dashed line across the tab at its
/// inner end, where it bends up out of the disc.  One `<line>` per tab.
pub fn latch_fold_lines(c: f64) -> Vec<(f64, f64, f64, f64)> {
    let half = LATCH_W_MM / 2.0;
    latch_angles_deg()
        .map(|centre| {
            let (x1, y1) = latch_at(centre, LATCH_INNER_R_MM, -half, c);
            let (x2, y2) = latch_at(centre, LATCH_INNER_R_MM, half, c);
            (x1, y1, x2, y2)
        })
        .collect()
}

/// The dial: units per turn, division step and count, label stride.
#[derive(Clone, Copy, PartialEq, Debug)]
pub struct Dial {
    pub units_per_rev: usize,
    pub mm_per_rev: f64,
    pub step: f64,
    pub divisions: usize,
    pub label_every: usize,
}

/// Smallest nice 1/2/5 x 10^n unit step that is >= `x`, allowing fractions.
fn nice_ceil_frac(x: f64) -> f64 {
    if !x.is_finite() || x <= 0.0 {
        return 1.0;
    }
    let pow = 10f64.powi(x.log10().floor() as i32);
    let m = x / pow;
    let base = if m <= 1.0 {
        1.0
    } else if m <= 2.0 {
        2.0
    } else if m <= 5.0 {
        5.0
    } else {
        10.0
    };
    // Same rounding as Python's "%.10g".
    format!("{:.10}", base * pow)
        .trim_end_matches('0')
        .trim_end_matches('.')
        .parse()
        .unwrap_or(base * pow)
}

/// Nearest nice 1/2/5 x 10^n value (on a log scale).
fn nice_round(x: f64) -> usize {
    if !x.is_finite() || x <= 0.0 {
        return 1;
    }
    let pow = 10f64.powi(x.log10().floor() as i32);
    let m = x / pow;
    let base = [1.0, 2.0, 5.0, 10.0]
        .into_iter()
        .min_by(|a, b| {
            (m / a)
                .log10()
                .abs()
                .partial_cmp(&(m / b).log10().abs())
                .unwrap()
        })
        .unwrap();
    (base * pow).round() as usize
}

/// Derive the dial from the calibration. Returns `None` on bad input.
pub fn compute_dial(units_per_mm: f64) -> Option<Dial> {
    if !units_per_mm.is_finite() || units_per_mm <= 0.0 {
        return None;
    }
    let units_per_rev = nice_round(TARGET_MM_PER_REV * units_per_mm).max(1);
    let mm_per_rev = units_per_rev as f64 / units_per_mm;
    let step = nice_ceil_frac(units_per_rev as f64 / MAX_DIAL_DIVISIONS as f64);
    let divisions = (units_per_rev as f64 / step).round() as usize;
    if divisions == 0 {
        return None;
    }
    let label_every = if divisions >= 40 {
        10
    } else if divisions >= 15 {
        5
    } else {
        1
    };
    Some(Dial {
        units_per_rev,
        mm_per_rev,
        step,
        divisions,
        label_every,
    })
}

/// Radial tick length: labelled majors, unlabelled majors at half the label
/// stride, minors elsewhere.
pub fn tick_length(i: usize, label_every: usize) -> f64 {
    if i % label_every.max(1) == 0 {
        TICK_LABEL_MM
    } else if i % (label_every / 2).max(1) == 0 {
        TICK_MAJOR_MM
    } else {
        TICK_MINOR_MM
    }
}

/// Angle of division `i` in degrees, 0 at the top, clockwise.
pub fn tick_angle_deg(i: usize, divisions: usize) -> f64 {
    90.0 - 360.0 * i as f64 / divisions as f64
}

/// Circumferential pitch of adjacent divisions on the tick ring, in mm.
pub fn pitch_mm(dial: &Dial) -> f64 {
    2.0 * PI * TICK_OUTER_MM / dial.divisions as f64
}

/// Pretty unit step without a trailing ".0": 0.2, 2, 200.
pub fn fmt_step(step: f64) -> String {
    // Rust has no %g; strip the Debug float the same way.
    let mut s = format!("{step:?}");
    if s.contains('.') {
        s = s.trim_end_matches('0').trim_end_matches('.').to_string();
    }
    if s.is_empty() || s == "-0" {
        s = "0".to_string();
    }
    s
}

/// Cap height of the sans-serif face as a fraction of the font size.  Text
/// baselines are placed with this rather than `dominant-baseline`, whose
/// result depends on the font's ascent/descent, so the step icon can be
/// centred on the numerals themselves.
pub const CAP_HEIGHT_RATIO: f64 = 0.72;

/// Baseline y where a line of `size` mm text is centred on cap height at `y`.
pub fn baseline_y(y: f64, size: f64) -> f64 {
    y + size * CAP_HEIGHT_RATIO / 2.0
}

/// Rough sans-serif advance width of a label, in mm (0.62 em per glyph,
/// 0.35 for a space).  Only used to place the step icon, so close enough.
pub fn label_width_mm(text: &str, size: f64) -> f64 {
    let em: f64 = text
        .chars()
        .map(|ch| if ch == ' ' { 0.35 } else { 0.62 })
        .sum();
    em * size
}

/// The step icon and its unit label laid out as one horizontally centred
/// group: each centre's x, in mm, relative to the dial centre.
#[derive(Clone, Copy, PartialEq, Debug)]
pub struct StepLabelDx {
    pub icon: f64,
    pub label: f64,
}

/// Centre x of the step icon and of the unit label, relative to the dial
/// centre, when the two are centred together as one group (icon left).
pub fn step_label_dx_mm(label: &str, size: f64) -> StepLabelDx {
    let text = label_width_mm(label, size);
    StepLabelDx {
        icon: -(text + STEP_ICON_LABEL_GAP_MM) / 2.0,
        label: (STEP_ICON_W_MM + STEP_ICON_LABEL_GAP_MM) / 2.0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn millimetre_caliper_matches_the_readme() {
        // UNITS=1 PER_MM=1: 20 mm/turn, 100 x 0.2 mm.
        let d = compute_dial(1.0).unwrap();
        assert_eq!(d.units_per_rev, 20);
        assert_eq!(d.divisions, 100);
        assert!((d.step - 0.2).abs() < 1e-9);
        assert_eq!(d.label_every, 10);
        assert!((d.mm_per_rev - 20.0).abs() < 1e-9);
    }

    #[test]
    fn dense_units_match_the_readme() {
        // UNITS=150 PER_MM=10: 200 u/turn, 100 x 2 u.
        let d = compute_dial(15.0).unwrap();
        assert_eq!(d.units_per_rev, 200);
        assert_eq!(d.divisions, 100);
        assert!((d.step - 2.0).abs() < 1e-9);
        assert_eq!(d.label_every, 10);
    }

    #[test]
    fn rejects_bad_input() {
        assert!(compute_dial(0.0).is_none());
        assert!(compute_dial(-1.0).is_none());
        assert!(compute_dial(f64::NAN).is_none());
        assert!(compute_dial(f64::INFINITY).is_none());
    }

    #[test]
    fn tick_hierarchy_is_labelled_major_minor() {
        // 100 divisions, labels every 10: labelled / major / minor.
        assert!((tick_length(0, 10) - TICK_LABEL_MM).abs() < 1e-12);
        assert!((tick_length(5, 10) - TICK_MAJOR_MM).abs() < 1e-12);
        assert!((tick_length(3, 10) - TICK_MINOR_MM).abs() < 1e-12);
        assert!((tick_length(10, 10) - TICK_LABEL_MM).abs() < 1e-12);
        // the three levels stay distinct, longest labelled
        let levels = [tick_length(0, 10), tick_length(5, 10), tick_length(3, 10)];
        assert!(levels[0] > levels[1] && levels[1] > levels[2]);
    }

    #[test]
    fn artwork_fits_inside_the_disc() {
        assert!(TICK_OUTER_MM < DIAL_R_MM);
        assert!(NUM_R_MM + NUM_SIZE_MM / 2.0 < TICK_OUTER_MM - TICK_LABEL_MM);
        assert!(BORE_R_MM < NUM_R_MM - NUM_SIZE_MM);
    }

    #[test]
    fn latches_bite_inside_and_stand_proud_of_the_rim() {
        assert!((LATCH_INNER_R_MM - (DIAL_R_MM - LATCH_IN_MM)).abs() < 1e-12);
        assert!((LATCH_OUTER_R_MM - (DIAL_R_MM + LATCH_OUT_MM)).abs() < 1e-12);
        // the total length is 3 mm, 1.4 of it inside the cut line
        assert!((LATCH_OUTER_R_MM - LATCH_INNER_R_MM - LATCH_LEN_MM).abs() < 1e-12);
        assert!((LATCH_LEN_MM - 3.0).abs() < 1e-12);
        assert!((LATCH_OUT_MM - 1.6).abs() < 1e-12);
        assert!(LATCH_INNER_R_MM < LATCH_OUTER_R_MM);
        // the latches clear the tick ring, and are narrower than the rim
        // arc between two of them
        assert!(LATCH_INNER_R_MM > TICK_OUTER_MM);
        assert!(2.0 * latch_half_angle_deg() < LATCH_STEP_DEG);
    }

    #[test]
    fn cut_outline_carries_six_latches() {
        let d = cut_outline_path(10.0);
        assert_eq!(d.matches('M').count(), 1, "one closed outline: {d}");
        assert_eq!(d.matches('A').count(), LATCH_COUNT, "one arc per gap: {d}");
        assert!(d.trim_end().ends_with('Z'));
        // each latch contributes a slit in, out, across and back to the rim
        let moves = d.matches(" L ").count();
        assert_eq!(moves, LATCH_COUNT * 5, "slit + tab sides: {d}");
    }

    #[test]
    fn fold_lines_span_each_latch_at_its_inner_end() {
        let c = 30.0;
        let lines = latch_fold_lines(c);
        assert_eq!(lines.len(), LATCH_COUNT);
        for (k, (x1, y1, x2, y2)) in lines.iter().enumerate() {
            // one 10 mm line per latch, centred on the latch axis
            let len = ((x2 - x1).powi(2) + (y2 - y1).powi(2)).sqrt();
            assert!((len - LATCH_W_MM).abs() < 1e-9, "latch {k}: {len} mm");
            let (mx, my) = ((x1 + x2) / 2.0, (y1 + y2) / 2.0);
            let r = ((mx - c).powi(2) + (my - c).powi(2)).sqrt();
            assert!((r - LATCH_INNER_R_MM).abs() < 1e-9, "latch {k} at r={r}");
            // and it lies along the latch's tangent, not radially
            let ang = (k as f64 * LATCH_STEP_DEG).to_radians();
            let along_radius = ((x2 - x1) * ang.sin() - (y2 - y1) * ang.cos()).abs() / len;
            assert!(along_radius < 1e-9, "latch {k} is not tangential");
        }
    }

    #[test]
    fn nice_helpers_match_scale_py() {
        assert_eq!(nice_round(20.0), 20);
        assert_eq!(nice_round(200.0), 200);
        assert!((nice_ceil_frac(0.2) - 0.2).abs() < 1e-9);
        assert!((nice_ceil_frac(2.0) - 2.0).abs() < 1e-9);
        assert!((nice_ceil_frac(0.11) - 0.2).abs() < 1e-9);
    }

    #[test]
    fn default_dial_stays_printable() {
        let d = compute_dial(1.0).unwrap();
        assert!(pitch_mm(&d) >= 1.0, "ticks crowd below 1 mm");
    }

    #[test]
    fn step_icon_and_label_are_centred_as_one_group() {
        let label = format!("{} mm", fmt_step(compute_dial(1.0).unwrap().step));
        let dx = step_label_dx_mm(&label, UNIT_SIZE_MM);
        let width = label_width_mm(&label, UNIT_SIZE_MM);

        // icon left of the text, exactly one label gap between them
        let icon_right = dx.icon + STEP_ICON_W_MM / 2.0;
        let text_left = dx.label - width / 2.0;
        assert!((text_left - icon_right - STEP_ICON_LABEL_GAP_MM).abs() < 1e-12);
        // the group's bounding box straddles the dial centre
        let left = dx.icon - STEP_ICON_W_MM / 2.0;
        let right = dx.label + width / 2.0;
        assert!((left + right).abs() < 1e-12);

        // and its outermost corner stays inside the cut line
        let far = left.abs();
        assert!((far * far + UNIT_LABEL_Y_MM * UNIT_LABEL_Y_MM).sqrt() < DIAL_R_MM);
    }

    #[test]
    fn label_baseline_centres_cap_height_on_the_row() {
        let centre = 32.5;
        let baseline = baseline_y(centre, UNIT_SIZE_MM);
        let cap = UNIT_SIZE_MM * CAP_HEIGHT_RATIO;
        // the cap box (top .. baseline) straddles the row centre
        let (top, bottom) = (baseline - cap, baseline);
        assert!(((top + bottom) / 2.0 - centre).abs() < 1e-12);
        assert!(baseline > centre, "baseline sits below the cap box centre");
    }

    #[test]
    fn label_width_tracks_glyph_count() {
        assert!(label_width_mm("0.2 mm", UNIT_SIZE_MM) > label_width_mm("2 mm", UNIT_SIZE_MM));
        assert!(label_width_mm("0.2 mm", UNIT_SIZE_MM) > 0.0);
    }
}
