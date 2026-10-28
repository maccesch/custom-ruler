//! Pure scale-generation logic: adaptive 1/2/5 ticks + 3 levels.
//! `units_per_mm` = how many logical units fit into one physical millimetre.
//! Total physical length = units_eff / units_per_mm mm.
//! Minor ticks land every ~1.5mm by snapping to a nice 1/2/5 × 10^n step.

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum TickKind {
    Minor,
    Medium,
    Major,
}

#[derive(Clone, PartialEq, Debug)]
pub struct Tick {
    pub value: usize,
    pub x_mm: f64,
    pub kind: TickKind,
    pub show_label: bool,
}

#[derive(Clone, Copy, PartialEq, Debug)]
pub struct ScaleSteps {
    pub minor_units: usize,
    pub medium_units: usize,
    pub major_units: usize,
    pub total_mm: f64,
    pub minor_mm: f64,
    pub medium_mm: f64,
}

pub const MAX_UNITS_HARD_CAP: usize = 100_000;

/// Upper bound on emitted ticks. 100_000 units at 1 unit/mm would otherwise
/// produce 100_000 SVG nodes and lock the tab.
pub const MAX_TICKS: usize = 5_000;

/// Smallest nice 1/2/5 × 10^n value that is >= `x`.
fn nice_ceil(x: f64) -> usize {
    if !x.is_finite() || x <= 1.0 {
        return 1;
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
    (base * pow).round() as usize
}

/// Choose a minor step so that consecutive minor ticks are ~1.5mm apart,
/// then cap it so that `major_units = step × 10` never exceeds `units_eff`,
/// guaranteeing a labelled major tick is always visible.
///
/// Below 10 units there is no room for a ×10 hierarchy at all; the cap
/// bottoms out at 1 and only the levels that fit get drawn.
///
/// Returns at least 1 (can't subdivide a single logical unit).
pub fn nice_minor_step(units_per_mm: f64, units_eff: usize) -> usize {
    if !units_per_mm.is_finite() || units_per_mm <= 0.0 {
        return 1;
    }
    // target physical spacing = 1.5mm -> target step in units = 1.5 × units_per_mm
    let raw = 1.5 * units_per_mm;
    let base_step = if raw <= 1.0 {
        1
    } else {
        let pow = 10f64.powi(raw.log10().floor() as i32);
        let m = raw / pow;
        let base = if m < 1.75 {
            1.0
        } else if m < 3.5 {
            2.0
        } else if m < 7.5 {
            5.0
        } else {
            10.0
        };
        (base * pow).round() as usize
    };
    let cap = (units_eff / 10).max(1);
    base_step.min(cap).max(1)
}

/// Compute tick steps + tick list for the scale.
///
/// Ticks land only on exact multiples of `minor_units`, so the last tick may
/// sit short of `units_eff`. `total_mm` still describes the full length, and
/// callers should draw the baseline to it — a stub of bare line past the last
/// tick is honest, a tick crammed against its neighbour is not.
pub fn compute_ticks(units_eff: usize, units_per_mm: f64) -> Option<(ScaleSteps, Vec<Tick>)> {
    if units_eff == 0 || !units_per_mm.is_finite() || units_per_mm <= 0.0 {
        return None;
    }
    let mut minor_units = nice_minor_step(units_per_mm, units_eff);
    // Coarsen the step if a ~1.5mm pitch would emit an unrenderable tick count,
    // snapping up to the next nice value so the 1/5/10 hierarchy still holds.
    let min_step_for_count = units_eff.div_ceil(MAX_TICKS);
    if min_step_for_count > minor_units {
        minor_units = nice_ceil(min_step_for_count as f64);
    }
    let medium_units = minor_units.saturating_mul(5);
    let major_units = minor_units.saturating_mul(10);

    let steps = ScaleSteps {
        minor_units,
        medium_units,
        major_units,
        total_mm: units_eff as f64 / units_per_mm,
        minor_mm: minor_units as f64 / units_per_mm,
        medium_mm: medium_units as f64 / units_per_mm,
    };

    let mut ticks = Vec::new();
    let mut u = 0usize;
    while u <= units_eff {
        let kind = if u.is_multiple_of(major_units) {
            TickKind::Major
        } else if u.is_multiple_of(medium_units) {
            TickKind::Medium
        } else {
            TickKind::Minor
        };
        ticks.push(Tick {
            value: u,
            x_mm: u as f64 / units_per_mm,
            kind,
            // 0 keeps its major tick but goes unlabelled - the origin is
            // obvious from the tick itself.
            show_label: matches!(kind, TickKind::Major) && u > 0,
        });
        match u.checked_add(minor_units) {
            Some(next) => u = next,
            None => break,
        }
    }

    Some((steps, ticks))
}

pub fn parse_units(s: &str) -> Result<usize, &'static str> {
    let v: usize = s
        .trim()
        .parse()
        .map_err(|_| "Enter a positive whole number")?;
    if v == 0 {
        return Err("Must be at least 1");
    }
    if v > MAX_UNITS_HARD_CAP {
        return Err("Too large (max 100000)");
    }
    Ok(v)
}

/// Calibration: `sample_units` counted units were measured at `sample_mm`
/// millimetres, giving the units-per-mm density the scale is drawn at.
pub fn density_units_per_mm(sample_units: usize, sample_mm: f64) -> Option<f64> {
    if sample_units == 0 || !sample_mm.is_finite() || sample_mm <= 0.0 {
        return None;
    }
    let d = sample_units as f64 / sample_mm;
    (d.is_finite() && d > 0.0).then_some(d)
}

pub const MAX_COPIES: usize = 50;

/// How many identical scales get stacked down the page.
pub fn parse_copies(s: &str) -> Result<usize, &'static str> {
    let v: usize = s
        .trim()
        .parse()
        .map_err(|_| "Enter a positive whole number")?;
    if v == 0 {
        return Err("Must be at least 1");
    }
    if v > MAX_COPIES {
        return Err("Too many (max 50)");
    }
    Ok(v)
}

pub const MIN_FONT_MM: f64 = 0.5;
pub const MAX_FONT_MM: f64 = 20.0;

/// Label font size, in millimetres (SVG user units are mm here).
pub fn parse_font_mm(s: &str) -> Result<f64, &'static str> {
    let v: f64 = s.trim().parse().map_err(|_| "Enter a number")?;
    if !v.is_finite() || v < MIN_FONT_MM {
        return Err("Must be at least 0.5 mm");
    }
    if v > MAX_FONT_MM {
        return Err("Too large (max 20 mm)");
    }
    Ok(v)
}

pub fn parse_mm(s: &str) -> Result<f64, &'static str> {
    let v: f64 = s.trim().parse().map_err(|_| "Enter a number")?;
    if !v.is_finite() || v <= 0.0 {
        return Err("Must be a positive number");
    }
    if v > 1_000.0 {
        return Err("Too large (max 1000)");
    }
    Ok(v)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn example_150u_at_1_unit_per_mm() {
        // 150 units ÷ 1 unit/mm = 150mm
        let (steps, _) = compute_ticks(150, 1.0).unwrap();
        assert!((steps.total_mm - 150.0).abs() < 1e-9);
        // raw = 1.5×1 = 1.5 -> series {1,2,5}, m=1.5 <1.75 -> 1 unit = 1mm
        assert_eq!(steps.minor_units, 1);
        assert_eq!(steps.medium_units, 5);
        assert_eq!(steps.major_units, 10);
        assert!((steps.minor_mm - 1.0).abs() < 1e-9);
    }

    #[test]
    fn example_150u_at_10_units_per_mm() {
        // The shipped defaults: thin sheets, 10 to the millimetre -> 15mm total.
        let (steps, _) = compute_ticks(150, 10.0).unwrap();
        assert!((steps.total_mm - 15.0).abs() < 1e-9);
        // raw = 1.5×10 = 15 -> m=1.5 <1.75 -> 10 units = 1mm
        assert_eq!(steps.minor_units, 10);
        assert_eq!(steps.medium_units, 50);
        assert_eq!(steps.major_units, 100);
        assert!((steps.minor_mm - 1.0).abs() < 1e-9);
    }

    #[test]
    fn example_100u_at_2_units_per_mm() {
        // 100 units ÷ 2 units/mm = 50mm
        let (steps, _) = compute_ticks(100, 2.0).unwrap();
        assert!((steps.total_mm - 50.0).abs() < 1e-9);
        // raw = 1.5×2 = 3 -> m=3 <3.5 -> 2 units = 1mm
        assert_eq!(steps.minor_units, 2);
        assert_eq!(steps.medium_units, 10);
        assert_eq!(steps.major_units, 20);
        assert!((steps.minor_mm - 1.0).abs() < 1e-9);
    }

    #[test]
    fn minor_spacing_stays_near_1_5mm() {
        for density in [0.5, 1.0, 2.0, 10.0, 33.0, 250.0] {
            let step = nice_minor_step(density, 50_000) as f64;
            let mm = step / density;
            assert!(
                mm <= 2.0,
                "{density} units/mm: step {step} -> {mm}mm exceeds 2mm"
            );
        }
        // Sparse scales: one unit already spans more than 2mm, so 1 is the best fit.
        assert_eq!(nice_minor_step(0.2, 50_000), 1);
        assert_eq!(nice_minor_step(0.1, 50_000), 1);
    }

    #[test]
    fn no_crammed_tick_at_the_end() {
        // 155 ÷ 2 units/mm: minor step is 2 units, so ticks stop at 154.
        let (steps, ticks) = compute_ticks(155, 2.0).unwrap();
        assert_eq!(steps.minor_units, 2);
        assert_eq!(ticks.last().unwrap().value, 154);
        // Every tick sits on an exact minor multiple.
        assert!(ticks
            .iter()
            .all(|t| t.value.is_multiple_of(steps.minor_units)));
        // ...but the scale still describes its full physical length.
        assert!((steps.total_mm - 77.5).abs() < 1e-9);
    }

    #[test]
    fn major_hierarchy_fits_whenever_there_is_room() {
        for units in [10usize, 37, 150, 999, 12_345] {
            for density in [0.5, 1.0, 10.0, 100.0] {
                let (steps, ticks) = compute_ticks(units, density).unwrap();
                assert!(
                    steps.major_units <= units,
                    "{units}u @ {density}/mm: major {} exceeds length",
                    steps.major_units
                );
                assert!(
                    ticks
                        .iter()
                        .any(|t| t.value > 0 && t.kind == TickKind::Major),
                    "{units}u @ {density}/mm: no labelled major tick"
                );
            }
        }
    }

    #[test]
    fn hierarchy_preserved_on_short_scales() {
        let (steps, ticks) = compute_ticks(150, 1.0).unwrap();
        assert!(steps.major_units <= 150);
        assert!(ticks.iter().any(|t| t.kind == TickKind::Minor));
        assert!(ticks.iter().any(|t| t.kind == TickKind::Medium));
        assert!(ticks.iter().any(|t| t.kind == TickKind::Major));
    }

    #[test]
    fn only_major_ticks_past_zero_are_labelled() {
        let (_, ticks) = compute_ticks(150, 1.0).unwrap();
        assert!(ticks
            .iter()
            .all(|t| t.show_label == (t.kind == TickKind::Major && t.value > 0)));
        // 0 still gets a full-height major tick, just no number.
        let zero = ticks.first().unwrap();
        assert_eq!(zero.value, 0);
        assert_eq!(zero.kind, TickKind::Major);
        assert!(!zero.show_label);
        assert!(ticks.iter().any(|t| t.show_label));
    }

    #[test]
    fn tick_count_stays_renderable() {
        // Worst case: the hard cap of units at a density wanting 1-unit steps.
        let (steps, ticks) = compute_ticks(MAX_UNITS_HARD_CAP, 1.0).unwrap();
        assert!(
            ticks.len() <= MAX_TICKS + 1,
            "{} ticks exceeds the render guard",
            ticks.len()
        );
        // The coarsened step is still a nice 1/2/5 value with a live hierarchy.
        assert_eq!(steps.minor_units, 20);
        assert_eq!(steps.major_units, 200);
        assert!(ticks
            .iter()
            .any(|t| t.value > 0 && t.kind == TickKind::Major));
    }

    #[test]
    fn guard_does_not_disturb_ordinary_scales() {
        // Well under the guard: the ~1.5mm pitch is left alone.
        let (steps, ticks) = compute_ticks(1000, 10.0).unwrap();
        assert_eq!(steps.minor_units, 10);
        assert!(ticks.len() < MAX_TICKS);
    }

    #[test]
    fn nice_ceil_snaps_up_to_the_1_2_5_series() {
        assert_eq!(nice_ceil(0.4), 1);
        assert_eq!(nice_ceil(1.0), 1);
        assert_eq!(nice_ceil(1.1), 2);
        assert_eq!(nice_ceil(3.0), 5);
        assert_eq!(nice_ceil(20.0), 20);
        assert_eq!(nice_ceil(21.0), 50);
    }

    #[test]
    fn calibration_gives_units_per_mm() {
        // "150 units measured 10mm" -> 15 units/mm
        assert_eq!(density_units_per_mm(150, 10.0), Some(15.0));
        assert_eq!(density_units_per_mm(1, 2.0), Some(0.5));
        assert_eq!(density_units_per_mm(0, 10.0), None);
        assert_eq!(density_units_per_mm(150, 0.0), None);
        assert_eq!(density_units_per_mm(150, -1.0), None);
        assert_eq!(density_units_per_mm(150, f64::NAN), None);
    }

    #[test]
    fn calibrated_scale_length() {
        // 150 u per 10mm = 15 u/mm; a 1000-unit scale is 1000/15 = 66.67mm.
        let d = density_units_per_mm(150, 10.0).unwrap();
        let (steps, ticks) = compute_ticks(1000, d).unwrap();
        assert!((steps.total_mm - 1000.0 / 15.0).abs() < 1e-9);
        assert!(ticks
            .iter()
            .any(|t| t.value > 0 && t.kind == TickKind::Major));
    }

    #[test]
    fn rejects_bad_input() {
        assert!(parse_units("0").is_err());
        assert!(parse_units("abc").is_err());
        assert!(parse_mm("-1").is_err());
        assert!(parse_mm("0").is_err());
        assert!(parse_font_mm("0").is_err());
        assert!(parse_font_mm("0.4").is_err());
        assert!(parse_font_mm("21").is_err());
        assert!(parse_font_mm("x").is_err());
        assert_eq!(parse_font_mm("0.5"), Ok(0.5));
        assert_eq!(parse_font_mm(" 2.5 "), Ok(2.5));
        assert_eq!(parse_font_mm("20"), Ok(20.0));
        assert!(parse_copies("0").is_err());
        assert!(parse_copies("51").is_err());
        assert!(parse_copies("1.5").is_err());
        assert_eq!(parse_copies("1"), Ok(1));
        assert_eq!(parse_copies(" 8 "), Ok(8));
        assert_eq!(parse_copies("50"), Ok(MAX_COPIES));
    }
}
