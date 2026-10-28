// The Leptos view tree is deep enough to overflow rustc's default
// query depth when the test harness monomorphises it.
#![recursion_limit = "256"]

pub mod app;
pub mod cad;
pub mod dial;
pub mod paper;
pub mod scale;

#[cfg(feature = "hydrate")]
#[wasm_bindgen::prelude::wasm_bindgen]
pub fn hydrate() {
    use crate::app::*;
    console_error_panic_hook::set_once();
    leptos::mount::hydrate_body(App);
}
