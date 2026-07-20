/* L1a harness smoke test.
 *
 * Proves the Ceedling/Unity plumbing itself works, independently of any
 * project module. If this fails, the harness is broken; if only the other
 * files fail, the code under test is.
 *
 * Runs in the container, with NO hardware attached. Nothing in this directory
 * may include <serial.h>, open a port, or otherwise need a board --
 * tests/tools/test_no_hardware_imports.py enforces that mechanically.
 */
#include "unity.h"

void setUp(void) {}
void tearDown(void) {}

void test_harness_runs_a_passing_assertion(void)
{
    TEST_ASSERT_EQUAL_INT(42, 40 + 2);
}

void test_harness_compares_strings(void)
{
    TEST_ASSERT_EQUAL_STRING("ftm", "ftm");
}
