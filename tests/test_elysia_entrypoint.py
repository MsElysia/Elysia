from elysia_entrypoint import (
    env_flag_enabled,
    render_attach_only_banner,
    select_backend_launch_mode,
)


def test_env_flag_enabled_accepts_supported_truthy_values():
    for value in ("1", "true", "TRUE", " yes ", "On"):
        assert env_flag_enabled("FLAG", {"FLAG": value}) is True


def test_env_flag_enabled_rejects_missing_or_falsey_values():
    for value in ("", "0", "false", "off", "no", "random"):
        assert env_flag_enabled("FLAG", {"FLAG": value}) is False
    assert env_flag_enabled("FLAG", {}) is False


def test_select_backend_launch_mode_force_full_overrides_live_backend():
    decision = select_backend_launch_mode(force_full_backend=True, backend_alive=True)

    assert decision.should_start_backend is True
    assert decision.should_attach_only is False
    assert decision.reason == "force_full_backend"


def test_select_backend_launch_mode_attachs_when_backend_is_alive():
    decision = select_backend_launch_mode(force_full_backend=False, backend_alive=True)

    assert decision.should_attach_only is True
    assert decision.should_start_backend is False
    assert decision.reason == "backend_alive"


def test_render_attach_only_banner_contains_status_url_and_guidance():
    banner = render_attach_only_banner("http://127.0.0.1:8888")

    assert "ATTACH-ONLY MODE" in banner
    assert "http://127.0.0.1:8888/status" in banner
    assert "ELYSIA_FORCE_FULL_BACKEND=1" in banner
