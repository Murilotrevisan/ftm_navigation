/* L1b -- services/middleware/ftm_quality.
 *
 * The cases here are not hypothetical: they are the observed hardware
 * failures in docs/HARDWARE_FINDINGS.md. The clamp signature (§4, §6) is the
 * one that matters most -- a session that reports SUCCESS while 28 of its 30
 * frames were invalid, and whose 0.00 m reading is a saturated unsigned
 * subtraction rather than a measurement.
 */
#include <string.h>

#include "unity.h"

#include "ftm_quality.h"
#include "ftm_result.h"

/* Sentinel pattern: any field the callee writes on a rejected input shows up
 * as a difference from this, so "leaves `out` untouched" is actually checked
 * rather than assumed. */
static void poison(ftm_quality_t *q)
{
    memset(q, 0xA5, sizeof *q);
}

static void assert_untouched(const ftm_quality_t *q)
{
    ftm_quality_t reference;
    poison(&reference);
    TEST_ASSERT_EQUAL_MEMORY_MESSAGE(&reference, q, sizeof reference,
                                     "rejected input must not write `out`");
}

/* --- nominal ---------------------------------------------------------- */

static void test_healthy_session_is_usable(void)
{
    /* 30/30 -- the healthy count from HARDWARE_FINDINGS.md §2. */
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_OK, ftm_quality_evaluate(30u, 30u, &q));
    TEST_ASSERT_EQUAL_UINT32(30u, q.valid);
    TEST_ASSERT_EQUAL_UINT32(30u, q.total);
    TEST_ASSERT_EQUAL_UINT32(100u, q.valid_percent);
    TEST_ASSERT_TRUE(q.usable);
}

static void test_typical_healthy_session_of_28_of_30_is_usable(void)
{
    /* The low end of the observed healthy band (§2): 28/30 = 93 %. */
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_OK, ftm_quality_evaluate(28u, 30u, &q));
    TEST_ASSERT_EQUAL_UINT32(93u, q.valid_percent);
    TEST_ASSERT_TRUE(q.usable);
}

/* --- the clamp signature ---------------------------------------------- */

static void test_clamp_signature_is_unusable_despite_session_success(void)
{
    /* HARDWARE_FINDINGS.md §6: with a +600 cm offset the session still
     * reported SUCCESS while the valid count collapsed to 2/30 and every
     * reading came back 0.00 m. Status is not the quality signal; this ratio
     * is. If this test ever passes as "usable", the firmware will publish
     * clamped zeros as real distances. */
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_OK, ftm_quality_evaluate(2u, 30u, &q));
    TEST_ASSERT_EQUAL_UINT32(6u, q.valid_percent);
    TEST_ASSERT_FALSE_MESSAGE(q.usable,
                              "clamp signature (2/30) must never be usable");
}

static void test_three_of_thirty_is_also_unusable(void)
{
    /* The other end of the observed clamp band (§6 records 2-3 of 30). */
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_OK, ftm_quality_evaluate(3u, 30u, &q));
    TEST_ASSERT_FALSE(q.usable);
}

/* --- the 0.8 boundary -------------------------------------------------- */

static void test_exactly_at_the_threshold_is_usable(void)
{
    /* 24/30 = 80 % exactly. The threshold is inclusive; docs/TESTING.md §5
     * specifies "valid ratio >= 0.8". */
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_OK, ftm_quality_evaluate(24u, 30u, &q));
    TEST_ASSERT_EQUAL_UINT32(80u, q.valid_percent);
    TEST_ASSERT_TRUE_MESSAGE(q.usable, "80 % is inclusive");
}

static void test_one_frame_below_the_threshold_is_unusable(void)
{
    /* 23/30 = 76 %. The step either side of the boundary must land on
     * opposite verdicts, or the boundary is not really being tested. */
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_OK, ftm_quality_evaluate(23u, 30u, &q));
    TEST_ASSERT_EQUAL_UINT32(76u, q.valid_percent);
    TEST_ASSERT_FALSE(q.usable);
}

static void test_percent_truncates_rather_than_rounds(void)
{
    /* 4/5 = 80 % exactly usable; 79.9 % must not round up into usable.
     * 799/1000 = 79.9 -> 79. */
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_OK, ftm_quality_evaluate(799u, 1000u, &q));
    TEST_ASSERT_EQUAL_UINT32(79u, q.valid_percent);
    TEST_ASSERT_FALSE_MESSAGE(q.usable, "79.9 % must not round up to usable");
}

/* --- impossible and degenerate inputs ---------------------------------- */

static void test_valid_greater_than_total_is_rejected(void)
{
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_ERR_INVALID_MEASUREMENT,
                          ftm_quality_evaluate(31u, 30u, &q));
    assert_untouched(&q);
}

static void test_valid_one_above_total_is_rejected(void)
{
    /* The off-by-one boundary of the impossible-count check: 1/1 is fine,
     * 2/1 is not. */
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_ERR_INVALID_MEASUREMENT,
                          ftm_quality_evaluate(2u, 1u, &q));
    assert_untouched(&q);
}

static void test_zero_total_is_rejected_not_treated_as_perfect(void)
{
    /* 0/0 is not 100 % valid, and it must not divide by zero. A session that
     * attempted no frames yields no opinion. */
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_ERR_INVALID_MEASUREMENT,
                          ftm_quality_evaluate(0u, 0u, &q));
    assert_untouched(&q);
}

static void test_zero_valid_of_a_real_session_is_unusable(void)
{
    /* Legitimate input, worst possible outcome: every frame lost. */
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_OK, ftm_quality_evaluate(0u, 30u, &q));
    TEST_ASSERT_EQUAL_UINT32(0u, q.valid_percent);
    TEST_ASSERT_FALSE(q.usable);
}

static void test_null_output_is_rejected(void)
{
    TEST_ASSERT_EQUAL_INT(FTM_ERR_INVALID_ARG,
                          ftm_quality_evaluate(30u, 30u, NULL));
}

static void test_huge_counts_do_not_overflow(void)
{
    /* valid * 100 overflows uint32_t above ~42.9 M. These counts cannot come
     * from a real session, but they can come from a corrupted event
     * structure, and an overflow here would turn a 100 % session into an
     * arbitrary percentage. */
    ftm_quality_t q;
    poison(&q);

    TEST_ASSERT_EQUAL_INT(FTM_OK,
                          ftm_quality_evaluate(4000000000u, 4000000000u, &q));
    TEST_ASSERT_EQUAL_UINT32(100u, q.valid_percent);
    TEST_ASSERT_TRUE(q.usable);
}

void register_ftm_quality_tests(void)
{
    RUN_TEST(test_healthy_session_is_usable);
    RUN_TEST(test_typical_healthy_session_of_28_of_30_is_usable);
    RUN_TEST(test_clamp_signature_is_unusable_despite_session_success);
    RUN_TEST(test_three_of_thirty_is_also_unusable);
    RUN_TEST(test_exactly_at_the_threshold_is_usable);
    RUN_TEST(test_one_frame_below_the_threshold_is_unusable);
    RUN_TEST(test_percent_truncates_rather_than_rounds);
    RUN_TEST(test_valid_greater_than_total_is_rejected);
    RUN_TEST(test_valid_one_above_total_is_rejected);
    RUN_TEST(test_zero_total_is_rejected_not_treated_as_perfect);
    RUN_TEST(test_zero_valid_of_a_real_session_is_unusable);
    RUN_TEST(test_null_output_is_rejected);
    RUN_TEST(test_huge_counts_do_not_overflow);
}
