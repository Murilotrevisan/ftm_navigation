#include "ftm_result.h"

#include <stddef.h>

/* Indexed by ftm_result_t. Kept adjacent to the enum on purpose: a code added
 * to the enum without a name here yields NULL, which the tests catch. */
static const char *const k_names[FTM_RESULT_COUNT] = {
    [FTM_OK]                        = "FTM_OK",
    [FTM_ERR_INVALID_ARG]           = "FTM_ERR_INVALID_ARG",
    [FTM_ERR_NO_MEM]                = "FTM_ERR_NO_MEM",
    [FTM_ERR_TIMEOUT]               = "FTM_ERR_TIMEOUT",
    [FTM_ERR_INVALID_MEASUREMENT]   = "FTM_ERR_INVALID_MEASUREMENT",
    [FTM_ERR_UNCALIBRATED]          = "FTM_ERR_UNCALIBRATED",
    [FTM_ERR_INSUFFICIENT_ANCHORS]  = "FTM_ERR_INSUFFICIENT_ANCHORS",
    [FTM_ERR_DEGENERATE_GEOMETRY]   = "FTM_ERR_DEGENERATE_GEOMETRY",
};

const char *ftm_result_to_string(ftm_result_t result)
{
    /* The cast to a wide signed type matters: ftm_result_t may be compiled as
     * an unsigned type, in which case a negative literal arrives here as a
     * large positive value. Both must be rejected. */
    long long code = (long long)result;

    if (code < 0 || code >= (long long)FTM_RESULT_COUNT) {
        return NULL;
    }
    return k_names[code];
}
