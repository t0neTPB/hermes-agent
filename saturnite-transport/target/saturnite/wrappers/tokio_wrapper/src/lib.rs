//! Auto-generated Saturnite wrapper crate for `tokio`.
//!
//! This crate exposes `#[no_mangle] extern "C"` shim functions that forward
//! to the real `tokio` crate's API. It is compiled as a `staticlib`
//! so the Saturnite linker can include it.
//!
//! ABI version: 1

extern crate tokio;


/// ABI version: 1 -- shim for tokio.runtime_Builder_new_multi_thread
#[no_mangle]
pub extern "C" fn sat_tokio_runtime_Builder_new_multi_thread() -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio::runtime_Builder_new_multi_thread()
}


/// ABI version: 1 -- shim for tokio.runtime_Builder_enable_all
#[no_mangle]
pub extern "C" fn sat_tokio_runtime_Builder_enable_all(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio::runtime_Builder_enable_all(arg0)
}


/// ABI version: 1 -- shim for tokio.runtime_Builder_build
#[no_mangle]
pub extern "C" fn sat_tokio_runtime_Builder_build(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio::runtime_Builder_build(arg0)
}


/// ABI version: 1 -- shim for tokio.runtime_Runtime_block_on
#[no_mangle]
pub extern "C" fn sat_tokio_runtime_Runtime_block_on(arg0: *const std::os::raw::c_char, arg1: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio::runtime_Runtime_block_on(arg0, arg1)
}


/// ABI version: 1 -- shim for tokio.net_TcpListener_bind
#[no_mangle]
pub extern "C" fn sat_tokio_net_TcpListener_bind(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio::net_TcpListener_bind(arg0)
}


/// ABI version: 1 -- shim for tokio.net_TcpListener_accept
#[no_mangle]
pub extern "C" fn sat_tokio_net_TcpListener_accept(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio::net_TcpListener_accept(arg0)
}


/// ABI version: 1 -- shim for tokio.spawn
#[no_mangle]
pub extern "C" fn sat_tokio_spawn(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio::spawn(arg0)
}


/// ABI version: 1 -- shim for tokio.time_sleep
#[no_mangle]
pub extern "C" fn sat_tokio_time_sleep(arg0: i64) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio::time_sleep(arg0)
}


/// ABI version: 1 -- shim for tokio.task_JoinHandle_await
#[no_mangle]
pub extern "C" fn sat_tokio_task_JoinHandle_await(arg0: *const std::os::raw::c_char) -> *const std::os::raw::c_char {
    // Validate ABI version at compile time via static assertion.
    const _: () = {
        const _ASSERT_ABI_VERSION: () = [()][(1 - 1) as usize % 1];
        let _ = _ASSERT_ABI_VERSION;
    };
    tokio::task_JoinHandle_await(arg0)
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
