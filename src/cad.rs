//! Browser-side 3D generation.
//!
//! Drives `public/cad-worker.js`, which runs the build123d models in `cad/*.py`
//! on Pyodide with the OpenCascade bindings from
//! [OCP.wasm](https://github.com/yeicor/OCP.wasm).  Everything happens in the
//! visitor's browser: the wheels come from PyPI/jsDelivr and no geometry, and
//! no calibration, ever leaves the page.
//!
//! The Python sources are embedded with `include_str!` rather than fetched, so
//! the model the page generates is always the one in this repository.

/// Printable parts of the dial caliper that the browser generates, in
/// assembly order.  The static hardware (FacePlate, DialRing, SliderBottom,
/// SliderTop, ArrestLever, SliderTopConnectRing, ThumbPinion and SliderBar)
/// comes from `caliper_static.3mf`; the generated beam + black inlay and the
/// pinion are merged into that project.  The paper dial is drawn by the print
/// view, not built here.
pub const PARTS: &[(&str, &str)] = &[
    ("beam", "Beam and rack"),
    ("scale_insert", "Black scale bar (second colour)"),
    ("pinion", "Herringbone pinion"),
];

/// Parts served as plain downloads.  The static hardware now lives inside
/// `caliper_static.3mf`, so nothing is prebuilt separately.
pub const PREBUILT: &[&str] = &[];

/// Where `export_static.py` writes prebuilt part files, relative to the site
/// root.  Kept for models that may add static downloads again.
pub fn prebuilt_url(part: &str) -> String {
    format!("/stl/{part}.stl")
}

/// Parts slow enough to be worth warning about.  Empty since the pinion came
/// down from ~400 s to ~10 s in the browser; kept so `Model.slow` still has
/// somewhere to point if a heavier part shows up.
pub const SLOW_PARTS: &[&str] = &[];

/// The ruler is a single part and has nothing to pick.
pub const RULER_PARTS: &[(&str, &str)] = &[("ruler", "Ruler")];

/// A model the page can generate: the build123d modules in `cad/`.  The
/// paper dial is drawn by the print view, not by a model on the worker wire.
///
/// [`Model::id`] is both the module name and the id on the worker wire; the
/// rest of the metadata drives the picker, the panels and the parts grid.
/// Keeping this an enum means the model and its parts cannot drift apart.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Model {
    Caliper,
    Ruler,
}

impl Model {
    /// Every model, in the order shown in the picker.
    pub const ALL: [Model; 2] = [Model::Ruler, Model::Caliper];

    /// The model the page starts on.
    pub const DEFAULT: Model = Model::Ruler;

    /// The build123d module name, which is also `msg.model` on the wire.
    pub fn id(self) -> &'static str {
        match self {
            Model::Caliper => "caliper",
            Model::Ruler => "ruler",
        }
    }

    /// Name shown in the model picker.
    pub fn label(self) -> &'static str {
        match self {
            Model::Caliper => "Dial caliper",
            Model::Ruler => "Ruler",
        }
    }

    /// One line under the picker.
    pub fn blurb(self) -> &'static str {
        match self {
            Model::Caliper => {
                "A working rack-and-pinion caliper, graduated in the units \
                 above, with the scale engraved into a two-colour beam. \
                 The static hardware ships in caliper_static.3mf; the beam, \
                 black inlay and pinion are generated into a copy. The dial \
                 face prints on paper above."
            }
            Model::Ruler => {
                "One flat bar with the scale above engraved 1:1 into its \
                 face, rounded corners and a hanging hole - one STL."
            }
        }
    }

    /// Printable parts, in assembly order, with the labels shown in the UI.
    pub fn parts(self) -> &'static [(&'static str, &'static str)] {
        match self {
            Model::Caliper => PARTS,
            Model::Ruler => RULER_PARTS,
        }
    }

    /// Parts shipped as static downloads rather than generated.  The caliper's
    /// static hardware is inside `caliper_static.3mf`, not in this list.
    pub fn prebuilt(self) -> &'static [&'static str] {
        match self {
            Model::Caliper => PREBUILT,
            Model::Ruler => &[],
        }
    }

    /// The prebuilt parts as (name, label, url), for the download links.
    pub fn prebuilt_parts(self) -> Vec<(&'static str, &'static str, String)> {
        self.parts()
            .iter()
            .filter(|(name, _)| self.prebuilt().contains(name))
            .map(|(name, label)| (*name, *label, prebuilt_url(name)))
            .collect()
    }

    /// The parts the browser actually has to build: everything the model has,
    /// less the ones supplied as separate prebuilt downloads.  The caliper's
    /// static project is merged in by the worker, so all three listed caliper
    /// parts are built.
    pub fn buildable(self) -> Vec<(&'static str, &'static str)> {
        self.parts()
            .iter()
            .copied()
            .filter(|(name, _)| !self.prebuilt().contains(name))
            .collect()
    }

    /// Parts slow enough to be worth warning about.
    pub fn slow(self) -> &'static [&'static str] {
        match self {
            Model::Caliper => SLOW_PARTS,
            Model::Ruler => &[],
        }
    }

    /// Every part the grid offers, in assembly order: what it starts with
    /// ticked, and what a single-part model always builds.
    pub fn all_parts(self) -> Vec<String> {
        self.buildable()
            .iter()
            .map(|(name, _)| name.to_string())
            .collect()
    }

    /// The part names to hand to the worker: a single-part model always builds
    /// its one part, a multi-part model builds the picked ones.  Only names in
    /// `all_parts` survive, so a stale selection can never reach the wrong
    /// module or rebuild a part that already ships as a static file.
    pub fn parts_to_build(self, picked: &[String]) -> Vec<String> {
        let all = self.all_parts();
        if all.len() == 1 {
            return all;
        }
        all.into_iter()
            .filter(|name| picked.contains(name))
            .collect()
    }
}

/// The model itself, compiled into the bundle.
pub const SOURCES: &[(&str, &str)] = &[
    ("scale.py", include_str!("../cad/scale.py")),
    ("vecfont.py", include_str!("../cad/vecfont.py")),
    ("stroke_din.json", include_str!("../cad/stroke_din.json")),
    ("threemf.py", include_str!("../cad/threemf.py")),
    ("gears.py", include_str!("../cad/gears.py")),
    ("caliper.py", include_str!("../cad/caliper.py")),
    ("ruler.py", include_str!("../cad/ruler.py")),
];

/// What the worker reports back.
#[derive(Clone, Debug)]
pub enum CadMsg {
    /// Pyodide is up and build123d is installed.
    Ready,
    Log(String),
    /// Derived numbers for the current parameters, preformatted.
    Summary {
        text: String,
        warnings: Vec<String>,
    },
    /// The finished model as one 3MF, ready to download in one go.
    File {
        filename: String,
        url: String,
        bytes: usize,
    },
    Done,
    Error(String),
}

#[cfg(feature = "hydrate")]
mod imp {
    use super::{CadMsg, Model, SOURCES};
    use std::cell::RefCell;
    use wasm_bindgen::prelude::*;
    use wasm_bindgen::JsCast;
    use web_sys::{Blob, BlobPropertyBag, MessageEvent, Url, Worker, WorkerOptions, WorkerType};

    thread_local! {
        static WORKER: RefCell<Option<Worker>> = const { RefCell::new(None) };
        static ON_MSG: RefCell<Option<Closure<dyn FnMut(MessageEvent)>>> =
            const { RefCell::new(None) };
    }

    fn get(obj: &JsValue, key: &str) -> JsValue {
        js_sys::Reflect::get(obj, &JsValue::from_str(key)).unwrap_or(JsValue::UNDEFINED)
    }

    fn string(obj: &JsValue, key: &str) -> String {
        get(obj, key).as_string().unwrap_or_default()
    }

    fn object(pairs: &[(&str, JsValue)]) -> JsValue {
        let obj = js_sys::Object::new();
        for (k, v) in pairs {
            let _ = js_sys::Reflect::set(&obj, &JsValue::from_str(k), v);
        }
        obj.into()
    }

    /// Turn the worker's Uint8Array into a blob URL the browser can download.
    fn blob_url(bytes: &js_sys::Uint8Array, mime: &str) -> Result<String, String> {
        let parts = js_sys::Array::of1(bytes);
        let opts = BlobPropertyBag::new();
        opts.set_type(mime);
        let blob = Blob::new_with_u8_array_sequence_and_options(&parts, &opts)
            .map_err(|_| "could not build a blob".to_string())?;
        Url::create_object_url_with_blob(&blob).map_err(|_| "could not build a URL".to_string())
    }

    fn decode(data: &JsValue) -> CadMsg {
        match string(data, "type").as_str() {
            "ready" => CadMsg::Ready,
            "log" => CadMsg::Log(string(data, "text")),
            "done" => CadMsg::Done,
            "error" => CadMsg::Error(string(data, "text")),
            "summary" => {
                let s = get(data, "summary");
                let warnings = js_sys::Array::from(&get(&s, "warnings"))
                    .iter()
                    .filter_map(|w| w.as_string())
                    .collect();
                CadMsg::Summary {
                    text: string(&s, "text"),
                    warnings,
                }
            }
            "file" => {
                let filename = string(data, "filename");
                let bytes: js_sys::Uint8Array = get(data, "bytes").unchecked_into();
                match blob_url(&bytes, "model/3mf") {
                    Ok(url) => CadMsg::File {
                        filename,
                        url,
                        bytes: bytes.length() as usize,
                    },
                    Err(e) => CadMsg::Error(e),
                }
            }
            other => CadMsg::Log(format!("unexpected message {other:?}")),
        }
    }

    /// Spawn the worker if it is not running yet, point it at `on_msg`, and
    /// ask it to boot.  Booting is idempotent inside the worker, so calling
    /// this again just gets another `Ready` back.
    pub fn start(on_msg: impl Fn(CadMsg) + 'static) -> Result<(), String> {
        WORKER.with(|slot| {
            let mut slot = slot.borrow_mut();
            if slot.is_none() {
                let opts = WorkerOptions::new();
                opts.set_type(WorkerType::Module);
                *slot = Some(
                    Worker::new_with_options("/cad-worker.js", &opts)
                        .map_err(|_| "could not start the generator worker".to_string())?,
                );
            }
            let worker = slot.as_ref().expect("just created");

            let cb = Closure::<dyn FnMut(MessageEvent)>::new(move |ev: MessageEvent| {
                on_msg(decode(&ev.data()));
            });
            worker.set_onmessage(Some(cb.as_ref().unchecked_ref()));
            ON_MSG.with(|c| *c.borrow_mut() = Some(cb));

            let sources = js_sys::Object::new();
            for (name, text) in SOURCES {
                let _ = js_sys::Reflect::set(
                    &sources,
                    &JsValue::from_str(name),
                    &JsValue::from_str(text),
                );
            }
            worker
                .post_message(&object(&[
                    ("type", JsValue::from_str("init")),
                    ("sources", sources.into()),
                ]))
                .map_err(|_| "could not talk to the worker".to_string())
        })
    }

    /// Build the given parts of `model` with the given `CALIPER_*` parameters.
    pub fn generate(
        model: Model,
        env: &[(String, String)],
        parts: &[String],
    ) -> Result<(), String> {
        let env_obj = js_sys::Object::new();
        for (k, v) in env {
            let _ = js_sys::Reflect::set(&env_obj, &JsValue::from_str(k), &JsValue::from_str(v));
        }
        let list = js_sys::Array::new();
        for p in parts {
            list.push(&JsValue::from_str(p));
        }
        // the worker fetches these rather than building them, so the 3MF it
        // makes is still the whole model
        let prebuilt = js_sys::Array::new();
        for (name, _, url) in model.prebuilt_parts() {
            prebuilt.push(&object(&[
                ("name", JsValue::from_str(name)),
                ("url", JsValue::from_str(&url)),
            ]));
        }
        WORKER.with(|w| match w.borrow().as_ref() {
            Some(worker) => worker
                .post_message(&object(&[
                    ("type", JsValue::from_str("generate")),
                    ("model", JsValue::from_str(model.id())),
                    ("env", env_obj.into()),
                    ("parts", list.into()),
                    ("prebuilt", prebuilt.into()),
                ]))
                .map_err(|_| "could not talk to the worker".to_string()),
            None => Err("the generator is not running".to_string()),
        })
    }
    /// Hand the finished archive to the browser as a file download.
    pub fn download(filename: &str, url: &str) -> Result<(), String> {
        let doc = web_sys::window()
            .and_then(|w| w.document())
            .ok_or_else(|| "the page has no document".to_string())?;
        let link: web_sys::HtmlAnchorElement = doc
            .create_element("a")
            .map_err(|_| "could not create a download link".to_string())?
            .dyn_into()
            .map_err(|_| "could not create a download link".to_string())?;
        link.set_href(url);
        link.set_download(filename);
        if let Some(body) = doc.body() {
            let _ = body.append_child(&link);
        }
        link.click();
        link.remove();
        Ok(())
    }
}

#[cfg(not(feature = "hydrate"))]
mod imp {
    use super::{CadMsg, Model};

    pub fn start(_on_msg: impl Fn(CadMsg) + 'static) -> Result<(), String> {
        Err("3D generation runs in the browser".to_string())
    }

    pub fn generate(
        _model: Model,
        _env: &[(String, String)],
        _parts: &[String],
    ) -> Result<(), String> {
        Err("3D generation runs in the browser".to_string())
    }

    pub fn download(_filename: &str, _url: &str) -> Result<(), String> {
        Err("3D generation runs in the browser".to_string())
    }
}

pub use imp::{download, generate, start};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn single_part_models_build_their_part_without_picking() {
        assert_eq!(Model::Ruler.parts_to_build(&[]), ["ruler"]);
    }

    #[test]
    fn multi_part_models_build_only_the_picked_parts() {
        let picked = vec!["pinion".to_string(), "beam".to_string()];
        // assembly order, not pick order
        assert_eq!(Model::Caliper.parts_to_build(&picked), ["beam", "pinion"]);
    }

    #[test]
    fn the_paper_dial_is_never_built_as_a_part() {
        // a stale selection naming the old dial_face STL builds nothing
        assert!(Model::Caliper
            .parts_to_build(&["dial_face".to_string()])
            .is_empty());
    }

    #[test]
    fn only_the_generated_caliper_parts_are_offered() {
        assert_eq!(
            Model::Caliper.all_parts(),
            ["beam", "scale_insert", "pinion"]
        );
        assert!(PREBUILT.is_empty());
    }

    #[test]
    fn the_old_static_stls_are_not_built_any_more() {
        // the static hardware now comes from caliper_static.3mf
        for old in ["needle", "bezel", "lock_screw"] {
            assert!(Model::Caliper.parts_to_build(&[old.to_string()]).is_empty());
        }
    }

    #[test]
    fn parts_from_another_model_are_dropped() {
        // a ruler part left in the selection used to reach the caliper module
        assert!(Model::Caliper
            .parts_to_build(&["ruler".to_string()])
            .is_empty());
    }

    #[test]
    fn every_model_id_is_a_module_we_ship() {
        for model in Model::ALL {
            let file = format!("{}.py", model.id());
            assert!(SOURCES.iter().any(|(name, _)| *name == file));
        }
    }
}
