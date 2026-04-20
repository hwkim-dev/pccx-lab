from selenium.webdriver.common.by import By


def test_app_title(driver):
    title = driver.title
    assert title, f"empty title: {title!r}"
    assert "tauri" in title.lower() or "pccx" in title.lower()


def test_root_mounted(driver):
    root = driver.find_element(By.CSS_SELECTOR, "#root")
    assert root is not None


def test_menu_bar_visible(driver):
    menu_file = driver.find_element(By.XPATH, "//button[normalize-space()='File']")
    assert menu_file.is_displayed()


def test_synth_status_tab_reachable(driver):
    """Click Verification sidebar tab, then the Synth Status sub-tab.

    This exercises the full navigation path a user would follow to reach
    the synth report widget — proving both the tab is wired in and the
    SynthStatusCard renders in the native window."""
    driver.find_element(
        By.XPATH, "//button[normalize-space()='Verification']"
    ).click()
    driver.find_element(
        By.XPATH, "//button[normalize-space()='Synth Status']"
    ).click()
    heading = driver.find_element(
        By.XPATH, "//h3[contains(., 'Post-Synthesis Status')]"
    )
    assert heading.is_displayed()
