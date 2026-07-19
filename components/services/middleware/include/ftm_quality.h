/* Judge whether an FTM session's result is usable.
 *
 * docs/HARDWARE_FINDINGS.md §6 is the reason this module exists: a session can
 * report *success* while only 2 of 30 frames were valid (the zero-distance
 * clamp signature, §4). Session status alone is not sufficient to detect a bad
 * measurement -- the valid/total ratio is the quality signal.
 *
 * services/ public headers must not expose esp_err_t or any ESP-IDF type
 * (docs/ARCHITECTURE.md §9). This one depends on domain/types only.
 *
 * Phase 0 note: this is the reference module for the L1b harness. Phase 3 owns
 * the final filtering design; the tests in tests/host_idf encode the
 * behaviour that must survive it.
 */
#ifndef FTM_QUALITY_H
#define FTM_QUALITY_H

#include <stdbool.h>
#include <stdint.h>

#include "ftm_result.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Minimum share of valid frames for a session to be trusted, in percent.
 *
 * 80 % is the E2E acceptance floor in docs/TESTING.md §5 and
 * docs/HARDWARE_FINDINGS.md §10. A healthy session sits at 28-30 of 30 (§2);
 * the clamp signature sits at 2-3 of 30 (§6). The threshold separates them
 * with a wide margin.
 */
#define FTM_QUALITY_MIN_VALID_PERCENT 80u

typedef struct {
    uint32_t valid;         /* frames the session reported as valid          */
    uint32_t total;         /* frames the session attempted                  */
    uint32_t valid_percent; /* floor(valid * 100 / total)                    */
    bool     usable;        /* valid_percent >= FTM_QUALITY_MIN_VALID_PERCENT*/
} ftm_quality_t;

/* Evaluate a session's frame counts.
 *
 * `out` is only written when FTM_OK is returned; a rejected input leaves it
 * untouched so a caller cannot read a half-populated verdict.
 *
 * Returns:
 *   FTM_OK                        `out` populated
 *   FTM_ERR_INVALID_ARG           out == NULL
 *   FTM_ERR_INVALID_MEASUREMENT   total == 0 (no frames -- no opinion is
 *                                 possible, and 0/0 is not "100 % valid"), or
 *                                 valid > total, which the hardware can never
 *                                 legitimately report
 */
ftm_result_t ftm_quality_evaluate(uint32_t valid, uint32_t total, ftm_quality_t *out);

#ifdef __cplusplus
}
#endif

#endif /* FTM_QUALITY_H */
