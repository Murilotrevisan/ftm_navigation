idf_component_register(
    SRCS "target_smoke_main.c"
    INCLUDE_DIRS "."
    REQUIRES unity esp_wifi esp_event esp_netif nvs_flash
)
