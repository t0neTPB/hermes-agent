//! Auto-generated Saturnite wrapper crate for `tokio_tungstenite`.
//!
//! This crate exposes `#[no_mangle] extern "C"` shim functions that forward
//! to the real `tokio_tungstenite` crate's API. It is compiled as a `staticlib`
//! so the Saturnite linker can include it.
//!
//! ABI version: 1

extern crate tokio_tungstenite;


/// ABI version: 1 -- shim for tokio_tungstenite.accept_async
#[no_mangle]
pub extern "C" fn sat_tokio_tungstenite_accept_async(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio_tungstenite::accept_async(arg0)
}


/// ABI version: 1 -- shim for tokio_tungstenite.WebSocketStream_split
#[no_mangle]
pub extern "C" fn sat_tokio_tungstenite_WebSocketStream_split(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio_tungstenite::WebSocketStream_split(arg0)
}


/// ABI version: 1 -- shim for tokio_tungstenite.WebSocketStream_sink_send
#[no_mangle]
pub extern "C" fn sat_tokio_tungstenite_WebSocketStream_sink_send(arg0: *const std::os::raw::c_char, arg1: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio_tungstenite::WebSocketStream_sink_send(arg0, arg1)
}


/// ABI version: 1 -- shim for tokio_tungstenite.WebSocketStream_stream_next
#[no_mangle]
pub extern "C" fn sat_tokio_tungstenite_WebSocketStream_stream_next(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio_tungstenite::WebSocketStream_stream_next(arg0)
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
