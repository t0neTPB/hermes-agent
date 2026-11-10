//! Auto-generated Saturnite wrapper crate for `anyhow`.
//!
//! This crate exposes `#[no_mangle] extern "C"` shim functions that forward
//! to the real `anyhow` crate's API. It is compiled as a `staticlib`
//! so the Saturnite linker can include it.
//!
//! ABI version: 1

extern crate anyhow;


/// ABI version: 1 -- shim for anyhow.Result_ext_context
#[no_mangle]
pub extern "C" fn sat_anyhow_Result_ext_context(arg0: *const std::os::raw::c_char, arg1: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    anyhow::Result_ext_context(arg0, arg1)
}


/// ABI version: 1 -- shim for anyhow.anyhow_macro
#[no_mangle]
pub extern "C" fn sat_anyhow_anyhow_macro(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    anyhow::anyhow_macro(arg0)
}


/// ABI version: 1 -- shim for anyhow.Error_new
#[no_mangle]
pub extern "C" fn sat_anyhow_Error_new(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    anyhow::Error_new(arg0)
}


/// ABI version: 1 -- shim for anyhow.Error_chain
#[no_mangle]
pub extern "C" fn sat_anyhow_Error_chain(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    anyhow::Error_chain(arg0)
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
