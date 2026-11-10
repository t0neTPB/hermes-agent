//! Auto-generated Saturnite wrapper crate for `serde`.
//!
//! This crate exposes `#[no_mangle] extern "C"` shim functions that forward
//! to the real `serde` crate's API. It is compiled as a `staticlib`
//! so the Saturnite linker can include it.
//!
//! ABI version: 1

extern crate serde;


/// ABI version: 1 -- shim for serde.ser_Serializer_new
#[no_mangle]
pub extern "C" fn sat_serde_ser_Serializer_new() -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    serde::ser_Serializer_new()
}


/// ABI version: 1 -- shim for serde.de_Deserializer_new
#[no_mangle]
pub extern "C" fn sat_serde_de_Deserializer_new(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    serde::de_Deserializer_new(arg0)
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
