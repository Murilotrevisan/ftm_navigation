/* L1b entry point -- ESP-IDF `linux` target, Unity.
 *
 * Runs natively in the container, with NO hardware attached.
 *
 * THE TRAP (docs/CONTAINER.md §7): ESP-IDF's linux target keeps its scheduler
 * running after UNITY_END(). Without the explicit exit() below the binary
 * never terminates -- a failing suite HANGS instead of failing, which in CI
 * looks like a stuck machine rather than a broken build. The exit code is the
 * failure count, so the caller can branch on it.
 */
#include <stdio.h>
#include <stdlib.h>

#include "unity.h"

/* Defined in the per-module test files. */
void register_ftm_quality_tests(void);

void setUp(void) {}
void tearDown(void) {}

static void test_harness_runs_a_passing_assertion(void)
{
    TEST_ASSERT_EQUAL_INT(42, 40 + 2);
}

#ifdef FTM_TEST_SELFCHECK_FAIL
/* Harness self-check, compiled in only on demand:
 *
 *     ./tools/dev.sh test-host-selfcheck
 *
 * A suite that always exits 0 is indistinguishable from a suite that passes.
 * This deliberately-failing test proves the opposite -- that a failure
 * propagates to a non-zero exit code and the binary terminates rather than
 * hanging in the linux-target scheduler. It is never part of a normal run.
 */
static void test_selfcheck_deliberate_failure(void)
{
    TEST_FAIL_MESSAGE("deliberate failure: harness self-check");
}
#endif

void app_main(void)
{
    printf("\n=== L1b: ESP-IDF linux target, components/services ===\n");

    UNITY_BEGIN();

    RUN_TEST(test_harness_runs_a_passing_assertion);
#ifdef FTM_TEST_SELFCHECK_FAIL
    RUN_TEST(test_selfcheck_deliberate_failure);
#endif
    register_ftm_quality_tests();

    int failures = UNITY_END();

    printf("=== L1b finished: %d failure(s) ===\n", failures);
    fflush(stdout);

    /* Not optional. See the header comment. */
    exit(failures);
}
