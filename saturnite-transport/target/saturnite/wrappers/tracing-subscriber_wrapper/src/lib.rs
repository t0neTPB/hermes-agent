//! Auto-generated Saturnite wrapper crate for `tracing_subscriber`.
//!
//! This crate exposes `#[no_mangle] extern "C"` shim functions that forward
//! to the real `tracing_subscriber` crate's API. It is compiled as a `staticlib`
//! so the Saturnite linker can include it.
//!
//! ABI version: 1

extern crate tracing_subscriber;


/// ABI version: 1 -- shim for tracing_subscriber.fmt_init
#[no_mangle]
pub extern "C" fn sat_tracing_subscriber_fmt_init() -> i64 {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tracing_subscriber::fmt_init()
}


/// ABI version: 1 -- shim for tracing_subscriber.fmt_layer_new
#[no_mangle]
pub extern "C" fn sat_tracing_subscriber_fmt_layer_new() -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tracing_subscriber::fmt_layer_new()
}


/// ABI version: 1 -- shim for tracing_subscriber.Registry_with
#[no_mangle]
pub extern "C" fn sat_tracing_subscriber_Registry_with(arg0: *const std::os::raw::c_char, arg1: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tracing_subscriber::Registry_with(arg0, arg1)
}



// Embed the ABI version for runtime validation by rsrt_impl.c.
// The static is placed in a custom section so it survives dead-code elimination.
#[link_section = ".saturnite_meta"]
static _SAT_ABI_VERSION: [u8; 4] = [
    ((SATI_ABI_VERSION >> 24) & 0xFF) as u8,
    ((SATI_ABI_VERSION >> 16) & 0xFF) as u8,
    ((SATI_ABI_VERSION >> 8) & 0xFF) as u8,
    (SATI_ABI_VERSION & 0xFF) as u8,
];

const SATI_ABI_VERSION: u32 = 1;
