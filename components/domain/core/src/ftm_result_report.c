#include "ftm_result_report.h"

#include <stdio.h>
#include <string.h>

ftm_result_t ftm_result_report(ftm_result_t result, char *out, size_t cap)
{
    if (out == NULL || cap == 0u) {
        return FTM_ERR_INVALID_ARG;
    }

    char scratch[32];
    ftm_result_t rv = FTM_OK;
    const char *name = ftm_result_to_string(result);

    if (name == NULL) {
        /* The dependency rejected the code. Report the offending value rather
         * than swallowing it -- but still refuse with an error, so a caller
         * cannot mistake this for a valid name. */
        (void)snprintf(scratch, sizeof scratch, "unknown(%ld)", (long)result);
        name = scratch;
        rv = FTM_ERR_INVALID_ARG;
    }

    size_t need = strlen(name) + 1u;

    if (need > cap) {
        return FTM_ERR_NO_MEM; /* deliberately writes nothing */
    }

    memcpy(out, name, need);
    return rv;
}
