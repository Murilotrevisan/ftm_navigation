/* Shared result / error vocabulary for the whole system.
 *
 * domain/types depends on nothing but the C standard library
 * (docs/ARCHITECTURE.md §1). No ESP-IDF header may ever appear here, and
 * esp_err_t must not escape into this layer -- drivers translate at the
 * boundary.
 *
 * Phase 0 note: this module exists now because the L1a harness needs a real
 * module to test rather than a synthetic one. Phase 3 owns the final error
 * vocabulary and may extend this enum; the tests in
 * tests/host_ceedling/test/test_ftm_result.c encode the behaviour that must
 * survive that extension.
 */
#ifndef FTM_RESULT_H
#define FTM_RESULT_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    FTM_OK = 0,
    FTM_ERR_INVALID_ARG,
    FTM_ERR_NO_MEM,
    FTM_ERR_TIMEOUT,
    FTM_ERR_INVALID_MEASUREMENT,
    FTM_ERR_UNCALIBRATED,
    FTM_ERR_INSUFFICIENT_ANCHORS,
    FTM_ERR_DEGENERATE_GEOMETRY,
    FTM_RESULT_COUNT /* not a result; one past the last valid code */
} ftm_result_t;

/* Human-readable name of a result code.
 *
 * Returns NULL for any value outside [0, FTM_RESULT_COUNT). Returning NULL
 * rather than a placeholder string is deliberate: an out-of-range code is a
 * programming error and the caller is forced to notice it instead of logging
 * a plausible-looking "UNKNOWN".
 *
 * The returned pointer is to a string literal with static storage duration.
 */
const char *ftm_result_to_string(ftm_result_t result);

#ifdef __cplusplus
}
#endif

#endif /* FTM_RESULT_H */
