//! Auto-generated Saturnite wrapper crate for `tungstenite`.
//!
//! This crate exposes `#[no_mangle] extern "C"` shim functions that forward
//! to the real `tungstenite` crate's API. It is compiled as a `staticlib`
//! so the Saturnite linker can include it.
//!
//! ABI version: 1

extern crate tungstenite;


/// ABI version: 1 -- shim for tungstenite.Message_new_text
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_new_text(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_new_text(arg0)
}


/// ABI version: 1 -- shim for tungstenite.Message_new_binary
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_new_binary(arg0: *const std::os::raw::c_char, arg1: i64) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_new_binary(arg0, arg1)
}


/// ABI version: 1 -- shim for tungstenite.Message_new_ping
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_new_ping(arg0: *const std::os::raw::c_char, arg1: i64) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_new_ping(arg0, arg1)
}


/// ABI version: 1 -- shim for tungstenite.Message_new_pong
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_new_pong(arg0: *const std::os::raw::c_char, arg1: i64) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_new_pong(arg0, arg1)
}


/// ABI version: 1 -- shim for tungstenite.Message_new_close
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_new_close(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_new_close(arg0)
}


/// ABI version: 1 -- shim for tungstenite.Message_is_text
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_is_text(arg0: *const std::os::raw::c_char) -> i64 {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_is_text(arg0)
}


/// ABI version: 1 -- shim for tungstenite.Message_is_binary
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_is_binary(arg0: *const std::os::raw::c_char) -> i64 {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_is_binary(arg0)
}


/// ABI version: 1 -- shim for tungstenite.Message_is_ping
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_is_ping(arg0: *const std::os::raw::c_char) -> i64 {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_is_ping(arg0)
}


/// ABI version: 1 -- shim for tungstenite.Message_is_pong
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_is_pong(arg0: *const std::os::raw::c_char) -> i64 {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_is_pong(arg0)
}


/// ABI version: 1 -- shim for tungstenite.Message_is_close
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_is_close(arg0: *const std::os::raw::c_char) -> i64 {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_is_close(arg0)
}


/// ABI version: 1 -- shim for tungstenite.Message_text
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_text(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_text(arg0)
}


/// ABI version: 1 -- shim for tungstenite.Message_binary
#[no_mangle]
pub extern "C" fn sat_tungstenite_Message_binary(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tungstenite::Message_binary(arg0)
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
