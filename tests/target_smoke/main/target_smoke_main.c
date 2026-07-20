/* L2 on-target smoke test -- the pattern every later on-target suite copies.
 *
 * Two jobs:
 *   1. Prove Unity runs on silicon and reports through the USB-Serial-JTAG
 *      console (the L2 template).
 *   2. Serve as the known-good app the L3 E2E harness flashes to both boards,
 *      which is why the markers below are stable, greppable, and printed
 *      unconditionally.
 *
 * What it asserts is deliberately target-only: FTM hardware support and a
 * real esp_wifi bring-up. Domain and service logic is NOT retested here --
 * domain/ belongs to L1a and services/ to L1b, and a module tested in two
 * places drifts (docs/TESTING.md §2).
 */
#include <stdio.h>

#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "soc/soc_caps.h"
#include "unity.h"

/* Markers the E2E harness matches on. Keep them stable -- tests/e2e depends
 * on these exact strings. */
#define MARK_BOOT   "FTM_TARGET_SMOKE_BOOT"
#define MARK_PASS   "FTM_TARGET_SMOKE_PASS"
#define MARK_FAIL   "FTM_TARGET_SMOKE_FAIL"

void setUp(void) {}
void tearDown(void) {}

static void test_ftm_is_supported_by_this_soc(void)
{
    /* docs/HARDWARE_FINDINGS.md §1: SOC_WIFI_FTM_SUPPORT is y on the
     * ESP32-C3, for initiator and responder alike. If a future board loses
     * it, this fails at the first opportunity rather than deep inside a
     * session that silently never reports. */
#if defined(SOC_WIFI_FTM_SUPPORT)
    TEST_ASSERT_TRUE_MESSAGE(SOC_WIFI_FTM_SUPPORT, "SOC_WIFI_FTM_SUPPORT is 0");
#else
    TEST_FAIL_MESSAGE("SOC_WIFI_FTM_SUPPORT is not defined for this target");
#endif

#if !defined(CONFIG_ESP_WIFI_FTM_INITIATOR_SUPPORT)
    TEST_FAIL_MESSAGE("CONFIG_ESP_WIFI_FTM_INITIATOR_SUPPORT is disabled");
#endif
#if !defined(CONFIG_ESP_WIFI_FTM_RESPONDER_SUPPORT)
    TEST_FAIL_MESSAGE("CONFIG_ESP_WIFI_FTM_RESPONDER_SUPPORT is disabled");
#endif
}

static void test_wifi_starts_and_stops_cleanly(void)
{
    /* The point of an on-target test: this path cannot be faked on the host.
     * A leak or a failed init here is what an L1 suite can never catch. */
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();

    TEST_ASSERT_EQUAL_INT(ESP_OK, esp_wifi_init(&cfg));
    TEST_ASSERT_EQUAL_INT(ESP_OK, esp_wifi_set_mode(WIFI_MODE_STA));
    TEST_ASSERT_EQUAL_INT(ESP_OK, esp_wifi_start());
    TEST_ASSERT_EQUAL_INT(ESP_OK, esp_wifi_stop());
    TEST_ASSERT_EQUAL_INT(ESP_OK, esp_wifi_deinit());
}

static void test_console_is_on_usb_serial_jtag(void)
{
    /* If this ever fails, the symptom on the bench is misleading: boot logs
     * keep appearing while every serial write times out
     * (docs/HARDWARE_FINDINGS.md §1). Assert it explicitly so the diagnosis
     * is one line instead of an afternoon. */
#if !defined(CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG)
    TEST_FAIL_MESSAGE("CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y is required");
#endif
}

void app_main(void)
{
    /* Printed before anything can fail, so the E2E harness can tell "board
     * did not boot" from "board booted and the tests failed". */
    printf("\n" MARK_BOOT "\n");
    fflush(stdout);

    esp_err_t nvs = nvs_flash_init();
    if (nvs == ESP_ERR_NVS_NO_FREE_PAGES || nvs == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    UNITY_BEGIN();
    RUN_TEST(test_console_is_on_usb_serial_jtag);
    RUN_TEST(test_ftm_is_supported_by_this_soc);
    RUN_TEST(test_wifi_starts_and_stops_cleanly);
    int failures = UNITY_END();

    if (failures == 0) {
        printf(MARK_PASS " failures=0\n");
    } else {
        printf(MARK_FAIL " failures=%d\n", failures);
    }
    fflush(stdout);
}
