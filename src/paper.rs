//! Page geometry: paper sizes and the printable area left after the shared
//! print margin. The scale itself is drawn in millimetres and is paper
//! agnostic — the paper size only decides the `@page` rule the print dialog
//! uses and whether the current stack fits on one sheet.

/// Margin on every side of the sheet. Safe on both letter and A4: A4's
/// unprintable zone is ~5.2–15mm depending on printer, letter ~5.2mm.
/// Must stay in sync with the `@page` margin in `input.css`.
pub const PRINT_MARGIN_MM: f64 = 10.0;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum PaperSize {
    A4,
    UsLetter,
}

impl PaperSize {
    /// Parse the raw `<select>` value.
    pub fn parse(s: &str) -> Option<Self> {
        match s.trim() {
            "A4" => Some(Self::A4),
            "US Letter" => Some(Self::UsLetter),
            _ => None,
        }
    }

    /// Human-readable sheet description, e.g. "A4 landscape".
    pub fn label(self) -> &'static str {
        match self {
            Self::A4 => "A4 landscape",
            Self::UsLetter => "US Letter landscape",
        }
    }

    /// Full dimensions in landscape orientation, in millimetres.
    pub fn full_mm(self) -> (f64, f64) {
        match self {
            // ISO 216: 297 × 210.
            Self::A4 => (297.0, 210.0),
            // ANSI A / US Letter: 8.5" × 11" = 279.4 × 215.9.
            Self::UsLetter => (279.4, 215.9),
        }
    }

    /// Printable width and height after `PRINT_MARGIN_MM` on every side.
    pub fn printable_mm(self) -> (f64, f64) {
        let (w, h) = self.full_mm();
        (w - 2.0 * PRINT_MARGIN_MM, h - 2.0 * PRINT_MARGIN_MM)
    }

    /// CSS `size` descriptor for the dynamic `@page` rule.
    pub fn css_size(self) -> &'static str {
        match self {
            Self::A4 => "A4 landscape",
            Self::UsLetter => "letter landscape",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a4_printable_matches_the_previous_hardcoded_values() {
        let (w, h) = PaperSize::A4.printable_mm();
        assert!((w - 277.0).abs() < 1e-9);
        assert!((h - 190.0).abs() < 1e-9);
    }

    #[test]
    fn letter_printable() {
        let (w, h) = PaperSize::UsLetter.printable_mm();
        assert!((w - 259.4).abs() < 1e-9);
        assert!((h - 195.9).abs() < 1e-9);
    }

    #[test]
    fn parse_roundtrips_the_select_values() {
        assert_eq!(PaperSize::parse("A4"), Some(PaperSize::A4));
        assert_eq!(PaperSize::parse("US Letter"), Some(PaperSize::UsLetter));
        assert_eq!(PaperSize::parse("letter"), None);
        assert_eq!(PaperSize::parse(""), None);
    }

    #[test]
    fn css_size_uses_the_lowercase_keyword_letter() {
        assert_eq!(PaperSize::A4.css_size(), "A4 landscape");
        assert_eq!(PaperSize::UsLetter.css_size(), "letter landscape");
    }
}
