/* L1a -- domain/types/ftm_result, tested against the real implementation.
 *
 * Worst-case discipline (docs/TESTING.md §3): every public function gets a
 * nominal case, every boundary of every input, and every documented failure
 * mode. The out-of-range cases below are the point of the file -- a
 * to_string() that happily indexes past its table is the classic silent
 * memory bug.
 */
#include <stdint.h>

#include "unity.h"

#include "ftm_result.h"

void setUp(void) {}
void tearDown(void) {}

/* --- nominal ---------------------------------------------------------- */

void test_to_string_returns_the_name_of_a_known_code(void)
{
    TEST_ASSERT_EQUAL_STRING("FTM_OK", ftm_result_to_string(FTM_OK));
    TEST_ASSERT_EQUAL_STRING("FTM_ERR_INVALID_ARG",
                             ftm_result_to_string(FTM_ERR_INVALID_ARG));
}

void test_to_string_names_every_declared_code(void)
{
    /* Guards the table against an enum entry added without a name: a new code
     * would otherwise silently return NULL only when someone hits it. */
    for (int code = 0; code < (int)FTM_RESULT_COUNT; ++code) {
        const char *name = ftm_result_to_string((ftm_result_t)code);
        TEST_ASSERT_NOT_NULL_MESSAGE(name, "enum entry has no name in k_names");
        TEST_ASSERT_TRUE_MESSAGE(name[0] != '\0', "enum entry has an empty name");
    }
}

/* --- boundaries and out-of-range -------------------------------------- */

void test_to_string_rejects_the_count_sentinel(void)
{
    /* FTM_RESULT_COUNT is one past the last valid code -- the exact upper
     * boundary, and the value an off-by-one loop would pass in. */
    TEST_ASSERT_NULL(ftm_result_to_string(FTM_RESULT_COUNT));
}

void test_to_string_rejects_a_value_far_out_of_range(void)
{
    TEST_ASSERT_NULL(ftm_result_to_string((ftm_result_t)9999));
}

void test_to_string_rejects_a_negative_value(void)
{
    /* ftm_result_t may be compiled as an unsigned type, in which case this
     * arrives as a huge positive number. Either way it must be rejected. */
    TEST_ASSERT_NULL(ftm_result_to_string((ftm_result_t)-1));
}

void test_to_string_rejects_int_min(void)
{
    TEST_ASSERT_NULL(ftm_result_to_string((ftm_result_t)INT32_MIN));
}
