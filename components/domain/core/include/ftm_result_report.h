/* Render a result code into a caller-supplied buffer.
 *
 * domain/core is pure logic: no allocation, no I/O, no ESP-IDF
 * (docs/ARCHITECTURE.md §1). This module exists in Phase 0 as the reference
 * example of a core module with a *mockable dependency* -- it calls
 * ftm_result_to_string() from domain/types, which the L1a suite replaces with
 * a CMock mock to exercise both the success and the failure path of that
 * dependency.
 */
#ifndef FTM_RESULT_REPORT_H
#define FTM_RESULT_REPORT_H

#include <stddef.h>

#include "ftm_result.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Write the name of `result` as a NUL-terminated string into `out`.
 *
 * Never writes more than `cap` bytes, and on failure writes nothing at all --
 * a partially filled buffer is worse than an untouched one because it looks
 * like data.
 *
 * Returns:
 *   FTM_OK                 name written
 *   FTM_ERR_INVALID_ARG    out == NULL, cap == 0, or `result` is out of range
 *                          (in the out-of-range case a "unknown(<n>)" form is
 *                          still written when it fits, so a caller logging the
 *                          buffer sees the offending value)
 *   FTM_ERR_NO_MEM         `cap` too small for the name plus its terminator;
 *                          `out` is left untouched
 */
ftm_result_t ftm_result_report(ftm_result_t result, char *out, size_t cap);

#ifdef __cplusplus
}
#endif

#endif /* FTM_RESULT_REPORT_H */
