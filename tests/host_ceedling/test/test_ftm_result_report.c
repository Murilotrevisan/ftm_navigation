/* L1a -- domain/core/ftm_result_report, with its dependency MOCKED.
 *
 * This is the reference for every later CMock test in the project. Including
 * "mock_ftm_result.h" instead of "ftm_result.h" makes Ceedling generate the
 * mock from the real header and link it in place of the real
 * implementation -- a mock cannot drift from the interface, because it is
 * regenerated from it on every build (docs/TESTING.md §2).
 *
 * Both directions of the dependency are covered, as required:
 *   - it SUCCEEDS  -> the name is copied out
 *   - it FAILS     -> returns NULL, and the caller must handle it rather than
 *                     dereferencing it
 *
 * Buffer handling is covered with an explicit canary past the declared
 * capacity: an off-by-one that writes the terminator one byte too far is
 * invisible to a length-only assertion.
 */
#include <string.h>

#include "unity.h"

#include "mock_ftm_result.h"

#include "ftm_result_report.h"

void setUp(void) {}
void tearDown(void) {}

/* Buffer with a guard byte immediately after the region the callee is allowed
 * to touch. CAP is what we pass; the array is one byte longer. */
#define CAP 16u
#define CANARY 0x5Au

static char g_buf[CAP + 1u];

static void arm_buffer(void)
{
    memset(g_buf, 0, sizeof g_buf);
    g_buf[CAP] = (char)CANARY;
}

static void assert_canary_intact(void)
{
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(CANARY, (unsigned char)g_buf[CAP],
                                   "wrote past the declared capacity");
}

/* --- dependency succeeds ---------------------------------------------- */

void test_report_copies_the_name_from_the_dependency(void)
{
    arm_buffer();
    ftm_result_to_string_ExpectAndReturn(FTM_ERR_TIMEOUT, "FTM_ERR_TIMEOUT");

    TEST_ASSERT_EQUAL_INT(FTM_OK, ftm_result_report(FTM_ERR_TIMEOUT, g_buf, CAP));
    TEST_ASSERT_EQUAL_STRING("FTM_ERR_TIMEOUT", g_buf);
    assert_canary_intact();
}

void test_report_accepts_a_name_that_exactly_fills_the_buffer(void)
{
    /* 15 characters + NUL == CAP. The tightest passing case; one more
     * character must fail, which the next test asserts. */
    arm_buffer();
    ftm_result_to_string_ExpectAndReturn(FTM_OK, "123456789012345");

    TEST_ASSERT_EQUAL_INT(FTM_OK, ftm_result_report(FTM_OK, g_buf, CAP));
    TEST_ASSERT_EQUAL_STRING("123456789012345", g_buf);
    assert_canary_intact();
}

/* --- buffer too small -------------------------------------------------- */

void test_report_refuses_a_name_one_byte_too_long_and_writes_nothing(void)
{
    arm_buffer();
    ftm_result_to_string_ExpectAndReturn(FTM_OK, "1234567890123456"); /* 16 + NUL */

    TEST_ASSERT_EQUAL_INT(FTM_ERR_NO_MEM, ftm_result_report(FTM_OK, g_buf, CAP));
    TEST_ASSERT_EQUAL_CHAR_MESSAGE('\0', g_buf[0],
                                   "buffer must be untouched on failure");
    assert_canary_intact();
}

void test_report_rejects_zero_capacity_without_calling_the_dependency(void)
{
    arm_buffer();
    /* No Expect() is armed: CMock fails the test if the callee calls it. The
     * argument check must happen before any work. */
    TEST_ASSERT_EQUAL_INT(FTM_ERR_INVALID_ARG, ftm_result_report(FTM_OK, g_buf, 0u));
    assert_canary_intact();
}

/* --- NULL argument ----------------------------------------------------- */

void test_report_rejects_a_null_buffer(void)
{
    TEST_ASSERT_EQUAL_INT(FTM_ERR_INVALID_ARG, ftm_result_report(FTM_OK, NULL, CAP));
}

/* --- dependency fails -------------------------------------------------- */

void test_report_handles_the_dependency_returning_null(void)
{
    arm_buffer();
    ftm_result_to_string_ExpectAndReturn((ftm_result_t)9999, NULL);

    /* Must not dereference NULL, must report the failure, and must still show
     * the offending value so a log is diagnosable. */
    TEST_ASSERT_EQUAL_INT(FTM_ERR_INVALID_ARG,
                          ftm_result_report((ftm_result_t)9999, g_buf, CAP));
    TEST_ASSERT_EQUAL_STRING("unknown(9999)", g_buf);
    assert_canary_intact();
}

void test_report_handles_null_from_the_dependency_with_no_room_to_report_it(void)
{
    /* Both failure modes at once: unknown code AND a buffer too small for the
     * "unknown(...)" form. Nothing may be written. */
    char tiny[4] = {0, 0, 0, (char)CANARY};
    ftm_result_to_string_ExpectAndReturn((ftm_result_t)9999, NULL);

    TEST_ASSERT_EQUAL_INT(FTM_ERR_NO_MEM,
                          ftm_result_report((ftm_result_t)9999, tiny, 3u));
    TEST_ASSERT_EQUAL_CHAR('\0', tiny[0]);
    TEST_ASSERT_EQUAL_HEX8(CANARY, (unsigned char)tiny[3]);
}
