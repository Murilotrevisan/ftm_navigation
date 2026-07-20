#include "ftm_quality.h"

#include <stddef.h>

ftm_result_t ftm_quality_evaluate(uint32_t valid, uint32_t total, ftm_quality_t *out)
{
    if (out == NULL) {
        return FTM_ERR_INVALID_ARG;
    }
    if (total == 0u || valid > total) {
        return FTM_ERR_INVALID_MEASUREMENT;
    }

    /* 64-bit intermediate: valid * 100 overflows uint32_t above ~42.9 M, and
     * the frame counts arrive from the driver unvalidated. */
    uint32_t percent = (uint32_t)(((uint64_t)valid * 100u) / (uint64_t)total);

    out->valid         = valid;
    out->total         = total;
    out->valid_percent = percent;
    out->usable        = (percent >= FTM_QUALITY_MIN_VALID_PERCENT);

    return FTM_OK;
}
